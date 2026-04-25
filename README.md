# Payment Collection Agent

This project implements the assignment's required `Agent` interface for a deterministic, multi-turn payment collection flow.

## Setup

```bash
python3 -m unittest discover -s tests -v
python3 cli.py
```

Optional Streamlit frontend:

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Files

- `agent.py`: required import surface for the evaluator.
- `payment_agent/`: agent logic, validators, state, and API adapters.
- `tests/test_agent.py`: automated coverage for success, verification failure, payment failure, out-of-order input, and core validation edge cases.
- `evaluate.py`: simple transcript-style evaluator.
- `streamlit_app.py`: simple web chat frontend built with Streamlit.
- `DESIGN.md`: architecture and tradeoffs.
- `sample_conversations.md`: example conversations.

## Runtime Modes

This project supports two runtime modes:

1. In-memory mode
2. HTTP mode

### In-memory mode

This is the default mode. It uses local sample account data and local payment validation logic, so it is best for:

- deterministic local development
- running tests
- debugging the conversation flow without depending on a network service

Run it with:

```bash
python3 cli.py
```

### HTTP mode

HTTP mode is the integration mode for the assignment when you want the agent to call the provided remote API instead of the local in-memory adapter.

In this mode:

- account lookup is sent to the remote API
- payment processing is sent to the remote API
- the agent still controls the conversation flow, validation sequence, retries, and messaging

To run in HTTP mode:

```bash
export PAYMENT_API_MODE=http
export PAYMENT_API_BASE_URL='YOUR_API_BASE_URL_HERE'
python3 cli.py
```

If your evaluator or assignment provides a specific API endpoint, set that value in `PAYMENT_API_BASE_URL` before running the app.

### What `PAYMENT_API_MODE` does

`PAYMENT_API_MODE` tells the agent which backend to use:

- if unset, it uses the local `InMemoryPaymentAPI`
- if set to `http`, it uses `HttpPaymentAPI`

### What `PAYMENT_API_BASE_URL` does

`PAYMENT_API_BASE_URL` is the root URL of the remote payment service.

The code uses this base URL to build the full API endpoints for:

- account lookup
- payment processing

For example, the code combines:

- base URL: `https://example-service.com`
- path: `/openapi/0/34/api/lookup-account`

to make the final request URL.

If `PAYMENT_API_MODE` is not set to `http`, the base URL is not used.

## Notes

- Verification is strict: full name must match exactly, and at least one of DOB, Aadhaar last 4, or pincode must also match.
- The agent stores conversation state between `next()` calls and supports out-of-order user input without skipping workflow steps.
- Raw card details are used only for the payment call and are never echoed back in responses.
- For assignment-style integration, use HTTP mode with the provided API base URL. For local development and tests, use the default in-memory mode.
- The local validation layer covers account lookup failures, verification mismatches, invalid card length, checksum failure, masked or partial card numbers, invalid CVV input, invalid expiry values, expired cards, and invalid payment amounts.
