"""
Adjudication policy.

This is the 'governed configurability' surface. The exchange's team owns the knobs
(lever weights, hold thresholds), but every change is versioned and written to a
change log. That is what preserves the independence claim: the policy can be tuned,
but never quietly. Arbiter observes and reports; it does not set payout terms and it
does not change policy on its own.
"""

import json
import os
from datetime import datetime, timezone

_DATA = os.path.join(os.path.dirname(__file__), "..", "data", "policy.json")

DEFAULT_POLICY = {
    "version": "2026.08.24-1",
    "weights": {"source": 0.30, "timing": 0.30, "definition": 0.40},
    "thresholds": {"clean": 20, "monitored": 50},
    "changelog": [
        {"version": "2026.08.24-1", "at": "2026-08-24T00:00:00Z",
         "by": "arbiter.default",
         "note": "Initial policy. Definition weighted highest — interpretive "
                 "ambiguity is the most common driver of disputed resolutions."},
    ],
}


def load_policy():
    try:
        with open(_DATA) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        save_policy(DEFAULT_POLICY)
        return DEFAULT_POLICY


def save_policy(policy):
    os.makedirs(os.path.dirname(_DATA), exist_ok=True)
    with open(_DATA, "w") as f:
        json.dump(policy, f, indent=2)


def update_policy(new_weights=None, new_thresholds=None, by="exchange.admin", note=""):
    """Apply a governed change: mutate, bump version, append to the immutable log."""
    policy = load_policy()
    if new_weights:
        policy["weights"].update(new_weights)
    if new_thresholds:
        policy["thresholds"].update(new_thresholds)
    stamp = datetime.now(timezone.utc)
    policy["version"] = stamp.strftime("%Y.%m.%d") + f"-{len(policy['changelog']) + 1}"
    policy["changelog"].append({
        "version": policy["version"],
        "at": stamp.isoformat(),
        "by": by,
        "note": note or "policy updated",
        "weights": dict(policy["weights"]),
        "thresholds": dict(policy["thresholds"]),
    })
    save_policy(policy)
    return policy
