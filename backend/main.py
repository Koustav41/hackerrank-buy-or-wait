import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE_DIR = os.path.join(BASE_DIR, "code")
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
STATIC_DIR = os.path.join(BACKEND_DIR, "static")
SITE_PACKAGES = os.path.join(BASE_DIR, ".venv", "Lib", "site-packages")
for p in (SITE_PACKAGES, CODE_DIR, BACKEND_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from data_loader import load_all, AllData
from currency_converter import CurrencyConverter
from financial_state import build_financial_state
from forecaster import simulate_balance
import database
from models import (
    RequestSummary,
    DecisionDetail,
    TimelinePoint,
    StatsSummary,
    ChatRequest,
    ChatResponse
)

app = FastAPI(
    title="Buy or Wait Financial Decision Agent API",
    description="REST API serving financial decisions, 90-day balance trajectories, and interactive AI financial advisory.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA: Optional[AllData] = None
CONVERTER: Optional[CurrencyConverter] = None

def get_data() -> tuple[AllData, CurrencyConverter]:
    global DATA, CONVERTER
    if DATA is None or CONVERTER is None:
        database.init_db()
        DATA = load_all()
        CONVERTER = CurrencyConverter(DATA.exchange_rates)
    return DATA, CONVERTER


@app.get("/", include_in_schema=False)
def serve_dashboard():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Buy or Wait API is running. Go to /docs for OpenAPI docs."}

@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.get("/api/stats", response_model=StatsSummary)
def get_stats():
    stats = database.get_stats()
    return stats

@app.get("/api/requests", response_model=List[RequestSummary])
def get_requests(
    q: Optional[str] = Query(None, description="Search query for purpose, category, id"),
    status: Optional[str] = Query(None, description="Filter by affordability_status"),
    limit: int = Query(250, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    rows = database.get_all_requests(query=q, status=status, limit=limit, offset=offset)
    return rows

@app.get("/api/requests/{request_id}", response_model=DecisionDetail)
def get_request_detail(request_id: str):
    detail = database.get_request_detail(request_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Request not found")
    return detail

@app.get("/api/timeline/{request_id}", response_model=List[TimelinePoint])
def get_timeline(request_id: str):
    detail = database.get_request_detail(request_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Request not found")

    user_id = detail["user_id"]
    req_date_str = detail["request_date"]
    try:
        req_date = datetime.strptime(req_date_str, "%Y-%m-%d").date()
    except Exception:
        req_date = datetime.now().date()

    data, converter = get_data()
    profile = data.profiles.get(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    user_events = [e for e in data.events if e.user_id == user_id]

    fs = build_financial_state(
        user_id=user_id,
        request_date=req_date,
        profile=profile,
        user_events=user_events,
        converter=converter,
        image_amounts={},
        message_amendments={},
    )

    end_date = req_date + timedelta(days=90)

    # Spending changes
    spending_changes = {}
    changes_str = detail.get("spending_changes_needed", "none")
    if changes_str and changes_str.lower() != "none":
        for part in changes_str.split(";"):
            part = part.strip()
            if part.startswith("stop:"):
                eid = part.split(":")[1]
                spending_changes[eid] = -1.0
            elif part.startswith("reduce_to:"):
                pieces = part.split(":")
                eid = pieces[1]
                val = float(pieces[2])
                spending_changes[eid] = val

    # Extra debits
    extra_debits = []
    plan_str = detail.get("payment_plan", "none")
    if plan_str and plan_str.lower() != "none":
        for entry in plan_str.split("|"):
            if ":" in entry:
                d_s, amt_s = entry.split(":")
                try:
                    d_obj = datetime.strptime(d_s.strip(), "%Y-%m-%d").date()
                    extra_debits.append((d_obj, float(amt_s.strip())))
                except Exception:
                    pass

    daily_balance, _ = simulate_balance(
        start_balance=fs.effective_balance,
        events=fs.future_events,
        start_date=req_date,
        end_date=end_date,
        extra_debits=extra_debits,
        spending_changes=spending_changes,
    )

    points = []
    curr = req_date
    prev_bal = fs.effective_balance
    while curr <= end_date:
        bal = daily_balance.get(curr, prev_bal)
        net_flow = round(bal - prev_bal, 2)
        prev_bal = bal
        curr_str = curr.strftime("%Y-%m-%d")
        points.append(
            TimelinePoint(
                date=curr_str,
                balance=round(bal, 2),
                min_balance=round(fs.min_balance, 2),
                net_flow=net_flow,
                notes=None
            )
        )
        curr += timedelta(days=1)

    return points

@app.post("/api/chat", response_model=ChatResponse)
def ask_agent(req: ChatRequest):
    question = req.question.strip()
    req_detail = None
    if req.request_id:
        req_detail = database.get_request_detail(req.request_id)

    lower_q = question.lower()
    
    if req_detail:
        purpose = req_detail.get("purpose") or req_detail.get("request_text") or "Requested Item"
        amount = req_detail.get("requested_amount", 0.0)
        currency = req_detail.get("currency", "USD")
        status = req_detail.get("affordability_status", "unknown")
        method = req_detail.get("recommended_payment_method", "unknown")
        safe_amt = req_detail.get("amount_safe_to_pay", 0.0)
        explanation = req_detail.get("decision_explanation", "")
        min_bal = req_detail.get("minimum_balance_to_keep", 0.0)
        curr_bal = req_detail.get("current_balance", 0.0)
        plan = req_detail.get("payment_plan", "none")
        earliest = req_detail.get("earliest_date_for_full_payment")
        spending_changes = req_detail.get("spending_changes_needed")

        if "why" in lower_q or "reason" in lower_q or "explain" in lower_q:
            ans = (
                f"Regarding your purchase request '{purpose}' for {currency} {amount:,.2f}:\n\n"
                f"**Status**: {status.replace('_', ' ').title()}\n"
                f"**Recommended Method**: {method.replace('_', ' ').title()}\n\n"
                f"**Decision Reasoning**:\n{explanation}\n\n"
                f"**Financial Position**:\n"
                f"- Current Available Balance: {currency} {curr_bal:,.2f}\n"
                f"- Minimum Required Reserve: {currency} {min_bal:,.2f}\n"
            )
            if safe_amt > 0 and safe_amt < amount:
                ans += f"- Safe to pay on request date: {currency} {safe_amt:,.2f}\n"
            elif safe_amt == amount:
                ans += f"- Full payment of {currency} {safe_amt:,.2f} is 100% safe immediately.\n"
            return ChatResponse(answer=ans, context=req_detail)

        elif "plan" in lower_q or "schedule" in lower_q or "installment" in lower_q or "how to pay" in lower_q:
            if plan and plan.lower() != "none":
                ans = (
                    f"Here is your recommended payment schedule for **{purpose}** ({currency} {amount:,.2f}):\n\n"
                    f"**Payment Method**: {method.replace('_', ' ').title()}\n\n"
                    f"**Milestones**:\n"
                )
                for step in plan.split("|"):
                    if ":" in step:
                        d, a = step.split(":")
                        ans += f"- **{d.strip()}**: {currency} {float(a):,.2f}\n"
                if spending_changes and spending_changes != "none":
                    ans += f"\n**Required Spending Adjustments**: `{spending_changes}`\n"
            else:
                ans = (
                    f"For request '{purpose}', the recommended method is **{method.replace('_', ' ').title()}**. "
                    f"No installment or partial schedule is needed or recommended. "
                )
                if earliest:
                    ans += f"Full payment is safely achievable on **{earliest}** once confirmed income arrives."
            return ChatResponse(answer=ans, context=req_detail)

        elif "safe" in lower_q or "afford" in lower_q or "balance" in lower_q or "how much" in lower_q:
            ans = (
                f"For **{purpose}**, the maximum safe payment today is **{currency} {safe_amt:,.2f}**.\n\n"
                f"- Current Balance: {currency} {curr_bal:,.2f}\n"
                f"- Minimum Reserve: {currency} {min_bal:,.2f}\n"
                f"- Earliest Full Settlement Date: {earliest if earliest else 'Not safe within 90-day forecast'}\n\n"
                f"**Recommendation**: {explanation}"
            )
            return ChatResponse(answer=ans, context=req_detail)

    # General overview question
    stats = database.get_stats()
    ans = (
        f"Hello! I am your Buy or Wait AI Financial Advisor. Across all {stats['total_requests']} analyzed requests:\n\n"
        f"- **Affordable Now**: {stats['affordable_now']} requests\n"
        f"- **Affordable With Plan**: {stats['affordable_with_plan']} requests (via partial payment or installments)\n"
        f"- **Affordable Later**: {stats['affordable_later']} requests (after verified salary settlement)\n"
        f"- **Not Affordable**: {stats['not_affordable']} requests\n\n"
        f"Select any specific purchase request from the dashboard to inspect its 90-day cash flow simulation, payment options, and personalized budget adjustments!"
    )
    return ChatResponse(answer=ans, context=stats)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
