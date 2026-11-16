"""
Round 8, Part B: repair and replay. Was the knowledge base involved?

Poisoned passages enter by the normal ingestion path, so every hash checks out
and no witness in the record can fire on them. When the knowledge base is
poisoned in the same decision as a component fault, the component's alarm fires
and seems to explain the bad decision. The only signal left for the library is
behavioural: change something, replay the production model, and see whether the
decision becomes the one the complainant says was right.

What the investigator is given (and nothing else):

  the record          sigma, the round 8 candidate (sigma_r8)
  the archive         passage snapshot, content store, registered prompt,
                      policy and tool description, and offline re-retrieval
                      over the snapshot (with passages left out, for step 4)
  the dispute         the released output, and a test of whether a released
                      output is the decision the complainant says was right
                      (Assumption A-D; in HotpotQA the gold answer stands in)
  replay              the production model at the recorded configuration, the
                      registered policy, and the registered tool re-invoked
                      with the recorded request (Assumption A-R)

The investigator never sees the sealed fault log. This module must not import
sealing, faults or attacks.

Procedure, as registered in PREREG_round8.md:

  1. Collect every alarm the record raises (verify_all).
  2. Repair each alarmed component with its value of record and replay:
       F_R  passages re-retrieved over the archived snapshot
       F_X  the context rebuilt from the registered template (it always is:
            a hash-only record cannot reproduce the faulty context)
       F_T  the registered tool re-invoked with the recorded arguments, and the
            registered description. The store holds what the pipeline
            received, which for an impostor is the impostor's response.
       F_P  the policy of record applied to the replayed output
  3. If the repaired replay gives the claimed decision, the partner explains
     it. Step 4 then runs with the partner left faulty, to catch a joint cause
     (run 26). If the faulty state cannot be rebuilt, the verdict is partner.
  4. Take passages out of the LIBRARY, not just out of the prompt: re-retrieve
     over the snapshot without them, so that what they displaced comes back
     (a planted passage that pushed the gold out of the top k is the common
     case). In order: every set of one or two recorded passages; then peeling
     (take out the top passage, re-retrieve, take out the new top one, up to
     five deep, which reaches a dose larger than k); then larger sets of every
     passage seen, until the replay budget is spent. Stop at the first replay
     that gives the claimed decision. Found: the library contributed (jointly
     with the partner if step 3 also succeeded).
  5. Otherwise: unexplained.

Before step 2 the faulty state is replayed in full and must reproduce the
disputed decision; if it does not, the investigator abstains (not_reproduced).
That check is skipped when the faulty state cannot be rebuilt (an F_X alarm on a
hash-only record).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple

from .verifier import Archive, _shown_description, _tool_call, verify_all

LIBRARY = ("library", "library_joint")
DEFAULT_BUDGET = 40          # replays per dispute, registered
MAX_REMOVAL = 5              # largest set of passages taken out at once


@dataclass
class ReplayEnv:
    """What replay gives the investigator (Assumption A-R)."""
    generate: Callable[[str, Dict[str, Any]], str]   # (prompt, theta) -> raw output
    render_context: Callable[..., str]                # the registered template
    apply_policy_of_record: Callable[[str], str]      # raw output -> released output
    tool_replay: Callable[[str, Dict[str, Any]], Any]  # (x_hash, args) -> genuine value
    registered_description: str


@dataclass
class Finding:
    verdict: str                 # partner | library | library_joint | unexplained
                                 # | not_reproduced | no_input
    alarms: Tuple[str, ...]
    partner_explains: Optional[bool] = None
    joint_testable: Optional[bool] = None
    reproduced: Optional[bool] = None
    removed: Optional[Tuple[str, ...]] = None    # content hashes taken out
    replays: int = 0
    budget_spent: bool = False
    note: str = ""

    @property
    def library_flagged(self) -> bool:
        return self.verdict in LIBRARY


@dataclass
class _State:
    hashes: List[str]                       # passages as recorded or repaired
    exclude: FrozenSet[str]                 # passages the (faulty) retriever lost
    tool: Optional[Tuple[str, str, str, Any]]
    raw_policy: bool                        # release the raw output (F_P left in)


class _Budget(Exception):
    pass


def investigate(sigma, arc: Archive, disputed_output: str,
                claimed_ok: Callable[[str], bool], env: ReplayEnv,
                budget: int = DEFAULT_BUDGET) -> Finding:
    vs = verify_all(sigma, arc)
    alarms = tuple(sorted(vs.classes))
    f = Finding(verdict="unexplained", alarms=alarms)

    if not (sigma.has("x_hash") and sigma.has("z_hashes") and sigma.has("theta")):
        f.verdict, f.note = "no_input", "record lacks input, retrieval set or theta"
        return f
    x_hash = sigma.get("x_hash")
    question = arc.query_text_by_hash.get(x_hash)
    if question is None:
        f.verdict, f.note = "no_input", "input text not in the archive"
        return f
    theta = dict(sigma.get("theta"))
    status, tc = _tool_call(sigma, arc)
    if status == "unavailable":
        f.verdict, f.note = "no_input", "tool response absent from the store"
        return f

    # --- the recorded (faulty) state and the repaired one -----------------------
    recorded = list(sigma.get("z_hashes"))
    rec_tool = ((tc["tool"], tc["version"], _shown_description(sigma, arc),
                 tc["returned"]["value"]) if status == "ok" else None)
    expected = arc.reretrieve(x_hash) if arc.reretrieve is not None else None
    lost = frozenset(set(expected or []) - set(recorded)) if "F_R" in alarms else frozenset()
    faulty_ok = all(h in arc.doc_text_by_hash for h in recorded) and "F_X" not in alarms
    faulty = _State(recorded, lost, rec_tool, raw_policy="F_P" in alarms)

    hashes = recorded
    if "F_R" in alarms and arc.reretrieve_excluding is not None:
        hashes = arc.reretrieve_excluding(x_hash, set()) or recorded
    tool = rec_tool
    if "F_T" in alarms and tc is not None:
        tool = (tc["tool"], tc["version"], env.registered_description,
                env.tool_replay(x_hash, tc.get("args", {})))
    repaired = _State([h for h in hashes if h in arc.doc_text_by_hash], frozenset(),
                      tool, raw_policy=False)

    def retrieve(state: _State, drop: FrozenSet[str]) -> List[str]:
        if not drop:
            return [h for h in state.hashes if h in arc.doc_text_by_hash]
        if arc.reretrieve_excluding is not None:
            got = arc.reretrieve_excluding(x_hash, set(drop) | set(state.exclude)) or []
            return [h for h in got if h in arc.doc_text_by_hash]
        return [h for h in state.hashes if h not in drop and h in arc.doc_text_by_hash]

    def run(state: _State, drop: FrozenSet[str] = frozenset()) -> Tuple[str, List[str]]:
        if f.replays >= budget:
            raise _Budget()
        f.replays += 1
        hs = retrieve(state, drop)
        raw = env.generate(env.render_context(question, [arc.doc_text_by_hash[h] for h in hs],
                                              state.tool), theta)
        return (raw if state.raw_policy else env.apply_policy_of_record(raw)), hs

    try:
        # --- reproduction ---------------------------------------------------------
        if faulty_ok:
            out, _ = run(faulty)
            f.reproduced = claimed_ok(out) == claimed_ok(disputed_output)
            if not f.reproduced:
                f.verdict = "not_reproduced"
                return f

        # --- steps 2-3: repair the alarmed components -------------------------------
        if alarms:
            out, _ = run(repaired)
            f.partner_explains = claimed_ok(out)
        else:
            f.partner_explains = False
        if f.partner_explains:
            f.joint_testable = faulty_ok
            if not faulty_ok:
                f.verdict = "partner"
                f.note = "joint cause not testable (faulty state not rebuildable)"
                return f
            state = faulty
        else:
            state = repaired

        # --- step 4: take passages out of the library ----------------------------
        # (a) every set of one or two recorded passages; (b) peeling: take out
        # the top-ranked passage, re-retrieve, take out the new top one, up to
        # MAX_REMOVAL deep, which reaches a dose larger than k; (c) larger sets
        # of every passage seen so far, until the budget is spent.
        tried = set()

        def attempt(drop) -> bool:
            key = frozenset(drop)
            if not key or key in tried:
                return False
            tried.add(key)
            out, hs = run(state, key)
            for h in hs:
                if h not in pool:
                    pool.append(h)
            if claimed_ok(out):
                f.removed = tuple(drop)
                f.verdict = "library_joint" if f.partner_explains else "library"
                return True
            return False

        pool = list(dict.fromkeys(state.hashes))
        for size in (1, 2):
            for drop in combinations(list(state.hashes), size):
                if attempt(drop):
                    return f
        peeled: List[str] = []
        current = list(state.hashes)
        for _ in range(MAX_REMOVAL):
            if not current:
                break
            peeled.append(current[0])
            if attempt(peeled):
                return f
            current = retrieve(state, frozenset(peeled))
        for size in range(3, MAX_REMOVAL + 1):
            for drop in combinations(list(pool), size):
                if attempt(drop):
                    return f
    except _Budget:
        f.budget_spent = True
    f.verdict = "partner" if f.partner_explains else "unexplained"
    return f
