# Arbiter v0.19 — Reference Exchange & End-to-End Settlement Harness

Adds a deliberately small, play-money reference venue that exercises Arbiter's full lifecycle without creating a real-money exchange.

- play-money accounts and binary YES/NO positions
- contract semantics + compiler gate before market opening
- non-ready contracts fail safely to HELD
- sandbox resolution and payout ledger
- content-hashed settlement packet
- complete audit events
- tenant-scoped reference venue records
- no custody, KYC, real-money trading, or production matching engine
- reference exchange posture and API endpoints
- automated reference-exchange release gate

The reference venue is a validation harness, not a regulated exchange or consumer trading product.
