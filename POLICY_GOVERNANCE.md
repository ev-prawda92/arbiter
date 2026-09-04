# Policy Governance

Active adjudication policy should not be edited in place. v0.12 adds a governed lifecycle:

**Draft → Submit → Independent Approval → Activate**

A draft records its base policy version, proposed weights/thresholds, creator, rationale, and hash. The creator cannot approve their own draft. Activation fails if the active base version changed after the draft was created, preventing stale-policy activation. Activation creates a new active version; historical resolution runs remain pinned to their original policy version.

Direct `POST /api/policy` remains available only for local-development backwards compatibility and is blocked in production mode.
