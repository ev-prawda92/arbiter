#!/usr/bin/env python3
"""Auditor key tool (standard library only). Run on the auditor's own machine;
the secret key never leaves it.

    python3 sign.py keygen auditor.key          # prints your public key; give it to Arbiter when opening an engagement
    python3 sign.py sign auditor.key <report_hash>   # prints the signature to paste at sign-off
    python3 sign.py pubkey auditor.key          # prints the public key again

Signs the message  "arbiter-audit-report:" + report_hash.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ed25519  # noqa: E402

MESSAGE_PREFIX = "arbiter-audit-report:"


def load(path: str) -> bytes:
    return bytes.fromhex(open(path).read().strip())


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "keygen":
        if os.path.exists(argv[1]):
            print(f"{argv[1]} already exists; not overwriting", file=sys.stderr)
            return 1
        secret = ed25519.new_secret()
        fd = os.open(argv[1], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(secret.hex() + "\n")
        print(ed25519.public_key(secret).hex())
        return 0
    if len(argv) >= 2 and argv[0] == "pubkey":
        print(ed25519.public_key(load(argv[1])).hex())
        return 0
    if len(argv) >= 3 and argv[0] == "sign":
        print(ed25519.sign(load(argv[1]), (MESSAGE_PREFIX + argv[2]).encode()).hex())
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
