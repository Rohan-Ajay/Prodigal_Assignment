from __future__ import annotations

import os
import re
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from .api import BasePaymentAPI, HttpPaymentAPI, InMemoryPaymentAPI, PaymentAPIError
from .types import ConversationState
from .validation import normalize_account_id, parse_amount, validate_card_number, validate_cvv, validate_expiry


ACCOUNT_ID_RE = re.compile(r"\bACC\d{4}\b", re.IGNORECASE)
DOB_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
PINCODE_RE = re.compile(r"\b(\d{6})\b")
LAST4_LABELED_RE = re.compile(r"(?:aadhaar|aadhar)[^\d]{0,10}(\d{4})", re.IGNORECASE)
AMOUNT_RE = re.compile(r"(?:amount|pay|payment)\D{0,8}(\d+(?:\.\d{1,2})?)", re.IGNORECASE)
CARD_NUMBER_RE = re.compile(r"\b(?:\d[ -]?){12,16}\b")
CVV_RE = re.compile(r"(?:cvv|cvc)[^\d]{0,6}(\d{3,4})", re.IGNORECASE)
EXPIRY_SLASH_RE = re.compile(r"\b(0[1-9]|1[0-2])\s*/\s*(\d{4})\b")
EXPIRY_LABEL_RE = re.compile(
    r"(?:expiry|exp)[^\d]{0,8}(0?[1-9]|1[0-2])[^\d]{1,5}(\d{4})",
    re.IGNORECASE,
)
CARDHOLDER_LABEL_RE = re.compile(
    r"(?:cardholder(?:\s+name)?|name\s+on\s+card)\s*[:\-]?\s*([A-Za-z][A-Za-z .'-]{1,80}?)(?=\s+(?:cvv|cvc|expiry|exp)\b|$)",
    re.IGNORECASE,
)


def build_default_api() -> BasePaymentAPI:
    mode = os.getenv("PAYMENT_API_MODE", "memory").strip().lower()
    if mode == "http":
        base_url = os.getenv("PAYMENT_API_BASE_URL", "").strip()
        if not base_url:
            raise ValueError("PAYMENT_API_BASE_URL must be set when PAYMENT_API_MODE=http.")
        return HttpPaymentAPI(base_url)
    return InMemoryPaymentAPI()


