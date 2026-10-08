"""
The integrity layer: INTEGRITY(tau, sigma) of Section 6.1, as code.

v8 specifies seven clauses and the pilots implemented one of them (BIND, as
the verifier's recomputation). This module implements six:

  WF     the record conforms to a versioned schema: every required element of
         the candidate record is present.
  CHAIN  each entry commits to its predecessor (Haber-Stornetta linking); the
         entry hash recomputes; sequence numbers run 0, 1, 2, ... with no gap.
  AUTH   each entry carries a forward-secure MAC (Schneier-Kelsey key
         evolution): entry i is tagged with k_i, then k_{i+1} = H(k_i) and k_i
         is erased. An attacker who steals the logger's key at time t learns
         k_t and every later key, but cannot compute any earlier key, so cannot
         re-tag entries written before t.
  FRESH  the chain head is published to an external witness every
         ANCHOR_EVERY entries and at shutdown; the auditor checks the log
         against every published head, which defeats truncation and rollback
         of anchored entries.
  BIND   recomputable relations hold: the context commitment c_hash
         recomputes from the recorded input hash, passage hashes, tool
         transcript and the registered template.
  CLASS  the output commitment opens: a disputed output o is accepted only if
         a sealed entry has h(o) = y_hash and delta(o) = y_class
         (event authenticity: "no such execution" otherwise).

  ATTEST (capture pipeline measured by a TEE) is NOT implemented. Without it,
         a logger that lies at capture time is out of the model: see the
         out-of-model attacks in exp_integrity.py.

Primitives are HMAC-SHA256 and SHA-256 from the standard library. A deployment
would use an asymmetric signature on anchors as well; HMAC is enough to test
the clause logic, which is what is being measured.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .pipeline import decision_class
from .state import Sigma
from .util import sha256

SCHEMA_VERSION = "msfs-record/1"
GENESIS = "0" * 64
ANCHOR_EVERY = 16
CLAUSES = ("WF", "CHAIN", "AUTH", "FRESH", "BIND", "CLASS")


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def evolve(key: bytes) -> bytes:
    """One-way key update. Knowing k_{i+1} gives no way back to k_i."""
    return hashlib.sha256(b"msfs-evolve|" + key).digest()


def key_at(k0: bytes, i: int) -> bytes:
    k = k0
    for _ in range(i):
        k = evolve(k)
    return k


def mac(key: bytes, entry_hash: str) -> str:
    return hmac.new(key, entry_hash.encode(), hashlib.sha256).hexdigest()


def entry_hash(body: Dict[str, Any]) -> str:
    return sha256(canonical(body))


def make_entry(seq: int, prev: str, record: Dict[str, Any], key: bytes,
               schema: str = SCHEMA_VERSION) -> Dict[str, Any]:
    body = {"schema": schema, "seq": seq, "prev": prev, "record": record}
    h = entry_hash(body)
    return {**body, "hash": h, "tag": mac(key, h)}


class SecureLog:
    """The logger. Holds only the current key; earlier keys are gone."""

    def __init__(self, k0: bytes, witness: List[Tuple[int, str]],
                 anchor_every: int = ANCHOR_EVERY):
        self._key = k0
        self.entries: List[Dict[str, Any]] = []
        self.head = GENESIS
        self.witness = witness              # external, append-only, auditor-readable
        self.anchor_every = anchor_every

    @property
    def current_key(self) -> bytes:
        """What an attacker who compromises the logger now obtains."""
        return self._key

    def append(self, record: Dict[str, Any]) -> Dict[str, Any]:
        e = make_entry(len(self.entries), self.head, record, self._key)
        self.entries.append(e)
        self.head = e["hash"]
        self._key = evolve(self._key)
        if len(self.entries) % self.anchor_every == 0:
            self.anchor()
        return e

    def anchor(self) -> None:
        if not self.witness or self.witness[-1][0] != len(self.entries):
            self.witness.append((len(self.entries), self.head))


# --- the auditor ------------------------------------------------------------------

@dataclass
class AuditResult:
    failures: Dict[str, List[str]] = field(default_factory=dict)

    def fail(self, clause: str, why: str) -> None:
        self.failures.setdefault(clause, []).append(why)

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def clauses(self) -> List[str]:
        return [c for c in CLAUSES if c in self.failures]


def audit(entries: List[Dict[str, Any]], k0: bytes,
          witness: List[Tuple[int, str]], required: frozenset,
          bind_check=None) -> AuditResult:
    """
    INTEGRITY over a whole log. `required` is the element set of the candidate
    record (WF). `bind_check(record) -> bool` recomputes the BIND relations.
    The auditor holds k0 (escrowed at setup) and reads the external witness.
    """
    res = AuditResult()
    prev, key = GENESIS, k0
    for i, e in enumerate(entries):
        # WF
        if e.get("schema") != SCHEMA_VERSION or not isinstance(e.get("record"), dict):
            res.fail("WF", f"entry {i}: schema")
        else:
            missing = [x for x in required if x not in e["record"]]
            if missing:
                res.fail("WF", f"entry {i}: missing {missing}")
        # CHAIN
        body = {k: e.get(k) for k in ("schema", "seq", "prev", "record")}
        if e.get("seq") != i:
            res.fail("CHAIN", f"entry {i}: seq {e.get('seq')}")
        if e.get("prev") != prev:
            res.fail("CHAIN", f"entry {i}: broken link")
        if entry_hash(body) != e.get("hash"):
            res.fail("CHAIN", f"entry {i}: hash does not recompute")
        # AUTH: the tag must verify under the key for this position
        if not hmac.compare_digest(mac(key, str(e.get("hash"))), str(e.get("tag"))):
            res.fail("AUTH", f"entry {i}: tag does not verify under k_{i}")
        # BIND
        if bind_check is not None and isinstance(e.get("record"), dict):
            if not bind_check(e["record"]):
                res.fail("BIND", f"entry {i}: context commitment does not recompute")
        prev, key = e.get("hash"), evolve(key)
    # FRESH: every published head must be present at its position
    for n, head in witness:
        if n > len(entries):
            res.fail("FRESH", f"witness anchored {n} entries, log has {len(entries)}")
        elif entries[n - 1].get("hash") != head:
            res.fail("FRESH", f"head at {n} differs from the published anchor")
    return res


def authenticate_event(entries: List[Dict[str, Any]], x_hash: str,
                       disputed_output: str) -> Optional[int]:
    """CLASS: the index of the sealed entry for (x, o), or None ('no such execution')."""
    yh = sha256(disputed_output)
    for i, e in enumerate(entries):
        r = e.get("record", {})
        if r.get("x_hash") == x_hash and r.get("y_hash") == yh \
           and r.get("y_class") == decision_class(disputed_output):
            return i
    return None


def make_bind_check(arc):
    """BIND for a commitment-only record: c_hash recomputes from what is recorded."""
    from .verifier import _canonical_prompt

    def check(record: Dict[str, Any]) -> bool:
        sigma = Sigma("audit", dict(record))
        if "c_hash" not in record:
            return False
        canon = _canonical_prompt(sigma, arc)
        if canon is None:
            # a passage hash outside the archive: provenance is the verifier's
            # F_R question, not an integrity failure
            return True
        return sha256(canon) == record["c_hash"]
    return check


def clone(entries):
    return copy.deepcopy(entries)
