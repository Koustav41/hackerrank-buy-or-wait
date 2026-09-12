"""
main.py
Entry point for the Buy or Wait? financial agent.

Usage:
    python code/main.py [--sample] [--limit N]

Flags:
    --sample    Process sample_requests.csv instead of requests.csv
    --limit N   Only process the first N requests (for testing)
"""

import os
import sys
import csv
import logging
import argparse
import json
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List, Tuple

# Add code directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import load_all, AllData, Request
from currency_converter import CurrencyConverter
from image_extractor import ImageExtractor
from message_parser import MessageParser
from financial_state import build_financial_state, FinancialState
from decision_engine import make_decision, Decision

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(REPO_ROOT, "dataset")
OUTPUT_CSV = os.path.join(DATASET_DIR, "output.csv")
USAGE_REPORT = os.path.join(REPO_ROOT, "code", "evaluation", "usage_report.md")

OUTPUT_COLUMNS = [
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]


def format_amount(amount: float) -> str:
    """Format amount: integer if whole number, else 2 decimals."""
    if amount == int(amount):
        return str(int(amount))
    return f"{round(amount, 2):.2f}"


def process_request(
    request: Request,
    data: AllData,
    converter: CurrencyConverter,
    image_extractor: ImageExtractor,
    message_parser: MessageParser,
    image_amounts: Dict[str, Tuple[Optional[float], Optional[str]]],
) -> Decision:
    """Process a single request and return a Decision."""
    user_id = request.user_id
    request_id = request.request_id

    profile = data.profiles.get(user_id)
    if not profile:
        logger.error(f"No profile for user {user_id} (request {request_id})")
        return Decision(
            request_id=request_id,
            amount_safe_to_pay=0.0,
            affordability_status="not_affordable",
            recommended_payment_method="not_recommended",
            payment_plan="none",
            earliest_date_for_full_payment="",
            spending_changes_needed="none",
            decision_explanation="User profile not found.",
        )

    # Get user events
    user_events = [e for e in data.events if e.user_id == user_id]

    # Parse messages relevant to this user/request
    message_amendments = message_parser.parse_all_relevant_messages(
        messages=data.messages,
        user_id=user_id,
        request_id=request_id,
        events_by_id={e.event_id: e for e in user_events},
    )

    # Build financial state
    try:
        fs = build_financial_state(
            user_id=user_id,
            request_date=request.request_date,
            profile=profile,
            user_events=user_events,
            converter=converter,
            image_amounts=image_amounts,
            message_amendments=message_amendments,
        )
    except Exception as e:
        logger.error(f"Failed to build financial state for {request_id}: {e}", exc_info=True)
        return Decision(
            request_id=request_id,
            amount_safe_to_pay=0.0,
            affordability_status="not_affordable",
            recommended_payment_method="not_recommended",
            payment_plan="none",
            earliest_date_for_full_payment="",
            spending_changes_needed="none",
            decision_explanation=f"Could not reconstruct financial state: {e}",
        )

    # Make decision
    try:
        decision = make_decision(
            request=request,
            profile=profile,
            fs=fs,
            payment_options=data.payment_options,
        )
    except Exception as e:
        logger.error(f"Decision engine failed for {request_id}: {e}", exc_info=True)
        decision = Decision(
            request_id=request_id,
            amount_safe_to_pay=0.0,
            affordability_status="not_affordable",
            recommended_payment_method="not_recommended",
            payment_plan="none",
            earliest_date_for_full_payment="",
            spending_changes_needed="none",
            decision_explanation=f"Decision engine error: {e}",
        )

    return decision


def write_output(decisions: List[Decision], output_path: str):
    """Write decisions to output.csv."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for d in decisions:
            writer.writerow({
                "request_id": d.request_id,
                "amount_safe_to_pay": format_amount(d.amount_safe_to_pay),
                "affordability_status": d.affordability_status,
                "recommended_payment_method": d.recommended_payment_method,
                "payment_plan": d.payment_plan,
                "earliest_date_for_full_payment": d.earliest_date_for_full_payment,
                "spending_changes_needed": d.spending_changes_needed,
                "decision_explanation": d.decision_explanation,
            })
    logger.info(f"Written {len(decisions)} rows to {output_path}")


def write_usage_report(
    image_extractor: ImageExtractor,
    message_parser: MessageParser,
    n_requests: int,
    elapsed_seconds: float,
):
    """Write the evaluation/usage_report.md as required by AGENTS.md §6.5."""
    img_usage = image_extractor.get_total_token_usage()
    msg_usage = message_parser.get_total_token_usage()

    total_input = img_usage["total_input_tokens"] + msg_usage["total_input_tokens"]
    total_output = img_usage["total_output_tokens"] + msg_usage["total_output_tokens"]
    total_tokens = total_input + total_output

    # Approximate costs (Claude Sonnet: $3/$15 per M; Claude Haiku: $0.25/$1.25 per M)
    img_cost = (
        img_usage["total_input_tokens"] * 3.0 / 1_000_000 +
        img_usage["total_output_tokens"] * 15.0 / 1_000_000
    )
    msg_cost = (
        msg_usage["total_input_tokens"] * 0.25 / 1_000_000 +
        msg_usage["total_output_tokens"] * 1.25 / 1_000_000
    )
    total_cost = img_cost + msg_cost

    report = f"""# Token Usage Report — Buy or Wait?

Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Requests processed: {n_requests}
Total elapsed time: {elapsed_seconds:.1f}s

