"""
financial_state.py
Build a user's financial state and 90-day balance projection.

Rules:
- Exclude: cancelled, failed events (no cash impact)
- Exclude: unrealized (investment valuations, not real cash)
- Pending debits: reserved immediately (reduce available balance now)
- Pending credits: do NOT count (not settled)
- Settled/Scheduled events: apply on settlement_date
- Recurring: detect from settled history + scheduled income anchors, project forward
- Blank amounts: must be supplied via image_amounts dict
- linked_event_id: terminal event state supersedes prior
- Convert all amounts to home_currency using settlement_date for FX rate
"""

import copy
import logging
import calendar
from dataclasses import dataclass, field
from datetime import date, datetime as dt, timedelta
from typing import Optional, List, Dict, Tuple

from data_loader import FinancialEvent, FinancialProfile
from currency_converter import CurrencyConverter

logger = logging.getLogger(__name__)

FORECAST_DAYS = 90


@dataclass
class ProjectedEvent:
    event_id: str
    description: str
    category: str
    direction: str  # debit / credit
    amount_home: float  # in home currency
    apply_date: date  # the date cash flow hits
    status: str
    flexibility: str
    minimum_allowed_amount_home: Optional[float]
    is_recurring: bool
    original_event: Optional[FinancialEvent] = None


@dataclass
class FinancialState:
    user_id: str
    home_currency: str
    request_date: date
    effective_balance: float  # balance after reserving pending debits
    min_balance: float
    # daily balance: dict date -> balance (from request_date to request_date+90)
    daily_balance: Dict[date, float]
    # events that will hit cash flow from request_date onward
    future_events: List[ProjectedEvent]
    # flexible events eligible for change (non-protected, stoppable/reducible)
    flexible_events: List[ProjectedEvent]
    # amount safely payable today (before any spending changes)
    amount_safe_today: float


