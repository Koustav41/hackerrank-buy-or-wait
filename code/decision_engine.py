"""
decision_engine.py
Core decision logic for the Buy or Wait? challenge.

Priority order (from problem spec):
1. affordable_now + full_payment (if safe today, user accepts full_payment)
2. affordable_with_plan + installments (within max_installment_months)
3. affordable_with_plan + partial_payment (if allows_partial and user accepts it)
4. affordable_with_plan + full_payment/installments with spending_changes
5. affordable_later + wait (earliest full date <= desired_completion)
6. not_affordable + not_recommended (fallback)

Ranking when multiple plans are safe:
1. Complete full request by desired_completion_date
2. Require no spending changes
3. Minimize total amount paid
4. Start payment earlier
5. Use fewer payments
6. Use lowest payment_option_id as tiebreaker
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional, List, Tuple, Dict

from data_loader import Request, FinancialProfile, PaymentOption
from financial_state import FinancialState, ProjectedEvent
from forecaster import (
    compute_amount_safe_today,
    compute_earliest_full_payment_date,
    compute_earliest_full_payment_with_changes,
    simulate_installments,
    simulate_installments_with_changes,
    simulate_balance,
    is_safe,
    FORECAST_DAYS,
)

logger = logging.getLogger(__name__)


@dataclass
class Decision:
    request_id: str
    amount_safe_to_pay: float
    affordability_status: str  # affordable_now|affordable_with_plan|affordable_later|not_affordable
    recommended_payment_method: str  # full_payment|partial_payment|installments|wait|not_recommended
    payment_plan: str  # "YYYY-MM-DD:amount|..." or "none"
    earliest_date_for_full_payment: str  # "YYYY-MM-DD" or ""
    spending_changes_needed: str  # "none" or "stop:eid|reduce_to:eid:amt|..."
    decision_explanation: str


def _build_installment_schedule(option: PaymentOption) -> List[Tuple[date, float]]:
    """Build the list of (date, amount) payments for an installment option."""
    if not option.first_payment_date or option.number_of_payments < 1:
        return []

    payments = []
    freq = option.payment_frequency_days or 30

    for i in range(option.number_of_payments):
        payment_date = option.first_payment_date + timedelta(days=freq * i)
        payments.append((payment_date, option.payment_amount))

    return payments


def _format_payment_plan(payments: List[Tuple[date, float]]) -> str:
    """Format a list of (date, amount) payments as the required string."""
    parts = []
    for d, amt in payments:
        if amt == int(amt):
            parts.append(f"{d}:{int(amt)}")
        else:
            # Round to 2 decimal places
            rounded = round(amt, 2)
            parts.append(f"{d}:{rounded:.2f}")
    return "|".join(parts)


def _format_amount(amount: float) -> str:
    """Format amount: integer if whole number, else 2 decimal places."""
    if amount == int(amount):
        return str(int(amount))
    return f"{round(amount, 2):.2f}"


def _compute_spending_change_savings(
    flexible_events: List[ProjectedEvent],
    request_date: date,
    end_date: date,
) -> List[Tuple[ProjectedEvent, float, str]]:
    """
    Return list of (event, savings_amount, change_type) for each flexible event,
    sorted by savings descending.
    change_type: 'stop' or 'reduce'
    """
    savings = []
    seen_events = set()

    for pe in flexible_events:
        if pe.original_event is None and not pe.is_recurring:
            continue
        # Get base event_id (for recurring events, use the original)
        base_event_id = pe.original_event.event_id if pe.original_event else pe.event_id

        if base_event_id in seen_events:
            continue
        seen_events.add(base_event_id)

        # Count how many times this event occurs in the window
        occurrences = sum(
            1 for ev in flexible_events
            if (ev.original_event.event_id if ev.original_event else ev.event_id) == base_event_id
            and request_date <= ev.apply_date <= end_date
        )

        if pe.flexibility in ("stoppable", "reducible_or_stoppable"):
            total_savings = pe.amount_home * occurrences
            savings.append((pe, total_savings, "stop"))
        elif pe.flexibility in ("reducible",):
            if pe.minimum_allowed_amount_home is not None:
                reduction_per = pe.amount_home - pe.minimum_allowed_amount_home
                total_savings = max(0, reduction_per * occurrences)
                if total_savings > 0:
                    savings.append((pe, total_savings, "reduce"))
            else:
                # Reduce by 50%
                reduction_per = pe.amount_home * 0.5
                total_savings = reduction_per * occurrences
                savings.append((pe, total_savings, "reduce"))

    # Sort by savings descending
    savings.sort(key=lambda x: x[1], reverse=True)
    return savings


def _apply_spending_changes_to_events(
    changes_list: List[Tuple[ProjectedEvent, float, str]],
    flexible_events: List[ProjectedEvent],
) -> Dict[str, float]:
    """
    Build spending_changes dict: event_id -> new_amount (-1 for stop)
    for all occurrences of the selected events.
    """
    changes = {}
    # Use list of tuples (base_id, change_type, rep_pe) - avoid set with unhashable dataclass
    selected_base_ids = []
    seen_base_ids = set()

    for (pe, savings, change_type) in changes_list:
        base_id = pe.original_event.event_id if pe.original_event else pe.event_id
        if base_id not in seen_base_ids:
            seen_base_ids.add(base_id)
            selected_base_ids.append((base_id, change_type, pe))

    # Apply to all occurrences
    for (base_id, change_type, rep_pe) in selected_base_ids:
        for ev in flexible_events:
            ev_base_id = ev.original_event.event_id if ev.original_event else ev.event_id
            if ev_base_id == base_id:
                if change_type == "stop":
                    changes[ev.event_id] = -1
                else:
                    # Reduce
                    if rep_pe.minimum_allowed_amount_home is not None:
                        changes[ev.event_id] = rep_pe.minimum_allowed_amount_home
                    else:
                        changes[ev.event_id] = rep_pe.amount_home * 0.5

    return changes


def _format_spending_changes(
    changes_list: List[Tuple[ProjectedEvent, float, str]],
) -> str:
    """Format spending_changes_needed string."""
    parts = []
    seen_bases = set()

    for (pe, savings, change_type) in changes_list:
        base_id = pe.original_event.event_id if pe.original_event else pe.event_id
        if base_id in seen_bases:
            continue
        seen_bases.add(base_id)

        if change_type == "stop":
            parts.append(f"stop:{base_id}")
        else:
            if pe.minimum_allowed_amount_home is not None:
                new_amt = pe.minimum_allowed_amount_home
                new_amt_str = _format_amount(new_amt)
                parts.append(f"reduce_to:{base_id}:{new_amt_str}")
            else:
                new_amt = pe.amount_home * 0.5
                new_amt_str = _format_amount(new_amt)
                parts.append(f"reduce_to:{base_id}:{new_amt_str}")

    return "|".join(parts) if parts else "none"


def make_decision(
    request: Request,
    profile: FinancialProfile,
    fs: FinancialState,
    payment_options: List[PaymentOption],
) -> Decision:
    """
    Make the affordability decision for a request.
    """
    request_id = request.request_id
    requested_amount = request.requested_amount
    request_date = request.request_date
    desired_completion = request.desired_completion_date
    allows_partial = request.allows_partial_payment
    accepted_methods = set(profile.payment_methods_user_will_consider)

    # ---- Compute core metrics ----
    amount_safe_today = compute_amount_safe_today(fs, requested_amount)
    amount_safe_today = max(0.0, min(amount_safe_today, requested_amount))

    earliest_full_date = compute_earliest_full_payment_date(fs, requested_amount)

    # ---- Filter payment options for this request ----
    req_options = sorted(
        [o for o in payment_options if o.request_id == request_id],
        key=lambda x: x.payment_option_id
    )
    full_payment_options = [o for o in req_options if o.payment_method == "full_payment"]
    installment_options = [o for o in req_options if o.payment_method == "installments"]

    # ---- PRIORITY 1: affordable_now + full_payment ----
    can_full_payment = "full_payment" in accepted_methods
    full_safe_today = amount_safe_today >= requested_amount - 0.011  # 1.1 cent tolerance

    if can_full_payment and full_safe_today:
        plan_date = request_date
        if full_payment_options:
            plan_date = full_payment_options[0].first_payment_date or request_date

        return Decision(
            request_id=request_id,
            amount_safe_to_pay=requested_amount,
            affordability_status="affordable_now",
            recommended_payment_method="full_payment",
            payment_plan=_format_payment_plan([(plan_date, requested_amount)]),
            earliest_date_for_full_payment=str(request_date),
            spending_changes_needed="none",
            decision_explanation=_explain_affordable_now(
                profile.home_currency, requested_amount, profile.minimum_balance_to_keep
            ),
        )

    # ---- PRIORITY 2 & 3: affordable_with_plan (installments & partial_payment without changes) ----
    candidates_no_changes = []

    # Check installments
    can_installments = "installments" in accepted_methods
    max_months = profile.max_installment_months  # None = no installments

    if can_installments and max_months is not None:
        for option in installment_options:
            n = option.number_of_payments
            freq = option.payment_frequency_days or 30
            plan_months = (n * freq) / 30.0

            if plan_months > max_months:
                continue

            if option.first_payment_date is None:
                continue

            schedule = _build_installment_schedule(option)
            if not schedule or schedule[-1][0] > desired_completion:
                continue

            if simulate_installments(fs, schedule):
                dec = Decision(
                    request_id=request_id,
                    amount_safe_to_pay=amount_safe_today,
                    affordability_status="affordable_with_plan",
                    recommended_payment_method="installments",
                    payment_plan=_format_payment_plan(schedule),
                    earliest_date_for_full_payment=str(earliest_full_date) if earliest_full_date else "",
                    spending_changes_needed="none",
                    decision_explanation=_explain_installments(
                        profile.home_currency, option, n, requested_amount, profile.minimum_balance_to_keep
                    ),
                )
                total_cost = option.total_payable_amount if option.total_payable_amount else (option.payment_amount * n)
                candidates_no_changes.append((total_cost, schedule[0][0], n, option.payment_option_id, dec))

    # Check partial payment
    can_partial = "partial_payment" in accepted_methods
    partial_eligible = (
        allows_partial
        and can_partial
        and amount_safe_today > 0.011
        and amount_safe_today < requested_amount - 0.011  # must be meaningfully less than requested
        and earliest_full_date is not None
        and earliest_full_date <= desired_completion
    )

    if partial_eligible:
        remainder = requested_amount - amount_safe_today
        schedule = [
            (request_date, amount_safe_today),
            (earliest_full_date, remainder),
        ]
        dec = Decision(
            request_id=request_id,
            amount_safe_to_pay=amount_safe_today,
            affordability_status="affordable_with_plan",
            recommended_payment_method="partial_payment",
            payment_plan=_format_payment_plan(schedule),
            earliest_date_for_full_payment=str(earliest_full_date),
            spending_changes_needed="none",
            decision_explanation=_explain_partial(
                profile.home_currency, amount_safe_today, remainder,
                request_date, earliest_full_date, profile.minimum_balance_to_keep
            ),
        )
        total_cost = requested_amount
        candidates_no_changes.append((total_cost, request_date, 2, "payment_option_00", dec))

    if candidates_no_changes:
        candidates_no_changes.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
        return candidates_no_changes[0][4]

    # ---- PRIORITY 4: affordable_later + wait ----
    # Check "wait" BEFORE suggesting spending changes — waiting is always preferable
    # to asking the user to alter spending when income will naturally cover the purchase.
    can_wait = "full_payment" in accepted_methods
    wait_eligible = (
        can_wait
        and earliest_full_date is not None
        and earliest_full_date <= desired_completion
    )

    if wait_eligible:
        return Decision(
            request_id=request_id,
            amount_safe_to_pay=amount_safe_today,
            affordability_status="affordable_later",
            recommended_payment_method="wait",
            payment_plan=_format_payment_plan([(earliest_full_date, requested_amount)]),
            earliest_date_for_full_payment=str(earliest_full_date),
            spending_changes_needed="none",
            decision_explanation=_explain_wait(
                profile.home_currency, requested_amount,
                earliest_full_date, profile.minimum_balance_to_keep
            ),
        )

    # ---- PRIORITY 5: spending changes to unlock full_payment or installments ----
    end_date = request_date + timedelta(days=FORECAST_DAYS)
    flexible_sorted = _compute_spending_change_savings(
        fs.flexible_events, request_date, end_date
    )

    if flexible_sorted:
        # Try combinations of up to 3 spending changes
        best_with_changes = None
        for n_changes in range(1, min(4, len(flexible_sorted) + 1)):
            # Try the top n_changes items
            selected_changes = flexible_sorted[:n_changes]
            # Ensure stop and reduce_to target different events
            seen_base_ids = set()
            valid_combo = True
            for pe, savings, ctype in selected_changes:
                base_id = pe.original_event.event_id if pe.original_event else pe.event_id
                if base_id in seen_base_ids:
                    valid_combo = False
                    break
                seen_base_ids.add(base_id)

            if not valid_combo:
                continue

            changes_dict = _apply_spending_changes_to_events(selected_changes, fs.flexible_events)

            # Check if full_payment is now possible
            if can_full_payment:
                # Compute amount safe with changes
                # Recompute: simulate with changes what min balance would be
                _, min_bal_with_changes = simulate_balance(
                    start_balance=fs.effective_balance,
                    events=fs.future_events,
                    start_date=request_date,
                    end_date=end_date,
                    extra_debits=[(request_date, requested_amount)],
                    spending_changes=changes_dict,
                )
                if is_safe(min_bal_with_changes, fs.min_balance):
                    spending_changes_str = _format_spending_changes(selected_changes)
                    earliest_with_changes = compute_earliest_full_payment_with_changes(
                        fs, requested_amount, changes_dict
                    )
                    best_with_changes = Decision(
                        request_id=request_id,
                        amount_safe_to_pay=amount_safe_today,
                        affordability_status="affordable_with_plan",
                        recommended_payment_method="full_payment",
                        payment_plan=_format_payment_plan([(request_date, requested_amount)]),
                        earliest_date_for_full_payment=str(earliest_with_changes or earliest_full_date or request_date),
                        spending_changes_needed=spending_changes_str,
                        decision_explanation=_explain_spending_changes(
                            profile.home_currency, requested_amount,
                            profile.minimum_balance_to_keep, selected_changes
                        ),
                    )
                    break

            # Check if installments are now possible
            if can_installments and max_months is not None and best_with_changes is None:
                for option in installment_options:
                    n = option.number_of_payments
                    freq = option.payment_frequency_days or 30
                    if (n * freq / 30.0) > max_months:
                        continue
                    if option.first_payment_date is None:
                        continue
                    schedule = _build_installment_schedule(option)
                    if not schedule or schedule[-1][0] > desired_completion:
                        continue
                    if simulate_installments_with_changes(fs, schedule, changes_dict):
                        spending_changes_str = _format_spending_changes(selected_changes)
                        best_with_changes = Decision(
                            request_id=request_id,
                            amount_safe_to_pay=amount_safe_today,
                            affordability_status="affordable_with_plan",
                            recommended_payment_method="installments",
                            payment_plan=_format_payment_plan(schedule),
                            earliest_date_for_full_payment=str(earliest_full_date) if earliest_full_date else "",
                            spending_changes_needed=spending_changes_str,
                            decision_explanation=_explain_installments_with_changes(
                                profile.home_currency, option, n, requested_amount,
                                profile.minimum_balance_to_keep, selected_changes
                            ),
                        )
                        break

            if best_with_changes:
                break

        if best_with_changes:
            return best_with_changes

    # ---- PRIORITY 6: not_affordable + not_recommended ----
    return Decision(
        request_id=request_id,
        amount_safe_to_pay=amount_safe_today,
        affordability_status="not_affordable",
        recommended_payment_method="not_recommended",
        payment_plan="none",
        earliest_date_for_full_payment="",
        spending_changes_needed="none",
        decision_explanation=_explain_not_affordable(
            profile.home_currency, requested_amount,
            desired_completion, profile.minimum_balance_to_keep
        ),
    )


# ---- Explanation helpers ----

def _explain_affordable_now(currency: str, amount: float, min_bal: float) -> str:
    amt_str = _format_amount(amount)
    min_str = _format_amount(min_bal)
    return (
        f"Pay {currency} {amt_str} today. "
        f"This leaves at least {currency} {min_str} available over the next 90 days."
    )


def _explain_installments(
    currency: str, option: PaymentOption, n: int,
    total: float, min_bal: float
) -> str:
    amt_str = _format_amount(option.payment_amount)
    min_str = _format_amount(min_bal)
    first_date = option.first_payment_date
    return (
        f"Use {n} installments of {currency} {amt_str}, "
        f"starting {first_date}. "
        f"This leaves at least {currency} {min_str} available."
    )


def _explain_partial(
    currency: str, first_amt: float, second_amt: float,
    first_date: date, second_date: date, min_bal: float
) -> str:
    first_str = _format_amount(first_amt)
    second_str = _format_amount(second_amt)
    min_str = _format_amount(min_bal)
    return (
        f"Pay {currency} {first_str} today and the remaining "
        f"{currency} {second_str} on {second_date}. "
        f"This completes the full request and keeps the {currency} {min_str} minimum protected."
    )


def _explain_spending_changes(
    currency: str, amount: float, min_bal: float,
    changes: List[Tuple]
) -> str:
    amt_str = _format_amount(amount)
    min_str = _format_amount(min_bal)
    change_descs = []
    seen = set()
    for pe, savings, ctype in changes:
        base_id = pe.original_event.event_id if pe.original_event else pe.event_id
        if base_id in seen:
            continue
        seen.add(base_id)
        if ctype == "stop":
            change_descs.append(f"stop the {pe.description}")
        else:
            if pe.minimum_allowed_amount_home is not None:
                new_amt = _format_amount(pe.minimum_allowed_amount_home)
                change_descs.append(f"reduce the {pe.description} to {currency} {new_amt}")
            else:
                new_amt = _format_amount(pe.amount_home * 0.5)
                change_descs.append(f"reduce the {pe.description} to {currency} {new_amt}")
    changes_text = " and ".join(change_descs)
    if changes_text:
        changes_text = changes_text[0].upper() + changes_text[1:] + ", then pay"
    else:
        changes_text = "Pay"
    return (
        f"{changes_text} {currency} {amt_str} today. "
        f"This leaves at least {currency} {min_str} available."
    )


def _explain_installments_with_changes(
    currency: str, option: PaymentOption, n: int,
    total: float, min_bal: float, changes: List[Tuple]
) -> str:
    amt_str = _format_amount(option.payment_amount)
    min_str = _format_amount(min_bal)
    change_descs = []
    seen = set()
    for pe, savings, ctype in changes:
        base_id = pe.original_event.event_id if pe.original_event else pe.event_id
        if base_id in seen:
            continue
        seen.add(base_id)
        if ctype == "stop":
            change_descs.append(f"stop the {pe.description}")
        else:
            if pe.minimum_allowed_amount_home is not None:
                new_amt = _format_amount(pe.minimum_allowed_amount_home)
                change_descs.append(f"reduce {pe.description} to {currency} {new_amt}")
    prefix = (", ".join(change_descs) + ", then use") if change_descs else "Use"
    return (
        f"{prefix} {n} installments of {currency} {amt_str}, "
        f"starting {option.first_payment_date}. "
        f"This leaves at least {currency} {min_str} available."
    )


def _explain_wait(
    currency: str, amount: float, safe_date: date, min_bal: float
) -> str:
    amt_str = _format_amount(amount)
    min_str = _format_amount(min_bal)
    return (
        f"Pay {currency} {amt_str} in full on {safe_date}. "
        f"Paying earlier would take the balance below the {currency} {min_str} minimum."
    )


def _explain_not_affordable(
    currency: str, amount: float, deadline: date, min_bal: float
) -> str:
    amt_str = _format_amount(amount)
    min_str = _format_amount(min_bal)
    return (
        f"Do not make this payment by {deadline}. "
        f"None of the available options keeps the {currency} {min_str} minimum protected."
    )
