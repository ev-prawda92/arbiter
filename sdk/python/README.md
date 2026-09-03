# Arbiter Python SDK — Preview

No third-party dependency is required.

```python
from arbiter_sdk import Arbiter

arbiter = Arbiter(api_key="arb_dev_example")
result = arbiter.compile(
    "DEMO-CPI-001",
    "Will CPI be above 3.0% on Sep 11, 2026?",
    "Resolves YES if BLS CPI is above 3.0% on Sep 11, 2026 at 08:30 EDT. First release controls.",
)
print(result["status"])
```