## Model Usage

### Image Extraction (claude-sonnet-4-5)
| Metric | Value |
|--------|-------|
| Model | claude-sonnet-4-5 |
| API calls | {img_usage["calls"]} |
| Input tokens | {img_usage["total_input_tokens"]:,} |
| Output tokens | {img_usage["total_output_tokens"]:,} |
| Total tokens | {img_usage["total_input_tokens"] + img_usage["total_output_tokens"]:,} |
| Avg tokens/image | {(img_usage["total_input_tokens"] + img_usage["total_output_tokens"]) / max(1, img_usage["calls"]):.0f} |
| Estimated cost | ${img_cost:.4f} |

### Message Parsing (claude-haiku-4-5)
| Metric | Value |
|--------|-------|
| Model | claude-haiku-4-5 |
| API calls | {msg_usage["calls"]} |
| Input tokens | {msg_usage["total_input_tokens"]:,} |
| Output tokens | {msg_usage["total_output_tokens"]:,} |
| Total tokens | {msg_usage["total_input_tokens"] + msg_usage["total_output_tokens"]:,} |
| Avg tokens/call | {(msg_usage["total_input_tokens"] + msg_usage["total_output_tokens"]) / max(1, msg_usage["calls"]):.0f} |
| Estimated cost | ${msg_cost:.4f} |

## Overall Totals
| Metric | Value |
|--------|-------|
| Total input tokens | {total_input:,} |
| Total output tokens | {total_output:,} |
| Total tokens | {total_tokens:,} |
| Avg tokens per request | {total_tokens / max(1, n_requests):.1f} |
| Total estimated cost | ${total_cost:.4f} |
| Avg cost per request | ${total_cost / max(1, n_requests):.6f} |