class Agent:
    def __init__(self, api: Optional[BasePaymentAPI] = None, today: Optional[date] = None) -> None:
        self.api = api or build_default_api()
        self.state = ConversationState(today=today or date.today())

    def next(self, user_input: str) -> Dict[str, str]:
        if self.state.closed:
            return {"message": "This conversation is closed. Please start a new session for another payment."}

        text = (user_input or "").strip()
        extracted = self._extract_fields(text)
        response_parts: List[str] = []

        if self.state.stage == "awaiting_account_id":
            self._handle_account_phase(text, extracted, response_parts)
        elif self.state.stage == "awaiting_verification":
            self._handle_verification_phase(text, extracted, response_parts)
        elif self.state.stage == "awaiting_payment":
            self._handle_payment_phase(text, extracted, response_parts)
        elif self.state.stage == "completed":
            self.state.closed = True
            response_parts.append("The payment flow is already complete. Please start a new session if you need anything else.")
        else:
            self.state.closed = True
            response_parts.append("The conversation ended unexpectedly. Please start a new session.")

        return {"message": " ".join(part for part in response_parts if part).strip()}

    def _handle_account_phase(self, text: str, extracted: Dict[str, object], response_parts: List[str]) -> None:
        account_id = extracted.get("account_id")
        if not account_id:
            response_parts.append("Hello! Please share your account ID to get started with the payment collection flow.")
            return

        normalized_id = normalize_account_id(str(account_id))
        self.state.account_id = normalized_id

        try:
            account = self.api.lookup_account(normalized_id)
        except PaymentAPIError as exc:
            self.state.lookup_attempts += 1
            if self.state.lookup_attempts >= self.state.lookup_retry_limit:
                self.state.closed = True
                response_parts.append(
                    f"I couldn't complete account lookup after multiple attempts. {exc.message} I'm closing this conversation for safety."
                )
                return
            response_parts.append(
                f"I couldn't complete account lookup. {exc.message} Please check the account ID and try again. Attempts remaining: {self.state.lookup_retry_limit - self.state.lookup_attempts}."
            )
            return

        self.state.account = account
        self.state.lookup_attempts = 0
        self.state.stage = "awaiting_verification"
        self._store_verification_inputs(text, extracted)
        verification_message = self._evaluate_verification_attempt()
        if verification_message:
            response_parts.append(verification_message)
            return

        response_parts.append("Thanks. I found the account. Please confirm your full name exactly as on the account.")

    def _handle_verification_phase(self, text: str, extracted: Dict[str, object], response_parts: List[str]) -> None:
        if extracted.get("account_id"):
            self._reset_for_new_account(normalize_account_id(str(extracted["account_id"])))
            self._handle_account_phase(text, extracted, response_parts)
            return

        self._store_verification_inputs(text, extracted)
        verification_message = self._evaluate_verification_attempt()
        if verification_message:
            response_parts.append(verification_message)
            return

        if not self.state.verification.full_name:
            response_parts.append("Please confirm your full name exactly as on the account.")
            return

        response_parts.append("Please verify either your date of birth (`YYYY-MM-DD`), Aadhaar last 4 digits, or pincode.")

    def _handle_payment_phase(self, text: str, extracted: Dict[str, object], response_parts: List[str]) -> None:
        self._store_payment_inputs(text, extracted)

        field_error = self._validate_partial_payment_fields()
        if field_error:
            response_parts.append(field_error)
            return

        missing = self._missing_payment_fields()
        if missing:
            response_parts.append(self._prompt_for_missing_payment_field(missing[0]))
            return

        payment = self.state.payment
        assert self.state.account_id is not None
        assert payment.amount is not None
        assert payment.cardholder_name is not None
        assert payment.card_number is not None
        assert payment.cvv is not None
        assert payment.expiry_month is not None
        assert payment.expiry_year is not None

        try:
            result = self.api.process_payment(
                account_id=self.state.account_id,
                amount=str(payment.amount),
                cardholder_name=payment.cardholder_name,
                card_number=payment.card_number,
                cvv=payment.cvv,
                expiry_month=payment.expiry_month,
                expiry_year=payment.expiry_year,
                today=self.state.today,
            )
        except PaymentAPIError as exc:
            self.state.payment.attempts += 1
            retryable_field = self._infer_payment_error_field(exc)
            if self.state.payment.attempts >= self.state.payment.retry_limit and retryable_field is not None:
                self.state.closed = True
                response_parts.append(
                    f"Payment failed. {exc.message} The retry limit has been reached, so I'm closing this conversation now."
                )
                return

            response_parts.append(self._handle_payment_error(exc, field_name=retryable_field))
            return

        self.state.stage = "completed"
        self.state.closed = True
        response_parts.append(
            f"Payment successful for INR {payment.amount:.2f}. Your transaction ID is `{result['transaction_id']}`. This conversation is now complete."
        )

    def _extract_fields(self, text: str) -> Dict[str, object]:
        extracted: Dict[str, object] = {}

        account_match = ACCOUNT_ID_RE.search(text)
        if account_match:
            extracted["account_id"] = account_match.group(0).upper()

        dob_match = DOB_RE.search(text)
        if dob_match:
            extracted["dob"] = dob_match.group(1)

        last4_match = LAST4_LABELED_RE.search(text)
        if last4_match:
            extracted["aadhaar_last4"] = last4_match.group(1)

        pincode_match = re.search(r"(?:pincode|pin\s*code)[^\d]{0,10}(\d{6})", text, re.IGNORECASE)
        if pincode_match:
            extracted["pincode"] = pincode_match.group(1)

        amount_match = AMOUNT_RE.search(text)
        if amount_match:
            extracted["amount"] = amount_match.group(1)

        card_match = CARD_NUMBER_RE.search(text)
        if card_match:
            extracted["card_number"] = re.sub(r"[ -]", "", card_match.group(0))

        cvv_match = CVV_RE.search(text)
        if cvv_match:
            extracted["cvv"] = cvv_match.group(1)

        expiry_match = EXPIRY_LABEL_RE.search(text) or EXPIRY_SLASH_RE.search(text)
        if expiry_match:
            extracted["expiry_month"] = int(expiry_match.group(1))
            extracted["expiry_year"] = int(expiry_match.group(2))

        cardholder_match = CARDHOLDER_LABEL_RE.search(text)
        if cardholder_match:
            extracted["cardholder_name"] = cardholder_match.group(1).strip()

        return extracted

    def _store_verification_inputs(self, text: str, extracted: Dict[str, object]) -> None:
        verification = self.state.verification

        if "dob" in extracted:
            verification.dob = str(extracted["dob"])
        if "aadhaar_last4" in extracted:
            verification.aadhaar_last4 = str(extracted["aadhaar_last4"])
        if "pincode" in extracted:
            verification.pincode = str(extracted["pincode"])

        if "amount" in extracted:
            self._store_payment_inputs(text, extracted)

        if self.state.account and "full_name" not in extracted:
            labeled_name_match = re.search(r"(?:full name)\s*[:\-]?\s*([A-Za-z][A-Za-z .'-]{1,80})", text, re.IGNORECASE)
            if labeled_name_match:
                verification.full_name = labeled_name_match.group(1).strip()
            elif self.state.account.full_name in text:
                verification.full_name = self.state.account.full_name
            else:
                inferred_name = self._infer_name(text)
                if inferred_name and (verification.full_name is None or self._is_name_expected()):
                    verification.full_name = inferred_name

        if self.state.stage == "awaiting_verification":
            if verification.dob is None and "dob" not in extracted and self._expects_secondary_factor(text):
                bare_four = re.fullmatch(r"\d{4}", text.strip())
                bare_six = re.fullmatch(r"\d{6}", text.strip())
                if bare_four:
                    verification.aadhaar_last4 = bare_four.group(0)
                elif bare_six:
                    verification.pincode = bare_six.group(0)

    def _store_payment_inputs(self, text: str, extracted: Dict[str, object]) -> None:
        payment = self.state.payment
        next_missing = self._missing_payment_fields()[:1]

        if "amount" in extracted:
            amount, error = parse_amount(str(extracted["amount"]))
            if amount and not error:
                payment.amount = amount
        elif self.state.stage == "awaiting_payment" and next_missing == ["amount"]:
            bare_amount = re.fullmatch(r"\d+(?:\.\d{1,2})?", text.strip())
            if bare_amount:
                amount, error = parse_amount(bare_amount.group(0))
                if amount and not error:
                    payment.amount = amount

        if "card_number" in extracted:
            payment.card_number = str(extracted["card_number"])
        elif self.state.stage == "awaiting_payment" and next_missing == ["card_number"]:
            bare_card = re.fullmatch(r"[\d\s\-*Xx_#]{10,25}", text.strip())
            if bare_card:
                payment.card_number = bare_card.group(0)

        if "cvv" in extracted:
            payment.cvv = str(extracted["cvv"])
        elif self.state.stage == "awaiting_payment" and next_missing == ["cvv"]:
            bare_cvv = re.fullmatch(r"\d{3,4}", text.strip())
            if bare_cvv:
                payment.cvv = bare_cvv.group(0)
            elif text.strip():
                payment.cvv = text.strip()

        if "expiry_month" in extracted and "expiry_year" in extracted:
            payment.expiry_month = int(extracted["expiry_month"])
            payment.expiry_year = int(extracted["expiry_year"])

        if "cardholder_name" in extracted:
            payment.cardholder_name = str(extracted["cardholder_name"])
        elif self.state.stage == "awaiting_payment" and next_missing == ["cardholder_name"]:
            inferred_name = self._infer_name(text)
            if inferred_name:
                payment.cardholder_name = inferred_name

    def _evaluate_verification_attempt(self) -> Optional[str]:
        verification = self.state.verification
        account = self.state.account
        if account is None:
            return None

        if verification.verified:
            return self._advance_after_verification()

        if verification.full_name is None:
            return None

        has_secondary = any([verification.dob, verification.aadhaar_last4, verification.pincode])
        if not has_secondary:
            return None

        verification.attempts += 1

        name_matches = verification.full_name == account.full_name
        secondary_matches = any(
            [
                verification.dob == account.dob if verification.dob else False,
                verification.aadhaar_last4 == account.aadhaar_last4 if verification.aadhaar_last4 else False,
                verification.pincode == account.pincode if verification.pincode else False,
            ]
        )

        if name_matches and secondary_matches:
            verification.verified = True
            return self._advance_after_verification()

        if verification.attempts >= verification.retry_limit:
            self.state.closed = True
            return "Verification failed because the provided details did not match the account records. The retry limit has been reached, so I'm closing this conversation for safety."

        remaining = verification.retry_limit - verification.attempts
        if not name_matches:
            verification.full_name = None
            return f"Verification failed because the full name did not match exactly. Please re-enter the exact full name. Attempts remaining: {remaining}."

        return (
            "Verification failed because the secondary factor did not match the account records. "
            f"Please retry with your date of birth (`YYYY-MM-DD`), Aadhaar last 4 digits, or pincode. Attempts remaining: {remaining}."
        )

    def _advance_after_verification(self) -> str:
        assert self.state.account is not None
        self.state.stage = "awaiting_payment"
        self.state.latest_balance_shared = True

        payment_summary = []
        self._store_payment_inputs("", {})
        missing = self._missing_payment_fields()
        if missing:
            payment_summary.append(self._prompt_for_missing_payment_field(missing[0]))

        balance_message = f"Identity verified. Your outstanding balance is INR {self.state.account.balance:.2f}."
        if payment_summary:
            return f"{balance_message} {payment_summary[0]}"
        return balance_message

    def _missing_payment_fields(self) -> List[str]:
        payment = self.state.payment
        missing: List[str] = []
        if payment.amount is None:
            missing.append("amount")
        if payment.cardholder_name is None:
            missing.append("cardholder_name")
        if payment.card_number is None:
            missing.append("card_number")
        if payment.cvv is None:
            missing.append("cvv")
        if payment.expiry_month is None or payment.expiry_year is None:
            missing.append("expiry")
        return missing

    def _prompt_for_missing_payment_field(self, field_name: str) -> str:
        prompts = {
            "amount": "Please share the payment amount you would like to pay.",
            "cardholder_name": "Please share the cardholder name exactly as it appears on the card.",
            "card_number": "Please share the card number using digits only.",
            "cvv": "Please share the card CVV.",
            "expiry": "Please share the card expiry in `MM/YYYY` format.",
        }
        return prompts[field_name]

    def _handle_payment_error(self, exc: PaymentAPIError, field_name: Optional[str] = None) -> str:
        field_name = field_name or self._infer_payment_error_field(exc)
        if field_name == "amount":
            self.state.payment.amount = None
            if "outstanding balance" in exc.message.lower() or "balance" in exc.message.lower():
                return f"Payment failed. {exc.message} Please share an amount less than or equal to the outstanding balance."
            return f"Payment failed. {exc.message} Please share a valid amount."
        if field_name == "card_number":
            self.state.payment.card_number = None
            return f"Payment failed. {exc.message} Please share a valid card number."
        if field_name == "cvv":
            self.state.payment.cvv = None
            return f"Payment failed. {exc.message} Please share the CVV again."
        if field_name == "expiry":
            self.state.payment.expiry_month = None
            self.state.payment.expiry_year = None
            return f"Payment failed. {exc.message} Please share a valid expiry date."
        self.state.closed = True
        return f"Payment failed. {exc.message} I'm closing this conversation now."

    def _validate_partial_payment_fields(self) -> Optional[str]:
        payment = self.state.payment

        if payment.card_number is not None:
            card_error = validate_card_number(payment.card_number)
            if card_error:
                return self._handle_payment_error(
                    PaymentAPIError("CARD_NUMBER_INVALID", card_error),
                    field_name="card_number",
                )

        if payment.card_number is not None and payment.cvv is not None:
            cvv_error = validate_cvv(payment.cvv, payment.card_number)
            if cvv_error:
                return self._handle_payment_error(
                    PaymentAPIError("CVV_INVALID", cvv_error),
                    field_name="cvv",
                )

        if payment.expiry_month is not None and payment.expiry_year is not None:
            expiry_error = validate_expiry(payment.expiry_month, payment.expiry_year, self.state.today)
            if expiry_error:
                return self._handle_payment_error(
                    PaymentAPIError("EXPIRY_INVALID", expiry_error),
                    field_name="expiry",
                )

        return None

    def _infer_payment_error_field(self, exc: PaymentAPIError) -> Optional[str]:
        if exc.code in {"AMOUNT_INVALID", "INVALID_AMOUNT"}:
            return "amount"
        if exc.code in {"CARD_NUMBER_INVALID", "INVALID_CARD"}:
            return "card_number"
        if exc.code in {"CVV_INVALID", "INVALID_CVV"}:
            return "cvv"
        if exc.code in {"EXPIRY_INVALID", "INVALID_EXPIRY"}:
            return "expiry"

        combined = f"{exc.code} {exc.message}".lower()
        if "cvv" in combined:
            return "cvv"
        if any(token in combined for token in {"expiry", "expired", "month", "year"}):
            return "expiry"
        if any(token in combined for token in {"amount", "balance"}):
            return "amount"
        if any(token in combined for token in {"card", "checksum", "digits only", "masked", "partial"}):
            return "card_number"
        return None

    def _reset_for_new_account(self, account_id: str) -> None:
        today = self.state.today
        self.state = ConversationState(today=today)
        self.state.account_id = account_id

    def _expects_secondary_factor(self, text: str) -> bool:
        return bool(text.strip())

    def _infer_name(self, text: str) -> Optional[str]:
        candidate = text
        candidate = ACCOUNT_ID_RE.sub(" ", candidate)
        candidate = DOB_RE.sub(" ", candidate)
        candidate = LAST4_LABELED_RE.sub(" ", candidate)
        candidate = re.sub(r"(?:pincode|pin\s*code)[^\d]{0,10}\d{6}", " ", candidate, flags=re.IGNORECASE)
        candidate = AMOUNT_RE.sub(" ", candidate)
        candidate = re.sub(r"\bpay\s+\d+(?:\.\d{1,2})?\b", " ", candidate, flags=re.IGNORECASE)
        candidate = CARD_NUMBER_RE.sub(" ", candidate)
        candidate = CVV_RE.sub(" ", candidate)
        candidate = EXPIRY_LABEL_RE.sub(" ", candidate)
        candidate = EXPIRY_SLASH_RE.sub(" ", candidate)
        candidate = CARDHOLDER_LABEL_RE.sub(lambda match: f" {match.group(1)} ", candidate)
        candidate = re.sub(r"(?:name on card|cardholder(?:\s+name)?|full name|name)\s*[:\-]?", " ", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"[^A-Za-z .'-]+", " ", candidate)
        candidate = re.sub(r"\s+", " ", candidate).strip()
        if not candidate:
            return None
        if len(candidate.split()) < 2:
            return None
        return candidate

    def _is_name_expected(self) -> bool:
        return self.state.stage == "awaiting_verification" and not self.state.verification.verified
