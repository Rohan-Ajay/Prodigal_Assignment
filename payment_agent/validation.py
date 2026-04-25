from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple


def normalize_account_id(account_id: str) -> str:
    return account_id.strip().upper()


def parse_amount(value: str) -> Tuple[Optional[Decimal], Optional[str]]:
    try:
        amount = Decimal(value.strip())
    except (InvalidOperation, AttributeError):
        return None, "Please share a valid payment amount, for example `500.00`."

    if amount <= 0:
        return None, "Amount must be greater than zero."
    if amount.as_tuple().exponent < -2:
        return None, "Amount can have at most 2 decimal places."
    return amount, None


def luhn_check(card_number: str) -> bool:
    digits = [int(ch) for ch in card_number]
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def validate_card_number(card_number: str) -> Optional[str]:
    if any(ch in card_number for ch in "*Xx_#"):
        return "Card number appears to be masked or partial. Please enter the full number."

    normalized = card_number.replace(" ", "").replace("-", "")
    if not normalized.isdigit():
        return "Card number must contain digits only."
    if not 12 <= len(normalized) <= 16:
        return "Card number must contain 12 to 16 digits."
    if not luhn_check(normalized):
        return "Card number did not pass checksum validation."
    return None


def expected_cvv_length(card_number: str) -> int:
    normalized = card_number.replace(" ", "").replace("-", "")
    if normalized.startswith(("34", "37")):
        return 4
    return 3


def validate_cvv(cvv: str, card_number: str) -> Optional[str]:
    if not cvv.isdigit():
        return "CVV must contain digits only."
    expected = expected_cvv_length(card_number)
    if len(cvv) != expected:
        return f"CVV must be {expected} digits for this card."
    return None


def validate_expiry(month: int, year: int, today: date) -> Optional[str]:
    if month < 1 or month > 12:
        return "Expiry month must be between 1 and 12."
    if year < 1000:
        return "Expiry year must use four digits."
    current_marker = today.year * 100 + today.month
    expiry_marker = year * 100 + month
    if expiry_marker < current_marker:
        return "Card has expired."
    return None
