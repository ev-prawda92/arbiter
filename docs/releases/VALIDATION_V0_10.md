# Arbiter v0.10 Validation Snapshot

Validated on the packaged reference implementation before release:

- v0.9.5 coherence regression: **48/48 PASS**
- v0.10 enterprise boundary gate: **14/14 PASS**
- Production-mode authentication gate: unauthenticated protected request -> **401**
- Production-mode valid hashed admin key -> protected read **200**
- Production-mode insufficient-scope key -> privileged mutation **403**
- Production-mode hashed admin key -> privileged benchmark mutation **200**
- Production readiness gate -> **200** under explicit auth and CORS configuration

These results demonstrate the tested application behavior above. They are not a penetration test, SOC 2 report, regulatory certification, or proof of complete production security.
