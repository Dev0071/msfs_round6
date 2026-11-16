"""
Signing keys, one per trust domain, and the HMAC used with them.

Round 8 change. Before round 8 every "signature" was sha256(key + payload): a
keyed hash with the key as a prefix, which is open to length extension and is
not a MAC. Every signature is now HMAC-SHA256.

These are shared secrets, so whoever verifies a tag could also forge one. That
is acceptable in the harness, where the investigator is not an adversary. In a
deployment the tool service and the witness would sign with public-key
signatures (for example Ed25519) and the investigator would hold only the
public keys. The paper says so.

Trust domains, and who holds each key:

  tool       the registered tool service. Signs every response it returns
             (Assumption A-T). The pipeline never holds this key.
  witness    the policy-witness wrapper: a process outside the output filter
             that observes the filter and signs what it saw. The filter never
             holds this key (assumption K1 / A-P).
  attacker   an impostor tool server. Signs with its own key, which does not
             verify against the registered tool's.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

TOOL_KEY = b"tool-service-signing-key-2026"
WITNESS_KEY = b"policy-witness-wrapper-key-2026"
ATTACKER_KEY = b"attacker-server-signing-key"


def sign(key: bytes, payload: str) -> str:
    return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify(key: bytes, payload: str, tag: str) -> bool:
    return hmac.compare_digest(sign(key, payload), str(tag or ""))


def canonical(obj: Any) -> str:
    """Deterministic serialisation for signing and for content addressing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
