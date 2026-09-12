"""
data_loader.py
Load and parse all dataset CSVs for the Buy or Wait? challenge.
"""

import os
import pandas as pd
from datetime import date, datetime
from dataclasses import dataclass, field
from typing import List, Optional


DATASET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dataset")


def _parse_pipe_list(value: str) -> List[str]:
    """Parse a pipe-separated string into a list. Empty string → empty list."""
    if not value or str(value).strip() == "":
        return []
    return [v.strip() for v in str(value).split("|") if v.strip()]


def _parse_date(value) -> Optional[date]:
    """Parse a YYYY-MM-DD string into a date object."""
    if not value or str(value).strip() == "" or str(value).strip().lower() == "nan":
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_optional_float(value) -> Optional[float]:
    """Parse a numeric value to float or None."""
    if value is None or str(value).strip() == "" or str(value).strip().lower() == "nan":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


@dataclass
class Request:
    request_id: str
    user_id: str
    request_date: date
    request_type: str
    requested_amount: float
    desired_completion_date: date
    allows_partial_payment: bool
    request_text: str


@dataclass
class FinancialProfile:
    user_id: str
    home_currency: str
    current_available_balance: float
    minimum_balance_to_keep: float
    financial_priorities: List[str]
    expense_categories_to_protect: List[str]
    expense_categories_user_is_willing_to_reduce: List[str]
    expense_categories_user_is_willing_to_stop: List[str]
    payment_methods_user_will_consider: List[str]
    max_installment_months: Optional[int]  # None means no installments


@dataclass
class FinancialEvent:
    event_id: str
    user_id: str
    event_type: str
    description: str
    category: str
    direction: str  # debit / credit / non_cash
    amount: Optional[float]  # None if blank (needs image)
    currency: str
    event_date: Optional[date]
    settlement_date: Optional[date]
    status: str  # settled / pending / scheduled / cancelled / failed / unrealized
    linked_event_id: str
    flexibility: str  # fixed / stoppable / reducible / reducible_or_stoppable
    minimum_allowed_amount: Optional[float]


@dataclass
class ExchangeRate:
    rate_date: date
    from_currency: str
    to_currency: str
    rate: float


@dataclass
class PaymentOption:
    payment_option_id: str
    request_id: str
    payment_method: str  # full_payment / installments
    payment_amount: float
    number_of_payments: int
    first_payment_date: Optional[date]
    payment_frequency_days: Optional[int]  # None for full_payment
    financing_fee: float
    total_payable_amount: float


@dataclass
class Message:
    message_id: str
    user_id: str
    request_id: str
    related_event_id: str
    sent_at: str
    source_type: str
    message_text: str


@dataclass
class ImageRecord:
    image_id: str
    user_id: str
    request_id: str
    related_event_id: str


@dataclass
class AllData:
    requests: List[Request]
    sample_requests: List[Request]
    profiles: dict  # user_id → FinancialProfile
    events: List[FinancialEvent]
    exchange_rates: List[ExchangeRate]
    payment_options: List[PaymentOption]
    messages: List[Message]
    images: List[ImageRecord]
    # sample output data
    sample_outputs: dict  # request_id → dict of output fields


