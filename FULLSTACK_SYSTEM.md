# Buy or Wait? — Full-Stack AI Financial Decision System

An enterprise-grade, deterministic, and AI-powered financial advisory system built for the **HackerRank Orchestrate (September 2026)** hackathon challenge.

---

## Architecture Overview

The system mirrors the two specification diagrams:

```
┌────────────────────────────────────────────────────────┐
│                   Next.js 15 Frontend                  │
│  (React 19 + TypeScript + Tailwind CSS + Recharts)    │
│                                                        │
│  [ Dashboard ]     [ Decision Card ]  [ Timeline ]     │
│  Top 5 KPI Cards   Safe Today Hero    90-Day Traj      │
│  Filterable Table  Method & Plan      Min Reserve Line │
│                                                        │
│                 [ Ask Agent AI Chat ]                  │
│                 Interactive Advisory                   │
└───────────────────────────┬────────────────────────────┘
                            │ REST API (JSON)
                            ▼
┌────────────────────────────────────────────────────────┐
│                   FastAPI Backend                      │
│                                                        │
│  GET /api/stats            GET /api/requests           │
│  GET /api/requests/{id}    GET /api/timeline/{id}      │
│  POST /api/chat            GET / (Web Dashboard)       │
└──────────────┬────────────────────────────┬────────────┘
               ▼                            ▼
┌─────────────────────────────┐  ┌───────────────────────┐
│     Financial Engine        │  │     SQLite Database   │
│  financial_state.py         │  │  Profiles, Events,    │
│  forecaster.py (90-day sim) │  │  Requests, Options,   │
│  decision_engine.py         │  │  Predictions Cache    │
└─────────────────────────────┘  └───────────────────────┘
```

---

## Components

### 1. Backend Layer (`backend/`)
- **`backend/main.py`**: FastAPI REST server exposing:
  - `GET /api/stats`: High-level metrics across all 275 requests (total, affordable now, with plan, later, not affordable, and safe volumes).
  - `GET /api/requests`: Search and status-filtered paginated list of purchase requests.
  - `GET /api/requests/{id}`: Detailed request analysis, user financial position, payment options, and decision breakdown.
  - `GET /api/timeline/{id}`: 90-day daily balance trajectory computed directly by the core financial forecasting engine (`code/forecaster.py` & `code/financial_state.py`).
  - `POST /api/chat`: Grounded AI financial advisory chat answering user inquiries regarding rationale, safe amounts, budget cuts, and payment milestones.
  - `GET /`: Embedded interactive web dashboard.
- **`backend/database.py`**: SQLite initialization and relational queries.
- **`backend/models.py`**: Pydantic schemas validating all inputs and outputs.
- **`backend/static/index.html`**: Zero-dependency modern web application with Tailwind CDN, Chart.js cash flow curve, metric cards, and live chat.

### 2. Frontend Layer (`frontend/`)
- Built with **Next.js 15 App Router**, **TypeScript**, **Tailwind CSS**, and **Recharts**.
- **`frontend/components/Dashboard.tsx`**: Top 5 KPI metric cards, search bar, status filters (`All`, `Affordable Now`, `With Plan`, `Affordable Later`, `Not Affordable`), and interactive requests table.
- **`frontend/components/DecisionCard.tsx`**: Amount Safe Today hero badge, affordability status, recommended method, staged milestone schedule, budget adjustment badges, and explanation.
- **`frontend/components/FinancialTimeline.tsx`**: Responsive Recharts area chart with 90-day balance curve and red dashed minimum reserve threshold.
- **`frontend/components/AskAgent.tsx`**: Chat assistant with quick suggestion chips and live financial Q&A.
- **`frontend/app/page.tsx`**: Main landing dashboard tying all modules together.

### 3. Core Financial Engine (`code/`)
- **`code/data_loader.py`**: Zero-dependency CSV reader parsing all dataset files using Python standard library.
- **`code/financial_state.py`**: Financial reconstruction accounting for settled income, scheduled expenses, reserved debits, and multi-week recurring salary detection.
- **`code/forecaster.py`**: Conservative 90-day daily cash flow simulation.
- **`code/decision_engine.py`**: Affordability evaluator, installment optimizer, and spending reduction planner conforming strictly to AGENTS.md §6.

---

## How to Run

### Run the FastAPI Backend & Web Dashboard
```bash
# From repo root
python backend/main.py
```
Open **`http://127.0.0.1:8000`** in your browser to view the interactive dashboard and test `/docs` for Swagger UI.

### Run the Next.js 15 Frontend
```bash
cd frontend
npm run dev
```
Open **`http://localhost:3000`** in your browser.

### Run Evaluation & Regenerate Submission Output
```bash
python code/main.py
python validate_submission.py
```

---

## HackerRank Submission
- **Deadline**: September 13, 2026, 6:00 PM IST
- **Submission URL**: https://www.hackerrank.com/contests/hackerrank-orchestrate-september26/challenges/buy-or-wait/submission
- **Deliverables**:
  - `output.csv` (250 evaluated predictions)
  - `code.zip` (clean source package with `evaluation/usage_report.md`)
  - `log.txt` (session & turn logs following §5)
