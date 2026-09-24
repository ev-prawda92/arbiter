# Reference Exchange

Arbiter's reference exchange is a play-money integration harness used to prove the contract-to-settlement lifecycle end to end.

It intentionally excludes real-money custody, KYC, brokerage, clearing, and a production matching engine. A market may open only when Arbiter's compiler returns READY; REVIEW/BLOCK contracts remain HELD. Successful sandbox settlement produces a deterministic payout ledger, settlement hash, and audit events.