def load_all() -> AllData:
    """Load all dataset files and return typed AllData."""
    ds = DATASET_DIR

    def _file(name):
        path = os.path.join(ds, name)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Required dataset file not found: {path}")
        return path

    # ---- requests.csv ----
    req_df = pd.read_csv(_file("requests.csv"), keep_default_na=False, dtype=str)
    requests = []
    for _, row in req_df.iterrows():
        requests.append(Request(
            request_id=row["request_id"].strip(),
            user_id=row["user_id"].strip(),
            request_date=_parse_date(row["request_date"]),
            request_type=row["request_type"].strip(),
            requested_amount=float(row["requested_amount"]),
            desired_completion_date=_parse_date(row["desired_completion_date"]),
            allows_partial_payment=str(row["allows_partial_payment"]).strip().lower() == "true",
            request_text=row["request_text"].strip(),
        ))

    # ---- sample_requests.csv ----
    sr_df = pd.read_csv(_file("sample_requests.csv"), keep_default_na=False, dtype=str)
    sample_requests = []
    sample_outputs = {}
    for _, row in sr_df.iterrows():
        rid = row["request_id"].strip()
        sample_requests.append(Request(
            request_id=rid,
            user_id=row["user_id"].strip(),
            request_date=_parse_date(row["request_date"]),
            request_type=row["request_type"].strip(),
            requested_amount=float(row["requested_amount"]),
            desired_completion_date=_parse_date(row["desired_completion_date"]),
            allows_partial_payment=str(row["allows_partial_payment"]).strip().lower() == "true",
            request_text=row["request_text"].strip(),
        ))
        sample_outputs[rid] = {
            "amount_safe_to_pay": row.get("amount_safe_to_pay", ""),
            "affordability_status": row.get("affordability_status", ""),
            "recommended_payment_method": row.get("recommended_payment_method", ""),
            "payment_plan": row.get("payment_plan", ""),
            "earliest_date_for_full_payment": row.get("earliest_date_for_full_payment", ""),
            "spending_changes_needed": row.get("spending_changes_needed", ""),
            "decision_explanation": row.get("decision_explanation", ""),
        }

    # ---- financial_profiles.csv ----
    fp_df = pd.read_csv(_file("financial_profiles.csv"), keep_default_na=False, dtype=str)
    profiles = {}
    for _, row in fp_df.iterrows():
        uid = row["user_id"].strip()
        max_inst = _parse_optional_float(row.get("max_installment_months", ""))
        profiles[uid] = FinancialProfile(
            user_id=uid,
            home_currency=row["home_currency"].strip(),
            current_available_balance=float(row["current_available_balance"]),
            minimum_balance_to_keep=float(row["minimum_balance_to_keep"]),
            financial_priorities=_parse_pipe_list(row.get("financial_priorities", "")),
            expense_categories_to_protect=_parse_pipe_list(row.get("expense_categories_to_protect", "")),
            expense_categories_user_is_willing_to_reduce=_parse_pipe_list(row.get("expense_categories_user_is_willing_to_reduce", "")),
            expense_categories_user_is_willing_to_stop=_parse_pipe_list(row.get("expense_categories_user_is_willing_to_stop", "")),
            payment_methods_user_will_consider=_parse_pipe_list(row.get("payment_methods_user_will_consider", "")),
            max_installment_months=int(max_inst) if max_inst is not None else None,
        )

    # ---- financial_events.csv ----
    fe_df = pd.read_csv(_file("financial_events.csv"), keep_default_na=False, dtype=str)
    events = []
    for _, row in fe_df.iterrows():
        amt_str = str(row["amount"]).strip()
        amt = None if amt_str == "" else float(amt_str)
        min_allowed_str = str(row.get("minimum_allowed_amount", "")).strip()
        min_allowed = None if min_allowed_str == "" else _parse_optional_float(min_allowed_str)
        events.append(FinancialEvent(
            event_id=row["event_id"].strip(),
            user_id=row["user_id"].strip(),
            event_type=row["event_type"].strip(),
            description=row["description"].strip(),
            category=row["category"].strip(),
            direction=row["direction"].strip(),
            amount=amt,
            currency=row["currency"].strip(),
            event_date=_parse_date(row["event_date"]),
            settlement_date=_parse_date(row["settlement_date"]),
            status=row["status"].strip(),
            linked_event_id=row["linked_event_id"].strip(),
            flexibility=row["flexibility"].strip(),
            minimum_allowed_amount=min_allowed,
        ))

    # ---- exchange_rates.csv ----
    er_df = pd.read_csv(_file("exchange_rates.csv"), keep_default_na=False, dtype=str)
    exchange_rates = []
    for _, row in er_df.iterrows():
        exchange_rates.append(ExchangeRate(
            rate_date=_parse_date(row["rate_date"]),
            from_currency=row["from_currency"].strip(),
            to_currency=row["to_currency"].strip(),
            rate=float(row["rate"]),
        ))

    # ---- request_payment_options.csv ----
    po_df = pd.read_csv(_file("request_payment_options.csv"), keep_default_na=False, dtype=str)
    payment_options = []
    for _, row in po_df.iterrows():
        freq_str = str(row.get("payment_frequency_days", "")).strip()
        freq = None if freq_str == "" else int(float(freq_str))
        payment_options.append(PaymentOption(
            payment_option_id=row["payment_option_id"].strip(),
            request_id=row["request_id"].strip(),
            payment_method=row["payment_method"].strip(),
            payment_amount=float(row["payment_amount"]),
            number_of_payments=int(float(row["number_of_payments"])),
            first_payment_date=_parse_date(row["first_payment_date"]),
            payment_frequency_days=freq,
            financing_fee=float(row["financing_fee"]),
            total_payable_amount=float(row["total_payable_amount"]),
        ))

    # ---- messages.csv ----
    msg_df = pd.read_csv(_file("messages.csv"), keep_default_na=False, dtype=str)
    messages = []
    for _, row in msg_df.iterrows():
        messages.append(Message(
            message_id=row["message_id"].strip(),
            user_id=row["user_id"].strip(),
            request_id=row.get("request_id", "").strip(),
            related_event_id=row.get("related_event_id", "").strip(),
            sent_at=row.get("sent_at", "").strip(),
            source_type=row.get("source_type", "").strip(),
            message_text=row["message_text"].strip(),
        ))

    # ---- images.csv ----
    img_df = pd.read_csv(_file("images.csv"), keep_default_na=False, dtype=str)
    images = []
    for _, row in img_df.iterrows():
        images.append(ImageRecord(
            image_id=row["image_id"].strip(),
            user_id=row["user_id"].strip(),
            request_id=row.get("request_id", "").strip(),
            related_event_id=row.get("related_event_id", "").strip(),
        ))

    return AllData(
        requests=requests,
        sample_requests=sample_requests,
        profiles=profiles,
        events=events,
        exchange_rates=exchange_rates,
        payment_options=payment_options,
        messages=messages,
        images=images,
        sample_outputs=sample_outputs,
    )


if __name__ == "__main__":
    data = load_all()
    print(f"Requests: {len(data.requests)}")
    print(f"Sample requests: {len(data.sample_requests)}")
    print(f"Profiles: {len(data.profiles)}")
    print(f"Events: {len(data.events)}")
    print(f"Exchange rates: {len(data.exchange_rates)}")
    print(f"Payment options: {len(data.payment_options)}")
    print(f"Messages: {len(data.messages)}")
    print(f"Images: {len(data.images)}")
