# Sample Conversations

## Successful Flow

User: hello
Agent: Hello! Please share your account ID to get started with the payment collection flow.

User: ACC1001
Agent: Thanks. I found the account. Please confirm your full name exactly as on the account.

User: Nithin Jain
Agent: Please verify either your date of birth (`YYYY-MM-DD`), Aadhaar last 4 digits, or pincode.

User: 1990-05-14
Agent: Identity verified. Your outstanding balance is INR 1250.75. Please share the payment amount you would like to pay.

User: pay 500
Agent: Please share the cardholder name exactly as it appears on the card.

User: name on card: Nithin Jain
Agent: Please share the card number using digits only.

User: 4532015112830366
Agent: Please share the card CVV.

User: cvv 123
Agent: Please share the card expiry in `MM/YYYY` format.

User: 12/2027
Agent: Payment successful for INR 500.00. Your transaction ID is `TXN-000001`. This conversation is now complete.

## Verification Failure

User: ACC1001
Agent: Thanks. I found the account. Please confirm your full name exactly as on the account.

User: Wrong Name
Agent: Please verify either your date of birth (`YYYY-MM-DD`), Aadhaar last 4 digits, or pincode.

User: 400001
Agent: Verification failed because the full name did not match exactly. Please re-enter the exact full name. Attempts remaining: 2.

## Payment Failure

User: ACC1002
Agent: Thanks. I found the account. Please confirm your full name exactly as on the account.

User: Rajarajeswari Balasubramaniam
Agent: Please verify either your date of birth (`YYYY-MM-DD`), Aadhaar last 4 digits, or pincode.

User: 9876
Agent: Identity verified. Your outstanding balance is INR 540.00. Please share the payment amount you would like to pay.

User: pay 500
Agent: Please share the cardholder name exactly as it appears on the card.

User: name on card: Rajarajeswari Balasubramaniam
Agent: Please share the card number using digits only.

User: 4111111111111111
Agent: Please share the card CVV.

User: cvv 123
Agent: Please share the card expiry in `MM/YYYY` format.

User: 01/2020
Agent: Payment failed. Card has expired. Please share a valid expiry date.
