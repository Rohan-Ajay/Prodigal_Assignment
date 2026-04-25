from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass
class AccountRecord:
    account_id: str
    full_name: str
    dob: str
    aadhaar_last4: str
    pincode: str
    balance: Decimal


@dataclass
class VerificationState:
    full_name: Optional[str] = None
    dob: Optional[str] = None
    aadhaar_last4: Optional[str] = None
    pincode: Optional[str] = None
    attempts: int = 0
    retry_limit: int = 3
    verified: bool = False


@dataclass
class PaymentDetails:
    amount: Optional[Decimal] = None
    cardholder_name: Optional[str] = None
    card_number: Optional[str] = None
    cvv: Optional[str] = None
    expiry_month: Optional[int] = None
    expiry_year: Optional[int] = None
    attempts: int = 0
    retry_limit: int = 3


@dataclass
class ConversationState:
    stage: str = "awaiting_account_id"
    account_id: Optional[str] = None
    account: Optional[AccountRecord] = None
    verification: VerificationState = field(default_factory=VerificationState)
    payment: PaymentDetails = field(default_factory=PaymentDetails)
    lookup_attempts: int = 0
    lookup_retry_limit: int = 3
    latest_balance_shared: bool = False
    closed: bool = False
    today: date = field(default_factory=date.today)
