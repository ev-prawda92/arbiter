# Enterprise Secrets, Model Administration & Identity Federation

Arbiter v0.18 treats AI provider access and enterprise identity as governed control-plane resources.

## Secret custody
- Provider secrets are write-only through Arbiter APIs.
- Application responses expose masked metadata and a SHA-256 fingerprint, never the raw credential or storage reference.
- Local development uses Fernet encryption with a local master key under `backend/data/.local_secret_master_key`.
- Production requires an external secret backend. The reference adapter uses AWS Secrets Manager and supports a customer-managed KMS key through `ARBITER_KMS_KEY_ID`.

## Model-provider policy
Each tenant can govern provider, default/fast models, allowed purposes, call limits, and enabled/disabled state. The Model Intelligence Gateway resolves tenant configuration before falling back to environment configuration.

## OIDC
The federation layer supports signed bearer tokens validated against configured issuer/audience/JWKS. Claims are mapped to Arbiter principal, tenant, and scope context before request handling.

## Non-authority rule
Model access is not settlement authority. Identity grants only the scopes assigned by policy; settlement authorization continues to require the existing governed approval path.
