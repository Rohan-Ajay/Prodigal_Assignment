import json
import unittest
from datetime import date
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import MagicMock, patch

from agent import Agent
from payment_agent.api import HttpPaymentAPI, InMemoryPaymentAPI, PaymentAPIError


class AgentTests(unittest.TestCase):
    def test_successful_end_to_end_flow(self) -> None:
        agent = Agent(today=date(2026, 4, 24))
        self.assertIn("account ID", agent.next("hello")["message"])
        self.assertIn("full name", agent.next("ACC1001")["message"])
        self.assertIn("date of birth", agent.next("Nithin Jain")["message"])
        self.assertIn("outstanding balance", agent.next("1990-05-14")["message"])
        self.assertIn("cardholder name", agent.next("pay 500")["message"])
        self.assertIn("card number", agent.next("name on card: Nithin Jain")["message"])
        self.assertIn("CVV", agent.next("4532015112830366")["message"])
        self.assertIn("expiry", agent.next("cvv 123")["message"])
        final = agent.next("12/2027")["message"]
        self.assertIn("Payment successful", final)
        self.assertIn("TXN-000001", final)

    def test_verification_failure_closes_after_limit(self) -> None:
        agent = Agent(today=date(2026, 4, 24))
        agent.next("ACC1001")
        self.assertIn("Please confirm your full name", agent.next("Wrong Name")["message"])
        first_failure = agent.next("full name: Wrong Name pincode 400001")["message"]
        self.assertIn("full name did not match exactly", first_failure)
        self.assertIn("Attempts remaining: 2", first_failure)
        second_failure = agent.next("full name: Still Wrong pincode 400001")["message"]
        self.assertIn("Attempts remaining: 1", second_failure)
        final = agent.next("full name: No Match pincode 400001")["message"]
        self.assertIn("retry limit", final)
        self.assertIn("closing this conversation", final)

    def test_payment_failure_and_recovery(self) -> None:
        agent = Agent(today=date(2026, 4, 24))
        agent.next("ACC1002")
        agent.next("Rajarajeswari Balasubramaniam")
        agent.next("9876")
        agent.next("pay 500")
        agent.next("Rajarajeswari Balasubramaniam")
        agent.next("4532015112830366")
        failure = agent.next("cvv 123")["message"]
        self.assertIn("expiry", failure)
        expired = agent.next("01/2020")["message"]
        self.assertIn("Card has expired", expired)
        success = agent.next("12/2027")["message"]
        self.assertIn("Payment successful", success)

    def test_out_of_order_information_is_used_without_reasking(self) -> None:
        agent = Agent(today=date(2026, 4, 24))
        msg = agent.next("ACC1004 Rahul Mehta 1988-02-29 pay 100 cardholder name: Rahul Mehta cvv 123 expiry 12/2027")["message"]
        self.assertIn("outstanding balance", msg)
        self.assertIn("card number", msg)

    def test_short_card_number_is_rejected_in_conversation(self) -> None:
        agent = Agent(today=date(2026, 4, 24))
        agent.next("ACC1001")
        agent.next("Nithin Jain")
        agent.next("1990-05-14")
        agent.next("pay 100")
        agent.next("name on card: Nithin Jain")
        failure = agent.next("12345678901")["message"]
        self.assertIn("12 to 16 digits", failure)
        self.assertIn("valid card number", failure)

    def test_masked_or_partial_card_number_is_rejected(self) -> None:
        api = InMemoryPaymentAPI()
        with self.assertRaises(PaymentAPIError) as ctx:
            api.process_payment(
                account_id="ACC1001",
                amount="100",
                cardholder_name="Nithin Jain",
                card_number="4532********0366",
                cvv="123",
                expiry_month=12,
                expiry_year=2027,
                today=date(2026, 4, 24),
            )
        self.assertEqual("CARD_NUMBER_INVALID", ctx.exception.code)
        self.assertIn("masked or partial", ctx.exception.message)

    def test_checksum_failure_is_rejected(self) -> None:
        api = InMemoryPaymentAPI()
        with self.assertRaises(PaymentAPIError) as ctx:
            api.process_payment(
                account_id="ACC1001",
                amount="100",
                cardholder_name="Nithin Jain",
                card_number="4532015112830365",
                cvv="123",
                expiry_month=12,
                expiry_year=2027,
                today=date(2026, 4, 24),
            )
        self.assertEqual("CARD_NUMBER_INVALID", ctx.exception.code)
        self.assertIn("checksum", ctx.exception.message)

    def test_wrong_cvv_length_is_rejected(self) -> None:
        api = InMemoryPaymentAPI()
        with self.assertRaises(PaymentAPIError) as ctx:
            api.process_payment(
                account_id="ACC1001",
                amount="100",
                cardholder_name="Nithin Jain",
                card_number="4532015112830366",
                cvv="12",
                expiry_month=12,
                expiry_year=2027,
                today=date(2026, 4, 24),
            )
        self.assertEqual("CVV_INVALID", ctx.exception.code)
        self.assertIn("CVV must be 3 digits", ctx.exception.message)

    def test_wrong_expiry_month_is_rejected(self) -> None:
        api = InMemoryPaymentAPI()
        with self.assertRaises(PaymentAPIError) as ctx:
            api.process_payment(
                account_id="ACC1001",
                amount="100",
                cardholder_name="Nithin Jain",
                card_number="4532015112830366",
                cvv="123",
                expiry_month=13,
                expiry_year=2027,
                today=date(2026, 4, 24),
            )
        self.assertEqual("EXPIRY_INVALID", ctx.exception.code)
        self.assertIn("between 1 and 12", ctx.exception.message)

    def test_wrong_expiry_year_is_rejected(self) -> None:
        api = InMemoryPaymentAPI()
        with self.assertRaises(PaymentAPIError) as ctx:
            api.process_payment(
                account_id="ACC1001",
                amount="100",
                cardholder_name="Nithin Jain",
                card_number="4532015112830366",
                cvv="123",
                expiry_month=12,
                expiry_year=99,
                today=date(2026, 4, 24),
            )
        self.assertEqual("EXPIRY_INVALID", ctx.exception.code)
        self.assertIn("four digits", ctx.exception.message)

    def test_bad_amount_is_rejected(self) -> None:
        api = InMemoryPaymentAPI()
        with self.assertRaises(PaymentAPIError) as ctx:
            api.process_payment(
                account_id="ACC1001",
                amount="0",
                cardholder_name="Nithin Jain",
                card_number="4532015112830366",
                cvv="123",
                expiry_month=12,
                expiry_year=2027,
                today=date(2026, 4, 24),
            )
        self.assertEqual("AMOUNT_INVALID", ctx.exception.code)
        self.assertIn("greater than zero", ctx.exception.message)

    def test_amount_above_balance_is_rejected_in_conversation(self) -> None:
        agent = Agent(today=date(2026, 4, 24))
        agent.next("ACC1002")
        agent.next("Rajarajeswari Balasubramaniam")
        agent.next("9876")
        agent.next("pay 1000")
        agent.next("name on card: Rajarajeswari Balasubramaniam")
        agent.next("4532015112830366")
        agent.next("cvv 123")
        failure = agent.next("12/2027")["message"]
        self.assertIn("outstanding balance", failure)
        self.assertIn("amount less than or equal", failure)

    def test_zero_balance_account_payment_attempt_is_rejected(self) -> None:
        agent = Agent(today=date(2026, 4, 24))
        agent.next("ACC1003")
        agent.next("Priya Agarwal")
        agent.next("1992-08-10")
        agent.next("pay 1")
        agent.next("name on card: Priya Agarwal")
        agent.next("4532015112830366")
        agent.next("cvv 123")
        failure = agent.next("12/2027")["message"]
        self.assertIn("outstanding balance", failure)
        self.assertIn("amount less than or equal", failure)

    def test_unknown_account_is_reported(self) -> None:
        agent = Agent(today=date(2026, 4, 24))
        message = agent.next("ACC9999")["message"]
        self.assertIn("No account found", message)

    def test_lookup_retry_limit_closes_conversation(self) -> None:
        agent = Agent(today=date(2026, 4, 24))
        self.assertIn("Attempts remaining: 2", agent.next("ACC9999")["message"])
        self.assertIn("Attempts remaining: 1", agent.next("ACC9998")["message"])
        final = agent.next("ACC9997")["message"]
        self.assertIn("multiple attempts", final)
        self.assertIn("closing this conversation", final)

    def test_secondary_factor_mismatch_is_reported(self) -> None:
        agent = Agent(today=date(2026, 4, 24))
        agent.next("ACC1001")
        agent.next("Nithin Jain")
        message = agent.next("400999")["message"]
        self.assertIn("secondary factor did not match", message)

    def test_non_numeric_cvv_is_rejected(self) -> None:
        agent = Agent(today=date(2026, 4, 24))
        agent.next("ACC1001")
        agent.next("Nithin Jain")
        agent.next("1990-05-14")
        agent.next("pay 100")
        agent.next("name on card: Nithin Jain")
        agent.next("4532 0151 1283 0366")
        failure = agent.next("cvv abc")["message"]
        self.assertIn("CVV must contain digits only", failure)
        self.assertIn("CVV again", failure)

    def test_card_number_with_dashes_is_accepted(self) -> None:
        agent = Agent(today=date(2026, 4, 24))
        agent.next("ACC1001")
        agent.next("Nithin Jain")
        agent.next("1990-05-14")
        agent.next("pay 100")
        agent.next("name on card: Nithin Jain")
        next_message = agent.next("4532-0151-1283-0366")["message"]
        self.assertIn("CVV", next_message)

    def test_amex_card_with_four_digit_cvv_is_accepted(self) -> None:
        api = InMemoryPaymentAPI()
        result = api.process_payment(
            account_id="ACC1001",
            amount="100",
            cardholder_name="Nithin Jain",
            card_number="378282246310005",
            cvv="1234",
            expiry_month=12,
            expiry_year=2027,
            today=date(2026, 4, 24),
        )
        self.assertTrue(result["success"])
        self.assertIn("TXN-", result["transaction_id"])

    def test_closed_conversation_stays_closed(self) -> None:
        agent = Agent(today=date(2026, 4, 24))
        agent.next("ACC1001")
        agent.next("Nithin Jain")
        agent.next("1990-05-14")
        agent.next("pay 100")
        agent.next("name on card: Nithin Jain")
        agent.next("4532015112830366")
        agent.next("cvv 123")
        agent.next("12/2027")
        closed = agent.next("anything else")["message"]
        self.assertIn("conversation is closed", closed)

    @patch("payment_agent.api.urllib.request.urlopen")
    def test_http_adapter_builds_expected_requests(self, mock_urlopen: MagicMock) -> None:
        lookup_response = MagicMock()
        lookup_response.read.return_value = json.dumps(
            {
                "account_id": "ACC1001",
                "full_name": "Nithin Jain",
                "dob": "1990-05-14",
                "aadhaar_last4": "4321",
                "pincode": "400001",
                "balance": "1250.75",
            }
        ).encode("utf-8")

        payment_response = MagicMock()
        payment_response.read.return_value = json.dumps(
            {"success": True, "transaction_id": "TXN-TEST-001"}
        ).encode("utf-8")

        mock_urlopen.side_effect = [
            MagicMock(__enter__=MagicMock(return_value=lookup_response), __exit__=MagicMock(return_value=False)),
            MagicMock(__enter__=MagicMock(return_value=payment_response), __exit__=MagicMock(return_value=False)),
        ]

        api = HttpPaymentAPI("https://example.com")
        account = api.lookup_account("ACC1001")
        self.assertEqual("ACC1001", account.account_id)

        lookup_request = mock_urlopen.call_args_list[0][0][0]
        self.assertEqual("POST", lookup_request.get_method())
        self.assertEqual(
            "https://example.com/api/lookup-account",
            lookup_request.full_url,
        )
        lookup_payload = json.loads(lookup_request.data.decode("utf-8"))
        self.assertEqual({"account_id": "ACC1001"}, lookup_payload)

        result = api.process_payment(
            account_id="ACC1001",
            amount="100",
            cardholder_name="Nithin Jain",
            card_number="4532015112830366",
            cvv="123",
            expiry_month=12,
            expiry_year=2027,
            today=date(2026, 4, 24),
        )
        self.assertTrue(result["success"])

        payment_request = mock_urlopen.call_args_list[1][0][0]
        self.assertEqual("POST", payment_request.get_method())
        self.assertEqual(
            "https://example.com/api/process-payment",
            payment_request.full_url,
        )
        payload = json.loads(payment_request.data.decode("utf-8"))
        self.assertEqual("ACC1001", payload["account_id"])
        self.assertEqual(100.0, payload["amount"])
        self.assertEqual("card", payload["payment_method"]["type"])

    @patch("payment_agent.api.urllib.request.urlopen")
    def test_http_adapter_handles_plain_text_http_errors(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = HTTPError(
            url="https://example.com/api/lookup-account",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=BytesIO(b"NOT_FOUND"),
        )

        api = HttpPaymentAPI("https://example.com")
        with self.assertRaises(PaymentAPIError) as ctx:
            api.lookup_account("ACC1001")

        self.assertEqual("API_ERROR", ctx.exception.code)
        self.assertEqual("NOT_FOUND", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
