# Design Overview

## Architecture

The agent is implemented as a deterministic state machine with three major phases:

1. Account lookup
2. Identity verification
3. Payment collection and processing

`Agent.next()` performs one conversational turn at a time while preserving all state internally. The state lives in a `ConversationState` dataclass, which contains:

- The active stage
- Loaded account details
- Verification inputs and retry counters
- Payment inputs and retry counters

This keeps the interaction predictable for an LLM-style evaluator while still supporting natural user behavior such as out-of-order inputs.

## Key Decisions

### Rule-based control instead of an LLM

The assignment emphasizes determinism, tool timing, validation, and failure handling. A rule-based state machine is a better fit here than using an LLM because it:

- Produces repeatable results across runs
- Makes retry and safety rules explicit
- Keeps verification strict with no fuzzy matching
- Simplifies testing and automated evaluation

### API abstraction

The core agent talks to a `BasePaymentAPI` interface. Two implementations are provided:

- `InMemoryPaymentAPI`: default mode for deterministic local development
- `HttpPaymentAPI`: optional adapter for the provided remote API shape

This isolates business logic from transport concerns and lets the same agent run both locally and against a real service.

### Strict verification

Verification succeeds only if:

- `full_name` matches exactly
- At least one of `dob`, `aadhaar_last4`, or `pincode` also matches exactly

No fuzzy matching, case-insensitive fallback, or partial acceptance is used. Failed attempts are counted only when the user has provided enough information to evaluate a real verification attempt.

Verification failures are surfaced as plain-language mismatch messages in the user-visible flow, and missing accounts are handled through ordinary account-lookup errors.

### Payment validation semantics

The in-memory adapter mirrors the assignment's payment validation rules, including:

- card length checks
- checksum validation
- rejection of masked or partial card numbers
- numeric-only CVV checks with card-specific length rules
- expiry month/year validation
- expired-card rejection
- positive-amount validation with two-decimal precision

This makes local testing behave much closer to the expected evaluator behavior while preserving the separate HTTP adapter for real API-backed execution.

### Sensitive data handling

The agent never echoes:

- DOB
- Aadhaar digits
- Pincode
- Raw card number
- CVV

Card data is collected only when needed for the payment step and is only used for the payment API invocation.

## Tradeoffs

- The parser is intentionally heuristic and simple rather than fully NLU-driven. This improves predictability but means unusual phrasing may be handled less gracefully than a model-backed system.
- The default in-memory API does not mutate balances between requests because the assignment notes that the reference server does not persist balance changes.
- The agent allows early collection of later-step fields, but it never skips verification before payment.

## Retry Policy

- Account lookup: 3 attempts
- Verification: 3 attempts
- User-fixable payment issues: 3 attempts

Once a retry limit is hit, the conversation closes cleanly.

## Improvements With More Time

- Stronger free-form entity extraction
- More nuanced handling of ambiguous mixed-input turns
- Richer evaluator metrics and transcript scoring
- Structured redaction utilities for observability in production
