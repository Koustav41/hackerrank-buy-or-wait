from typing import List, Optional, Dict, Any
from pydantic import BaseModel

class RequestSummary(BaseModel):
    request_id: str
    user_id: str
    request_date: str
    requested_amount: float
    currency: str
    request_type: str
    purpose: str
    amount_safe_to_pay: float
    affordability_status: str
    recommended_payment_method: str
    earliest_date_for_full_payment: Optional[str] = None

class PaymentOption(BaseModel):
    payment_option_id: str
    request_id: str
    payment_method: str
    payment_amount: float
    number_of_payments: int
    first_payment_date: Optional[str] = None
    payment_frequency_days: Optional[int] = None
    financing_fee: float
    total_payable_amount: float

class DecisionDetail(BaseModel):
    request_id: str
    user_id: str
    request_date: str
    requested_amount: float
    currency: str
    request_type: str
    request_text: str
    desired_completion_date: Optional[str] = None
    allows_partial_payment: bool
    amount_safe_to_pay: float
    affordability_status: str
    recommended_payment_method: str
    payment_plan: str
    earliest_date_for_full_payment: Optional[str] = None
    spending_changes_needed: str
    decision_explanation: str
    current_balance: float
    min_balance_to_keep: float
    financial_priorities: str = ""
    payment_options: List[Dict[str, Any]] = []

class TimelinePoint(BaseModel):
    date: str
    balance: float
    min_balance: float
    net_flow: float
    notes: Optional[str] = None

class StatsSummary(BaseModel):
    total_requests: int
    affordable_now: int
    affordable_with_plan: int
    affordable_later: int
    not_affordable: int
    total_safe_amount: float
    total_requested_amount: float

class ChatRequest(BaseModel):
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    question: str

class ChatResponse(BaseModel):
    answer: str
    context: Optional[Dict[str, Any]] = None
