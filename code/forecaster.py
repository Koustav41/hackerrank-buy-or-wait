"""
forecaster.py
90-day balance simulation and affordability computations.
"""

import logging
from datetime import date, timedelta
from typing import Optional, Dict, List, Tuple

from financial_state import FinancialState, ProjectedEvent, FORECAST_DAYS

logger = logging.getLogger(__name__)


def simulate_balance(
    start_balance: float,
    events: List[ProjectedEvent],
    start_date: date,
    end_date: date,
    extra_debits: Optional[List[Tuple[date, float]]] = None,
    spending_changes: Optional[Dict[str, float]] = None,  # event_id → new_amount (or -1 for stop)
) -> Tuple[Dict[date, float], float]:
    """
    Simulate daily balance from start_date to end_date.

    extra_debits: list of (date, amount) for proposed payments
    spending_changes: dict of event_id → new_amount_home (-1 means stop/0)

    Returns:
        (daily_balance_dict, minimum_balance_reached)
    """
    if spending_changes is None:
        spending_changes = {}

    # Group events by date
    events_by_date: Dict[date, List[ProjectedEvent]] = {}
    for pe in events:
        d = pe.apply_date
        if start_date <= d <= end_date:
            if d not in events_by_date:
                events_by_date[d] = []
            events_by_date[d].append(pe)

    # Group extra debits by date
    extra_by_date: Dict[date, float] = {}
    if extra_debits:
        for (d, amt) in extra_debits:
            if d not in extra_by_date:
                extra_by_date[d] = 0.0
            extra_by_date[d] += amt

    daily_balance = {}
    balance = start_balance
    min_balance_reached = balance

    current = start_date
    while current <= end_date:
        # Apply scheduled events
        if current in events_by_date:
            for pe in events_by_date[current]:
                amount = pe.amount_home
                # Apply spending change if any
                if pe.event_id in spending_changes:
                    new_amount = spending_changes[pe.event_id]
                    amount = 0.0 if new_amount < 0 else new_amount

                if pe.direction == "credit":
                    balance += amount
                elif pe.direction == "debit":
                    balance -= amount

        # Apply extra debits (payments)
        if current in extra_by_date:
            balance -= extra_by_date[current]

        daily_balance[current] = balance
        if balance < min_balance_reached:
            min_balance_reached = balance

        current += timedelta(days=1)

    return daily_balance, min_balance_reached


def is_safe(
    min_balance_reached: float,
    required_min_balance: float,
) -> bool:
    """Check if minimum balance is maintained throughout the simulation."""
    return min_balance_reached >= required_min_balance - 0.01  # small float tolerance


def compute_amount_safe_today(
    fs: FinancialState,
    requested_amount: float,
) -> float:
    """
    Binary search for the maximum amount X in [0, requested_amount] that can be
    paid on request_date while keeping balance >= min_balance for ALL 90 days.

    Algorithm:
      lo=0, hi=requested_amount
      For each candidate X: simulate 90-day window with debit of X on request_date.
      If balance stays >= min_balance throughout, X is safe; try higher.
      Otherwise try lower.
    Returns the floor of the safe amount, rounded to 2 decimal places.
    """
    end_date = fs.request_date + timedelta(days=FORECAST_DAYS)

    def _is_safe_to_pay(x: float) -> bool:
        """Return True if paying x today keeps balance >= min_balance for 90 days."""
        if x <= 0:
            # Check base case: even without payment, are we safe?
            _, min_bal = simulate_balance(
                start_balance=fs.effective_balance,
                events=fs.future_events,
                start_date=fs.request_date,
                end_date=end_date,
            )
            return is_safe(min_bal, fs.min_balance)
        _, min_bal = simulate_balance(
            start_balance=fs.effective_balance,
            events=fs.future_events,
            start_date=fs.request_date,
            end_date=end_date,
            extra_debits=[(fs.request_date, x)],
        )
        return is_safe(min_bal, fs.min_balance)

    # Quick upper bound: can't pay more than (balance - min_balance) immediately
    immediate_max = fs.effective_balance - fs.min_balance
    if immediate_max <= 0:
        return 0.0

    # If even paying 0 leaves us unsafe over 90 days, return 0
    if not _is_safe_to_pay(0.0):
        return 0.0

    # Binary search in [0, min(requested_amount, immediate_max)]
    lo = 0.0
    hi = min(requested_amount, immediate_max)

    # If paying hi is already safe, try to push all the way to requested_amount
    if _is_safe_to_pay(hi) and hi < requested_amount:
        if _is_safe_to_pay(requested_amount):
            return round(requested_amount, 2)
        # Otherwise binary search between hi and requested_amount
        lo = hi
        hi = requested_amount

    for _ in range(60):
        mid = (lo + hi) / 2
        if _is_safe_to_pay(mid):
            lo = mid
        else:
            hi = mid
        if hi - lo < 0.01:
            break

    return round(max(0.0, min(lo, requested_amount)), 2)


