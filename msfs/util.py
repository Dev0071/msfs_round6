"""Shared primitives, kept separate so the verifier need not import the sealing
module. The blinding claim in verifier.py should stay literally true."""
from __future__ import annotations

import hashlib


def sha256(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()
