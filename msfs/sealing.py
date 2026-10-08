"""
Sealed ground truth.

The scientific claim of this experiment rests on one thing: the ground truth was
fixed BEFORE the pipeline ran and could not be retrofitted to match what the
verifier said. So the injection log is hash-chained in the Haber-Stornetta /
Nitro style, each record committed before its execution, and the chain head is
checked at analysis time.

Blinding is enforced structurally: the verifier module never imports this one,
and `SealedLog.records` is only reachable through `open_for_scoring()`, which is
called after all verdicts are collected.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict

from .util import sha256
from pathlib import Path
from typing import Any, Dict, List, Optional

GENESIS = "0" * 64





@dataclass(frozen=True)
class InjectionRecord:
    injection_id: str
    execution_id: str
    fault_class: str           # F_R | F_X | F_T | F_P | NONE
    variant: str
    params: Dict[str, Any]
    timestamp: float
    prev_hash: str
    record_hash: str

    @staticmethod
    def _digest(payload: Dict[str, Any]) -> str:
        return sha256(json.dumps(payload, sort_keys=True, default=str))


class SealedLog:
    """Append-only, hash-chained. Sealing happens before execution, always."""

    def __init__(self) -> None:
        self._records: List[InjectionRecord] = []
        self._head = GENESIS
        self._open = False

    @property
    def head(self) -> str:
        return self._head

    def seal(
        self,
        execution_id: str,
        fault_class: str,
        variant: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> InjectionRecord:
        params = params or {}
        payload = {
            "injection_id": f"inj-{len(self._records):06d}",
            "execution_id": execution_id,
            "fault_class": fault_class,
            "variant": variant,
            "params": params,
            "timestamp": time.time(),
            "prev_hash": self._head,
        }
        rec = InjectionRecord(**payload, record_hash=InjectionRecord._digest(payload))
        self._records.append(rec)
        self._head = rec.record_hash
        return rec

    def verify_chain(self) -> bool:
        prev = GENESIS
        for rec in self._records:
            payload = {k: v for k, v in asdict(rec).items() if k != "record_hash"}
            if rec.prev_hash != prev:
                return False
            if InjectionRecord._digest(payload) != rec.record_hash:
                return False
            prev = rec.record_hash
        return prev == self._head

    def open_for_scoring(self) -> Dict[str, InjectionRecord]:
        """Call ONLY after every verdict is in. Raises if the chain is broken."""
        if not self.verify_chain():
            raise RuntimeError("sealed injection log failed chain verification")
        self._open = True
        return {r.execution_id: r for r in self._records}

    def write(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {"head": self._head, "records": [asdict(r) for r in self._records]},
                indent=2,
                default=str,
            )
        )