def compute_earliest_full_payment_date(
    fs: FinancialState,
    requested_amount: float,
) -> Optional[date]:
    """
    Find the first date D from request_date onwards where paying requested_amount
    on D keeps balance >= min_balance for the next 90 days from D.
    Returns None if not safe within 90 days from request_date.
    """
    end_search = fs.request_date + timedelta(days=FORECAST_DAYS)

    d = fs.request_date
    while d <= end_search:
        # For paying on date d, simulate from d for 90 days
        sim_end = d + timedelta(days=FORECAST_DAYS)
        # Get balance at date d (before the payment)
        balance_at_d = fs.daily_balance.get(d, fs.effective_balance)
        # Add back the amount that would be applied by the regular daily_balance at d
        # (We need to re-simulate from d's actual balance)
        # Use effective_balance and replay events from request_date to d-1 to get balance at d
        balance_before_d = fs.effective_balance
        for ev in fs.future_events:
            if fs.request_date <= ev.apply_date < d:
                if ev.direction == "credit":
                    balance_before_d += ev.amount_home
                elif ev.direction == "debit":
                    balance_before_d -= ev.amount_home

        # Now simulate from d paying requested_amount
        _, min_bal = simulate_balance(
            start_balance=balance_before_d,
            events=fs.future_events,
            start_date=d,
            end_date=sim_end,
            extra_debits=[(d, requested_amount)],
        )

        if is_safe(min_bal, fs.min_balance):
            return d

        d += timedelta(days=1)

    return None


def compute_earliest_full_payment_with_changes(
    fs: FinancialState,
    requested_amount: float,
    spending_changes: Dict[str, float],
) -> Optional[date]:
    """
    Find earliest date for full payment with spending changes applied.
    """
    end_search = fs.request_date + timedelta(days=FORECAST_DAYS)

    d = fs.request_date
    while d <= end_search:
        sim_end = d + timedelta(days=FORECAST_DAYS)

        balance_before_d = fs.effective_balance
        for ev in fs.future_events:
            if fs.request_date <= ev.apply_date < d:
                amount = ev.amount_home
                if ev.event_id in spending_changes:
                    new_amt = spending_changes[ev.event_id]
                    amount = max(0.0, new_amt) if new_amt >= 0 else 0.0
                if ev.direction == "credit":
                    balance_before_d += amount
                elif ev.direction == "debit":
                    balance_before_d -= amount

        _, min_bal = simulate_balance(
            start_balance=balance_before_d,
            events=fs.future_events,
            start_date=d,
            end_date=sim_end,
            extra_debits=[(d, requested_amount)],
            spending_changes=spending_changes,
        )

        if is_safe(min_bal, fs.min_balance):
            return d

        d += timedelta(days=1)

    return None


def simulate_installments(
    fs: FinancialState,
    payment_dates_amounts: List[Tuple[date, float]],
) -> bool:
    """
    Check if a series of installment payments is safe throughout the 90-day window.
    Returns True if all payments keep balance >= min_balance.
    """
    if not payment_dates_amounts:
        return False

    last_payment_date = payment_dates_amounts[-1][0]
    end_date = max(fs.request_date + timedelta(days=FORECAST_DAYS), last_payment_date)

    _, min_bal = simulate_balance(
        start_balance=fs.effective_balance,
        events=fs.future_events,
        start_date=fs.request_date,
        end_date=end_date,
        extra_debits=payment_dates_amounts,
    )

    return is_safe(min_bal, fs.min_balance)


def simulate_installments_with_changes(
    fs: FinancialState,
    payment_dates_amounts: List[Tuple[date, float]],
    spending_changes: Dict[str, float],
) -> bool:
    """Check installments with spending changes applied."""
    if not payment_dates_amounts:
        return False

    last_payment_date = payment_dates_amounts[-1][0]
    end_date = max(fs.request_date + timedelta(days=FORECAST_DAYS), last_payment_date)

    _, min_bal = simulate_balance(
        start_balance=fs.effective_balance,
        events=fs.future_events,
        start_date=fs.request_date,
        end_date=end_date,
        extra_debits=payment_dates_amounts,
        spending_changes=spending_changes,
    )

    return is_safe(min_bal, fs.min_balance)
