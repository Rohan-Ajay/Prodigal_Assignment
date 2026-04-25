from __future__ import annotations

import json
import urllib.error
import urllib.request
from decimal import Decimal
from typing import Dict, Optional

from .types import AccountRecord
from .validation import parse_amount, validate_card_number, validate_cvv, validate_expiry


SAMPLE_ACCOUNTS: Dict[str, AccountRecord] = {
    "ACC1001": AccountRecord(
        account_id="ACC1001",
        full_name="Nithin Jain",
        dob="1990-05-14",
        aadhaar_last4="4321",
        pincode="400001",
        balance=Decimal("1250.75"),
    ),
    "ACC1002": AccountRecord(
        account_id="ACC1002",
        full_name="Rajarajeswari Balasubramaniam",
        dob="1985-11-23",
        aadhaar_last4="9876",
        pincode="400002",
        balance=Decimal("540.00"),
    ),
    "ACC1003": AccountRecord(
        account_id="ACC1003",
        full_name="Priya Agarwal",
        dob="1992-08-10",
        aadhaar_last4="2468",
        pincode="400003",
        balance=Decimal("0.00"),
    ),
    "ACC1004": AccountRecord(
        account_id="ACC1004",
        full_name="Rahul Mehta",
        dob="1988-02-29",
        aadhaar_last4="1357",
        pincode="400004",
        balance=Decimal("3200.50"),
    ),
}

class PaymentAPIError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class BasePaymentAPI:
    def lookup_account(self, account_id: str) -> AccountRecord:
        raise NotImplementedError

    def process_payment(
        self,
        *,
        account_id: str,
        amount: str,
        cardholder_name: str,
        card_number: str,
        cvv: str,
        expiry_month: int,
        expiry_year: int,
        today,
    ) -> Dict[str, object]:
        raise NotImplementedError


class InMemoryPaymentAPI(BasePaymentAPI):
    def __init__(self) -> None:
        self._txn_counter = 0

    def lookup_account(self, account_id: str) -> AccountRecord:
        account = SAMPLE_ACCOUNTS.get(account_id)
        if not account:
            raise PaymentAPIError(
                "ACCOUNT_NOT_FOUND",
                "No account found with the provided account ID.",
            )
        return account

    def process_payment(
        self,
        *,
        account_id: str,
        amount: str,
        cardholder_name: str,
        card_number: str,
        cvv: str,
        expiry_month: int,
        expiry_year: int,
        today,
    ) -> Dict[str, object]:
        account = self.lookup_account(account_id)

        parsed_amount, amount_error = parse_amount(amount)
        if amount_error:
            raise PaymentAPIError("AMOUNT_INVALID", amount_error)
        assert parsed_amount is not None

        card_error = validate_card_number(card_number)
        if card_error:
            raise PaymentAPIError("CARD_NUMBER_INVALID", card_error)

        cvv_error = validate_cvv(cvv, card_number)
        if cvv_error:
            raise PaymentAPIError("CVV_INVALID", cvv_error)

        expiry_error = validate_expiry(expiry_month, expiry_year, today)
        if expiry_error:
            raise PaymentAPIError("EXPIRY_INVALID", expiry_error)

        if parsed_amount > account.balance:
            raise PaymentAPIError(
                "AMOUNT_INVALID",
                "Amount exceeds the account's outstanding balance.",
            )

        self._txn_counter += 1
        return {
            "success": True,
            "transaction_id": f"TXN-{self._txn_counter:06d}",
        }


class HttpPaymentAPI(BasePaymentAPI):
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _parse_error_response(self, body: str) -> tuple[str, str]:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            message = body.strip() or "API error"
            return "API_ERROR", message

        return payload.get("error_code", "API_ERROR"), payload.get("message", "API error")

    def _request(self, path: str, method: str = "GET", payload: Optional[dict] = None) -> dict:
        body = None
        headers = {}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            url=f"{self.base_url}{path}",
            method=method,
            data=body,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            code, message = self._parse_error_response(exc.read().decode("utf-8", errors="replace"))
            raise PaymentAPIError(code, message) from exc
        except urllib.error.URLError as exc:
            raise PaymentAPIError("NETWORK_ERROR", "Payment service is currently unreachable.") from exc

    def lookup_account(self, account_id: str) -> AccountRecord:
        payload = self._request(f"/api/lookup-account?accountId={account_id}")
        return AccountRecord(
            account_id=payload["accountId"],
            full_name=payload["fullName"],
            dob=payload["dob"],
            aadhaar_last4=payload["aadhaarLast4"],
            pincode=payload["pincode"],
            balance=Decimal(str(payload["balance"])),
        )

    def process_payment(
        self,
        *,
        account_id: str,
        amount: str,
        cardholder_name: str,
        card_number: str,
        cvv: str,
        expiry_month: int,
        expiry_year: int,
        today,
    ) -> Dict[str, object]:
        return self._request(
            "/api/process-payment",
            method="POST",
            payload={
                "accountId": account_id,
                "amount": amount,
                "paymentMethod": {
                    "type": "CARD",
                    "card": {
                        "cardholderName": cardholder_name,
                        "cardNumber": card_number,
                        "cvv": cvv,
                        "expiryMonth": expiry_month,
                        "expiryYear": expiry_year,
                    },
                },
            },
        )
