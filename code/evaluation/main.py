"""
evaluation/main.py
Evaluate output.csv against sample_requests.csv ground truth.
"""

import os
import sys
import csv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATASET_DIR = os.path.join(REPO_ROOT, "dataset")


def load_csv(path):
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def evaluate():
    sample_path = os.path.join(DATASET_DIR, "sample_requests.csv")
    output_path = os.path.join(DATASET_DIR, "output.csv")

    if not os.path.exists(output_path):
        print(f"ERROR: {output_path} not found. Run main.py --sample first.")
        return

    sample = {row["request_id"]: row for row in load_csv(sample_path)}
    output = {row["request_id"]: row for row in load_csv(output_path)}

    # Find sample requests in output
    common = [rid for rid in sample if rid in output]

    if not common:
        print("No common request_ids found between sample and output.")
        return

    fields = [
        "affordability_status",
        "recommended_payment_method",
        "earliest_date_for_full_payment",
        "spending_changes_needed",
    ]

    print(f"\nEvaluating {len(common)} sample requests against output.csv\n")
    print("=" * 80)

    field_counts = {f: 0 for f in fields}
    amount_errors = []
    total = len(common)

    for rid in sorted(common):
        exp = sample[rid]
        got = output[rid]

        print(f"\n--- {rid} ---")
        all_match = True

        for f in fields:
            e_val = exp.get(f, "").strip()
            g_val = got.get(f, "").strip()
            match = e_val == g_val
            if match:
                field_counts[f] += 1
            else:
                all_match = False
            symbol = "✓" if match else "✗"
            print(f"  {symbol} {f}:")
            print(f"      got: {g_val}")
            print(f"      exp: {e_val}")

        # Amount safe to pay (within 5% tolerance)
        try:
            exp_amt = float(exp.get("amount_safe_to_pay", 0))
            got_amt = float(got.get("amount_safe_to_pay", 0))
            if exp_amt > 0:
                err_pct = abs(exp_amt - got_amt) / exp_amt * 100
            else:
                err_pct = abs(got_amt) * 100
            amount_errors.append(err_pct)
            symbol = "✓" if err_pct < 5.0 else "✗"
            print(f"  {symbol} amount_safe_to_pay: got={got_amt:.2f} exp={exp_amt:.2f} (err={err_pct:.1f}%)")
        except (ValueError, TypeError):
            pass

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for f in fields:
        pct = 100 * field_counts[f] / total if total > 0 else 0
        print(f"  {f}: {field_counts[f]}/{total} ({pct:.1f}%)")

    if amount_errors:
        avg_err = sum(amount_errors) / len(amount_errors)
        within_5pct = sum(1 for e in amount_errors if e < 5.0)
        print(f"  amount_safe_to_pay within 5%: {within_5pct}/{len(amount_errors)} ({100*within_5pct/len(amount_errors):.1f}%)")
        print(f"  avg amount error: {avg_err:.1f}%")


if __name__ == "__main__":
    evaluate()