def _detect_recurring_events(
    user_events: List[FinancialEvent],
    as_of_date: date,
    home_currency: str,
    converter: CurrencyConverter,
    salary_updates: Optional[List[dict]] = None,
    end_employment: bool = False,
    rent_increases: Optional[List[dict]] = None,
) -> List[ProjectedEvent]:
    """
    Detect recurring expense/income patterns from settled + scheduled history.
    Returns list of ProjectedEvent to add to the forecast window.

    Key improvements:
    - For income (salary): includes scheduled/confirmed future events as anchors
    - For expenses: uses settled history with minimum 2 occurrences
    - Projects forward until end of 90-day forecast window
    """
    from collections import defaultdict

    end_date = as_of_date + timedelta(days=FORECAST_DAYS)

    def _is_valid_for_pattern(e):
        if e.amount is None:
            return False
        if e.settlement_date is None:
            return False
        if e.direction not in ("debit", "credit"):
            return False
        if e.event_type in ("refund", "investment_sale", "investment_purchase", "investment_valuation"):
            return False
        if e.status in ("cancelled", "failed", "unrealized"):
            return False
        return True

    # Historical settled events before as_of_date
    historical = [
        e for e in user_events
        if e.status == "settled"
        and e.settlement_date is not None
        and e.settlement_date < as_of_date
        and _is_valid_for_pattern(e)
    ]

    # Future scheduled income events (to anchor salary projection even with only 1 settled)
    future_scheduled_income = [
        e for e in user_events
        if e.status in ("scheduled", "pending")
        and e.settlement_date is not None
        and e.settlement_date >= as_of_date
        and e.direction == "credit"
        and e.event_type == "income"
        and _is_valid_for_pattern(e)
    ]

    # Hybrid grouping:
    # Fixed bills/subscriptions -> group by description
    # Variable frequent living expenses -> group by category
    VARIABLE_CATS = {"groceries", "transport"}

    groups = defaultdict(list)
    for e in historical:
        if e.category in VARIABLE_CATS:
            key = (e.category, e.category, e.direction, e.event_type)
        else:
            key = (e.description, e.category, e.direction, e.event_type)
        groups[key].append(e)

    projected = []
    covered_dates = set()  # (category, direction, date, desc) to avoid duplicates

    def _safe_convert(amount, currency, on_date):
        try:
            return converter.convert(amount, currency, home_currency, on_date)
        except Exception:
            return None

    def _median_amount(events_list):
        amounts = []
        for e in events_list[-4:]:
            ref_date = e.settlement_date or as_of_date
            amt = _safe_convert(e.amount, e.currency, ref_date)
            if amt is not None:
                amounts.append(amt)
        if not amounts:
            return None
        amounts.sort()
        return amounts[len(amounts) // 2]

    def _add_months(sourcedate: date, months: int) -> date:
        month = sourcedate.month - 1 + months
        year = sourcedate.year + month // 12
        month = month % 12 + 1
        day = min(sourcedate.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)

    def _project_forward(rep_event, last_date, freq_type, rep_amount,
                         flexibility, min_allowed, category, direction):
        """
        Project recurring events forward from last_date.
        For biweekly: step by exactly 14 days each time.
        For monthly: use calendar-aware month arithmetic to avoid date drift.
        For weekly: step by 7 days.
        """
        events_out = []
        step = 1
        while True:
            if freq_type == "monthly":
                next_date = _add_months(last_date, step)
            elif freq_type == "biweekly":
                # Use step * 14 from last settled anchor to stay aligned
                next_date = last_date + timedelta(days=14 * step)
            elif freq_type == "weekly":
                next_date = last_date + timedelta(days=7 * step)
            else:
                next_date = last_date + timedelta(days=30 * step)

            if next_date > end_date:
                break

            key = (category, direction, next_date, rep_event.description)
            if next_date >= as_of_date and key not in covered_dates:
                covered_dates.add(key)
                events_out.append(ProjectedEvent(
                    event_id=f"{rep_event.event_id}_proj_{next_date}",
                    description=rep_event.description,
                    category=category,
                    direction=direction,
                    amount_home=rep_amount,
                    apply_date=next_date,
                    status="scheduled_recurring",
                    flexibility=flexibility,
                    minimum_allowed_amount_home=min_allowed,
                    is_recurring=True,
                    original_event=rep_event,
                ))
            step += 1
        return events_out

    # Check if the overall most recent historical income event was a terminal final payroll
    income_historical = [e for e in historical if e.direction == "credit" and e.event_type == "income"]
    has_final_payroll = False
    if income_historical:
        latest_income = sorted(income_historical, key=lambda x: x.settlement_date)[-1]
        import re
        if re.search(r'\b(final|last)\b', latest_income.description, re.I):
            has_final_payroll = True

    # ---------- Process historical event groups ----------
    for (desc, category, direction, etype), events in groups.items():
        events_sorted = sorted(events, key=lambda x: x.settlement_date)

        # Find a matching future scheduled income anchor (if applicable)
        future_anchor = None
        if direction == "credit" and etype == "income":
            matching = [
                fe for fe in future_scheduled_income
                if fe.category == category and fe.event_type == etype
            ]
            if matching:
                future_anchor = sorted(matching, key=lambda x: x.settlement_date)[0]

            if has_final_payroll and not future_anchor:
                continue  # Employment ended with final payroll

        # Minimum occurrences required:
        # - 1 settled + future anchor = OK for income
        # - 2 settled for expenses
        min_required = 1 if (future_anchor is not None and direction == "credit") else 2

        # Filter outlier events by amount (remove one-off bonuses etc.)
        # Use median amount from non-outliers to filter
        all_amounts = []
        for e in events_sorted:
            try:
                ref = e.settlement_date or as_of_date
                a = converter.convert(e.amount, e.currency, home_currency, ref)
                all_amounts.append(a)
            except Exception:
                all_amounts.append(0)
        if all_amounts:
            sorted_amts = sorted(all_amounts)
            median_amt = sorted_amts[len(sorted_amts) // 2]
            if median_amt > 0:
                # Filter out events whose amount is < 50% or > 200% of median
                filtered_events = [
                    e for e, a in zip(events_sorted, all_amounts)
                    if median_amt * 0.5 <= a <= median_amt * 2.0
                ]
                if len(filtered_events) >= min_required:
                    events_sorted = filtered_events
                # Re-sort after filter
                events_sorted = sorted(events_sorted, key=lambda x: x.settlement_date)

        # Merge for interval analysis
        all_for_interval = events_sorted[:]
        if future_anchor:
            all_for_interval = sorted(events_sorted + [future_anchor], key=lambda x: x.settlement_date)

        if len(events_sorted) < min_required:
            continue

        # Build intervals
        intervals = []
        for i in range(1, len(all_for_interval)):
            delta = (all_for_interval[i].settlement_date - all_for_interval[i - 1].settlement_date).days
            if delta > 0:
                intervals.append(delta)

        if not intervals:
            continue

        avg_interval = sum(intervals) / len(intervals)

        # Is this a recognized recurring pattern?
        is_weekly = 5 <= avg_interval <= 9
        is_biweekly = 10 <= avg_interval <= 18
        is_monthly = 25 <= avg_interval <= 35

        if not (is_weekly or is_biweekly or is_monthly):
            continue

        # Check consistency (stddev < 45% of mean) when multiple intervals
        if len(intervals) >= 2:
            variance = sum((x - avg_interval) ** 2 for x in intervals) / len(intervals)
            std = variance ** 0.5
            if std > 0.45 * avg_interval:
                continue

        # Check recency: the last event in history must be active (not dormant/ended months ago)
        last_anchor = all_for_interval[-1]
        days_since_last = (as_of_date - last_anchor.settlement_date).days
        max_dormancy = 16 if is_weekly else (28 if is_biweekly else 45)
        if days_since_last > max_dormancy and not future_anchor:
            continue

        freq_type = "weekly" if is_weekly else ("biweekly" if is_biweekly else "monthly")

        # Representative amount
        if direction == "credit" and etype == "income":
            if end_employment:
                if salary_updates:
                    rep_amount = _safe_convert(salary_updates[0]["new_amount"], home_currency, as_of_date)
                else:
                    continue  # No regular salary payments after employment ended
            elif salary_updates:
                rep_amount = _safe_convert(salary_updates[0]["new_amount"], home_currency, as_of_date)
            elif future_anchor:
                rep_amount = _safe_convert(
                    future_anchor.amount, future_anchor.currency, future_anchor.settlement_date
                )
                if rep_amount is None:
                    rep_amount = _median_amount(events_sorted)
            else:
                rep_amount = _median_amount(events_sorted)
        elif category == "rent" and rent_increases:
            rep_amount = _median_amount(events_sorted)
            if rep_amount is not None:
                pct = rent_increases[0].get("percentage_change", 0.0)
                rep_amount = rep_amount * (1.0 + pct / 100.0)
        elif future_anchor:
            rep_amount = _safe_convert(
                future_anchor.amount, future_anchor.currency, future_anchor.settlement_date
            )
            if rep_amount is None:
                rep_amount = _median_amount(events_sorted)
        else:
            rep_amount = _median_amount(events_sorted)

        if rep_amount is None:
            continue

        # Flexibility (from most recent historical event)
        flexibility = "fixed"
        for e in reversed(events_sorted):
            if e.flexibility:
                flexibility = e.flexibility
                break

        # Minimum allowed amount
        min_allowed = None
        for e in reversed(events_sorted):
            if e.minimum_allowed_amount is not None:
                ref_date = e.settlement_date or as_of_date
                min_allowed = _safe_convert(e.minimum_allowed_amount, e.currency, ref_date)
                break

        # Project from the LAST event (may be future_anchor)
        rep_event_for_id = events_sorted[-1]
        last_anchor = all_for_interval[-1]
        last_date = last_anchor.settlement_date

        new_events = _project_forward(
            rep_event_for_id, last_date, freq_type, rep_amount,
            flexibility, min_allowed, category, direction
        )
        projected.extend(new_events)

    # ---------- Handle future scheduled income with NO settled history ----------
    handled_income_keys = set((k[1], k[2], k[3]) for k in groups.keys())
    for fe in future_scheduled_income:
        key = (fe.category, fe.direction, fe.event_type)
        if key in handled_income_keys:
            continue  # Already handled above

        # This is a scheduled income with no prior settled history
        # Project forward monthly from its date (assume monthly salary)
        rep_amount = _safe_convert(fe.amount, fe.currency, fe.settlement_date)
        if rep_amount is None:
            continue

        # Add the scheduled event itself first
        event_date_key = (fe.category, fe.direction, fe.settlement_date, fe.description)
        if fe.settlement_date >= as_of_date and event_date_key not in covered_dates:
            covered_dates.add(event_date_key)
            projected.append(ProjectedEvent(
                event_id=fe.event_id + "_anchor",
                description=fe.description,
                category=fe.category,
                direction=fe.direction,
                amount_home=rep_amount,
                apply_date=fe.settlement_date,
                status="scheduled",
                flexibility=fe.flexibility or "fixed",
                minimum_allowed_amount_home=None,
                is_recurring=True,
                original_event=fe,
            ))
        # Project forward from the scheduled date
        new_events = _project_forward(
            fe, fe.settlement_date, "monthly", rep_amount,
            "fixed", None, fe.category, fe.direction
        )
        projected.extend(new_events)

    return projected


def build_financial_state(
    user_id: str,
    request_date: date,
    profile: FinancialProfile,
    user_events: List[FinancialEvent],
    converter: CurrencyConverter,
    image_amounts: Dict[str, Tuple[Optional[float], Optional[str]]],
    message_amendments: List[dict],
) -> FinancialState:
    """
    Build the financial state for a user as of request_date.

    image_amounts: dict event_id -> (amount, currency) for blank-amount events
    message_amendments: list of parsed message dicts with amendment info
    """
    home_currency = profile.home_currency
    start_balance = profile.current_available_balance
    min_balance = profile.minimum_balance_to_keep

    # ---- Step 1: Apply message amendments to events ----
    event_amendments = {}
    salary_updates = []
    rent_increases = []
    end_employment = False

    for amendment in message_amendments:
        atype = amendment.get("amendment_type", "irrelevant")
        target_event_id = amendment.get("target_event_id")
        new_amount = amendment.get("new_amount")
        new_date = amendment.get("new_date")
        related_event_id = amendment.get("related_event_id", "")

        if atype == "irrelevant":
            continue

        if atype == "salary_update" and new_amount:
            salary_updates.append({
                "new_amount": new_amount,
                "related_event_id": related_event_id,
                "sent_at": amendment.get("sent_at", ""),
                "source_type": amendment.get("source_type", ""),
                "message_text": amendment.get("message_text", ""),
            })
        elif atype == "rent_increase":
            rent_increases.append(amendment)
        elif atype == "end_employment":
            end_employment = True

        event_id = target_event_id or related_event_id
        if event_id:
            event_amendments[event_id] = {
                "type": atype,
                "new_amount": new_amount,
                "new_date": new_date,
            }

    # ---- Step 2: Fill in blank amounts from images ----
    events_modified = []
    for ev in user_events:
        if ev.amount is None:
            img_result = image_amounts.get(ev.event_id)
            if img_result and img_result[0] is not None:
                ev_copy = copy.copy(ev)
                ev_copy.amount = img_result[0]
                if img_result[1]:
                    ev_copy.currency = img_result[1]
                events_modified.append(ev_copy)
                logger.debug(f"Filled blank amount for {ev.event_id}: {ev_copy.amount} {ev_copy.currency}")
            else:
                logger.warning(f"Cannot resolve blank amount for {ev.event_id} -- skipping event")
                # Skip events with unresolved blank amounts
        else:
            events_modified.append(ev)

    # ---- Step 3: Apply message amendments ----
    events_after_amendments = []
    for ev in events_modified:
        amend = event_amendments.get(ev.event_id)
        if amend:
            atype = amend["type"]
            if atype == "cancel":
                continue  # Drop
            elif atype == "confirm" and ev.status == "pending":
                ev = copy.copy(ev)
                ev.status = "settled"
            elif atype == "amend_amount" and amend["new_amount"]:
                ev = copy.copy(ev)
                ev.amount = amend["new_amount"]
            elif atype == "delay" and amend["new_date"]:
                ev = copy.copy(ev)
                try:
                    ev.settlement_date = dt.strptime(amend["new_date"], "%Y-%m-%d").date()
                    ev.event_date = ev.settlement_date
                except Exception:
                    pass
        events_after_amendments.append(ev)

    # ---- Step 4: De-duplicate via linked_event_id ----
    # If event B has linked_event_id = event A, then B supersedes A
    superseded_ids = set()
    for ev in events_after_amendments:
        if ev.linked_event_id:
            superseded_ids.add(ev.linked_event_id)

    events_deduped = [
        ev for ev in events_after_amendments
        if ev.event_id not in superseded_ids
    ]

    # ---- Step 5: Filter by status ----
    valid_statuses = {"settled", "pending", "scheduled"}
    events_valid = [
        ev for ev in events_deduped
        if ev.status in valid_statuses
        and ev.direction != "non_cash"
    ]

    # ---- Step 6: Reserve pending debits immediately ----
    effective_balance = start_balance
    for ev in events_valid:
        if ev.status == "pending" and ev.direction == "debit" and ev.amount is not None:
            try:
                ref_date = ev.settlement_date or request_date
                amt_home = converter.convert(ev.amount, ev.currency, home_currency, ref_date)
                effective_balance -= amt_home
            except Exception as e:
                logger.warning(f"FX conversion failed for pending debit {ev.event_id}: {e}")

    # ---- Step 7: Detect recurring patterns and project forward ----
    recurring_projected = _detect_recurring_events(
        user_events, request_date, home_currency, converter,
        salary_updates=salary_updates,
        end_employment=end_employment,
        rent_increases=rent_increases,
    )

    # ---- Step 8: Build future events list (settlement_date >= request_date) ----
    future_events = []

    # Track scheduled income event IDs already in recurring_projected to avoid duplicates
    already_covered_scheduled = set()
    for rpe in recurring_projected:
        if rpe.original_event and rpe.status == "scheduled":
            already_covered_scheduled.add(rpe.original_event.event_id)

    # From actual events (settled/scheduled)
    for ev in events_valid:
        if ev.status == "pending":
            continue  # Already reserved above

        settle_date = ev.settlement_date
        if settle_date is None:
            settle_date = ev.event_date
        if settle_date is None:
            continue

        if settle_date < request_date:
            continue  # Historical

        if settle_date > request_date + timedelta(days=FORECAST_DAYS):
            continue  # Beyond forecast window

        if ev.amount is None:
            continue  # Unresolved blank

        try:
            amt_home = converter.convert(ev.amount, ev.currency, home_currency, settle_date)
        except Exception as e:
            logger.warning(f"FX conversion failed for {ev.event_id}: {e}")
            continue

        # Apply salary updates from messages
        if ev.event_type == "income" and salary_updates:
            for su in sorted(salary_updates, key=lambda x: x["sent_at"], reverse=True):
                if (not su.get("related_event_id")) or su.get("related_event_id") == ev.linked_event_id:
                    try:
                        new_amt = su["new_amount"]
                        amt_home = converter.convert(new_amt, home_currency, home_currency, settle_date)
                    except Exception:
                        pass
                    break

        min_allowed_home = None
        if ev.minimum_allowed_amount is not None:
            try:
                min_allowed_home = converter.convert(
                    ev.minimum_allowed_amount, ev.currency, home_currency, settle_date
                )
            except Exception:
                pass

        future_events.append(ProjectedEvent(
            event_id=ev.event_id,
            description=ev.description,
            category=ev.category,
            direction=ev.direction,
            amount_home=amt_home,
            apply_date=settle_date,
            status=ev.status,
            flexibility=ev.flexibility or "fixed",
            minimum_allowed_amount_home=min_allowed_home,
            is_recurring=False,
            original_event=ev,
        ))

    # Add recurring projected events (only if not already covered by actual events)
    existing_event_dates = set()
    for pe in future_events:
        existing_event_dates.add((pe.category, pe.direction, pe.apply_date))

    for rpe in recurring_projected:
        key = (rpe.category, rpe.direction, rpe.apply_date)
        if key not in existing_event_dates:
            future_events.append(rpe)
            existing_event_dates.add(key)

    future_events.sort(key=lambda x: x.apply_date)

    # ---- Step 9: Build daily balance projection ----
    daily_balance = {}
    balance = effective_balance

    end_date = request_date + timedelta(days=FORECAST_DAYS)

    # Group future events by date
    events_by_date = {}
    for pe in future_events:
        d = pe.apply_date
        if d not in events_by_date:
            events_by_date[d] = []
        events_by_date[d].append(pe)

    current_date = request_date
    while current_date <= end_date:
        if current_date in events_by_date:
            for pe in events_by_date[current_date]:
                if pe.direction == "credit":
                    balance += pe.amount_home
                elif pe.direction == "debit":
                    balance -= pe.amount_home
        daily_balance[current_date] = balance
        current_date += timedelta(days=1)

    # ---- Step 10: Compute amount safe today ----
    min_projected = min(daily_balance.values()) if daily_balance else effective_balance
    amount_safe_today = max(0.0, min_projected - min_balance)

    # ---- Step 11: Identify flexible events ----
    protected_categories = set(profile.expense_categories_to_protect)
    reducible_categories = set(profile.expense_categories_user_is_willing_to_reduce)
    stoppable_categories = set(profile.expense_categories_user_is_willing_to_stop)
    flexible_events = []
    for pe in future_events:
        if pe.category in protected_categories:
            continue
        if pe.flexibility in ("stoppable", "reducible_or_stoppable") and pe.category in stoppable_categories:
            flexible_events.append(pe)
        elif pe.flexibility in ("reducible", "reducible_or_stoppable") and pe.category in reducible_categories:
            flexible_events.append(pe)

    return FinancialState(
        user_id=user_id,
        home_currency=home_currency,
        request_date=request_date,
        effective_balance=effective_balance,
        min_balance=min_balance,
        daily_balance=daily_balance,
        future_events=future_events,
        flexible_events=flexible_events,
        amount_safe_today=amount_safe_today,
    )