## Notes
- Image extraction uses cached results; API only called once per image.
- Message parsing uses cached results; API only called once per message.
- Financial state reconstruction and decision logic are fully deterministic (no LLM).
- All costs are estimates based on public Anthropic API pricing.
"""

    os.makedirs(os.path.dirname(USAGE_REPORT), exist_ok=True)
    with open(USAGE_REPORT, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info(f"Usage report written to {USAGE_REPORT}")


def main():
    import time

    parser = argparse.ArgumentParser(description="Buy or Wait? financial agent")
    parser.add_argument("--sample", action="store_true",
                        help="Process sample_requests.csv (with known answers)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only process first N requests")
    args = parser.parse_args()

    start_time = time.time()

    # ---- Load API key ----
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        # Try .env file
        env_file = os.path.join(REPO_ROOT, ".env")
        if os.path.exists(env_file):
            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("ANTHROPIC_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        os.environ["ANTHROPIC_API_KEY"] = api_key
                        break

    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set. Image extraction and message parsing will be skipped.")
    else:
        logger.info("ANTHROPIC_API_KEY loaded.")

    # ---- Load all data ----
    logger.info("Loading dataset...")
    data = load_all()
    logger.info(f"Loaded: {len(data.requests)} requests, {len(data.profiles)} profiles, "
                f"{len(data.events)} events, {len(data.payment_options)} payment options, "
                f"{len(data.messages)} messages, {len(data.images)} images")

    # ---- Build converter ----
    converter = CurrencyConverter(data.exchange_rates)

    # ---- Pre-extract image amounts ----
    image_extractor = ImageExtractor(api_key=api_key)
    events_by_id = {e.event_id: e for e in data.events}
    logger.info("Pre-extracting image amounts...")
    image_amounts = image_extractor.preload_all_images(
        images=data.images,
        events_by_id=events_by_id,
        profiles=data.profiles,
    )
    logger.info(f"Image extraction complete: {len(image_amounts)} events resolved")

    # ---- Initialize message parser ----
    message_parser = MessageParser(api_key=api_key)

    # ---- Choose request set ----
    if args.sample:
        requests_to_process = data.sample_requests
        logger.info(f"Processing {len(requests_to_process)} sample requests")
    else:
        requests_to_process = data.requests
        logger.info(f"Processing {len(requests_to_process)} evaluation requests")

    if args.limit:
        requests_to_process = requests_to_process[:args.limit]
        logger.info(f"Limited to {len(requests_to_process)} requests")

    # ---- Process each request ----
    decisions = []
    for i, req in enumerate(requests_to_process, 1):
        logger.info(f"[{i}/{len(requests_to_process)}] Processing {req.request_id} "
                    f"(user={req.user_id}, amount={req.requested_amount}, date={req.request_date})")
        decision = process_request(
            request=req,
            data=data,
            converter=converter,
            image_extractor=image_extractor,
            message_parser=message_parser,
            image_amounts=image_amounts,
        )
        decisions.append(decision)
        logger.info(
            f"  -> {decision.affordability_status} | {decision.recommended_payment_method} "
            f"| safe_today={decision.amount_safe_to_pay:.2f}"
        )

    # ---- Write output ----
    write_output(decisions, OUTPUT_CSV)

    # ---- Write usage report ----
    elapsed = time.time() - start_time
    write_usage_report(image_extractor, message_parser, len(decisions), elapsed)

    # ---- Write log entry ----
    log_path = os.path.join(REPO_ROOT, "log.txt")
    log_entry = (
        f"\n## {datetime.now().isoformat()} Build complete — generated {len(decisions)} predictions\n\n"
        f"User Prompt (verbatim, secrets redacted):\n"
        f"Run main.py to generate output.csv\n\n"
        f"Agent Response Summary:\n"
        f"Processed {len(decisions)} requests. "
        f"Output written to {OUTPUT_CSV}. "
        f"Usage report written to {USAGE_REPORT}.\n\n"
        f"Actions:\n"
        f"* code/main.py executed\n"
        f"* dataset/output.csv written ({len(decisions)} rows)\n"
        f"* code/evaluation/usage_report.md written\n\n"
        f"Context:\n"
        f"tool=Antigravity IDE (Google DeepMind)\n"
        f"branch=main\n"
        f"repo_root={REPO_ROOT}\n"
        f"worktree=main\n"
        f"parent_agent=none\n"
    )
    with open(log_path, "a", encoding="utf-8", newline="\n") as f:
        f.write(log_entry)

    logger.info(f"Done! Elapsed: {elapsed:.1f}s")

    # ---- If sample mode, print accuracy ----
    if args.sample:
        _evaluate_sample(decisions, data.sample_outputs)


def _evaluate_sample(decisions: List[Decision], sample_outputs: dict):
    """Compare decisions against sample_outputs and report accuracy."""
    print("\n" + "=" * 70)
    print("SAMPLE ACCURACY EVALUATION")
    print("=" * 70)

    status_correct = 0
    method_correct = 0
    total = 0

    for d in decisions:
        expected = sample_outputs.get(d.request_id, {})
        if not expected:
            continue

        total += 1
        exp_status = expected.get("affordability_status", "")
        exp_method = expected.get("recommended_payment_method", "")
        exp_plan = expected.get("payment_plan", "")
        exp_earliest = expected.get("earliest_date_for_full_payment", "")
        exp_changes = expected.get("spending_changes_needed", "")
        exp_safe = expected.get("amount_safe_to_pay", "")

        s_match = d.affordability_status == exp_status
        m_match = d.recommended_payment_method == exp_method

        if s_match:
            status_correct += 1
        if m_match:
            method_correct += 1

        match_symbol = "OK" if (s_match and m_match) else "XX"
        print(f"\n[{match_symbol}] {d.request_id}:")
        print(f"  status: {d.affordability_status:<25} (expected: {exp_status})")
        print(f"  method: {d.recommended_payment_method:<25} (expected: {exp_method})")
        print(f"  safe_today: {format_amount(d.amount_safe_to_pay):<20} (expected: {exp_safe})")
        print(f"  earliest: {d.earliest_date_for_full_payment:<25} (expected: {exp_earliest})")
        if not s_match or not m_match:
            print(f"  plan: {d.payment_plan}")
            print(f"  exp plan: {exp_plan}")
            print(f"  changes: {d.spending_changes_needed}")
            print(f"  exp changes: {exp_changes}")

    if total > 0:
        print(f"\n{'=' * 70}")
        print(f"TOTALS: {total} requests")
        print(f"  affordability_status: {status_correct}/{total} ({100*status_correct/total:.1f}%)")
        print(f"  recommended_payment_method: {method_correct}/{total} ({100*method_correct/total:.1f}%)")


if __name__ == "__main__":
    main()
