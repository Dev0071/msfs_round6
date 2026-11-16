#!/usr/bin/env python3
"""
Round 8 acceptance checks. Run before registering; every check must pass.

  python tests_round8.py

Mock backend, synthetic corpus, no model needed. These check the apparatus,
not the hypotheses.
"""

from __future__ import annotations

import random
import sys

from msfs import attacks, keys, pipeline
from msfs.attacks import CompositeFault
from msfs.backends import make_backend
from msfs.pipeline import Fault, apply_policy, build_corpus, call_tool, execute, render_context
from msfs.real_world import project_with_derivation
from msfs.replay import ReplayEnv, investigate
from msfs.scoring import make_check
from msfs.state import SIGMA_R8
from msfs.util import sha256
from msfs.verifier import verify_all
from run_experiment import build_archive
from run_realworld import pick_restricted
from run_round8 import CLASSES, VARIANT, eligible

FAILS = []


def check(name, ok, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def main() -> int:
    pipeline.set_answer_format("short")
    docs, queries = build_corpus(seed=7)
    values, restricted = pick_restricted(queries, docs, random.Random(8))
    pipeline.register_restricted(values)
    arc = build_archive(docs, queries, "archive+retriever", None, 4)
    arc.require_witness_tag = True
    arc.cross_source_check = False
    backend = make_backend("mock")
    answer = make_check("substring")

    def run(q, classes, variants=None, seed=11):
        variants = variants or [VARIANT[c] for c in classes]
        f = (CompositeFault([attacks.make_attack(c, random.Random(0), v)
                             for c, v in zip(classes, variants)],
                            member_seeds=[seed + i for i in range(len(classes))])
             if classes else Fault())
        theta = {"temperature": 0.0, "top_p": 1.0, "max_tokens": 64, "seed": seed}
        tau = execute(q, docs, backend, f, random.Random(seed), theta,
                      gen_rng=random.Random(seed + 7), top_k=4, answer_check=answer,
                      signed_witness=True)
        arc.blob_by_hash.update(tau["_store"])
        ing = getattr(f, "ingested", [])
        for d in ing:
            arc.doc_text_by_hash[d.content_hash] = d.text
            arc.snapshot[d.doc_id] = d
        sig = project_with_derivation(tau, SIGMA_R8)
        got = verify_all(sig, arc)
        for d in ing:
            arc.doc_text_by_hash.pop(d.content_hash, None)
            arc.snapshot.pop(d.doc_id, None)
        return tau, sig, got, f

    def pick(classes):
        return next(q for q in queries if eligible(q, classes, restricted))

    # 1. clean runs raise no alarm
    alarms = [run(q, [])[2].classes for q in queries[:12]]
    check("clean runs raise no alarm", all(not a for a in alarms), str(alarms))

    # 2. each single component fault gives exactly its own class
    for c in ["F_R", "F_X", "F_T", "F_P"]:
        got = run(pick([c]), [c])[2].classes
        check(f"single {c} gives exactly {{{c}}}", got == {c}, str(set(got)))

    # 3. poisoned data alone blames no component
    got = run(pick(["F_D"]), ["F_D"])[2].classes
    check("single F_D blames no component", not got, str(set(got)))

    # 4. rug pull: F_T only (the explain-away rule), not F_T and F_X
    got = run(pick(["F_T"]), ["F_T"], ["rug_pull"])[2].classes
    check("rug pull gives F_T only", got == {"F_T"}, str(set(got)))

    # 5. a runtime pair trips both witnesses
    for pair in (["F_R", "F_X"], ["F_X", "F_T"], ["F_T", "F_P"]):
        got = run(pick(pair), pair)[2].classes
        check(f"pair {'+'.join(pair)} names both", got == set(pair), str(set(got)))

    # 6. only the policy member touches the witness
    q = pick(["F_X", "F_P"])
    w_pair = run(q, ["F_X", "F_P"])[0]["p_witness"]
    w_alone = run(q, ["F_P"])[0]["p_witness"]
    check("F_X+F_P witness equals F_P alone", w_pair == w_alone)
    w_x = run(pick(["F_X"]), ["F_X"])[0]["p_witness"]
    check("F_X alone leaves an honest, verifying witness",
          w_x["heartbeat"] and keys.verify(keys.WITNESS_KEY, pipeline.witness_payload(w_x),
                                           w_x["tag"]))

    # 7. a member draws the same wrong answer alone and in a pair
    q = pick(["F_X", "F_D"])
    t1, _, _, f1 = run(q, ["F_X", "F_D"])
    t2, _, _, f2 = run(q, ["F_D"])
    p1 = f1.member_params()["F_D"].get("poison_hashes")
    p2 = f2.member_params()["F_D"].get("poison_hashes")
    check("poison identical in pair and single", p1 == p2 and bool(p1))

    # 8. forged witness and lying filter
    q = pick(["F_P"])
    got = run(q, ["F_P"], ["forged_witness"])[2]
    check("forged witness raises F_P (tag does not verify)",
          "F_P" in got.classes and any("does not verify" in e for e in got.evidence),
          str(got.evidence))
    tau, sig, got, _ = run(q, ["F_P"], ["lying_filter"])
    if tau["_released_violation"]:
        check("lying filter caught by y_class when it releases a violation",
              "F_P" in got.classes, str(got.evidence))
        no_cls = project_with_derivation(tau, SIGMA_R8.drop("y_class"))
        check("lying filter not caught without y_class", "F_P" not in verify_all(no_cls, arc).classes)

    # 9. HMAC: an impostor's tag does not verify; the genuine one does
    r = call_tool(pick(["F_T"]), docs, {})
    check("genuine tool tag verifies", keys.verify(keys.TOOL_KEY, pipeline.tool_payload(r), r["sig"]))
    check("impostor tag does not verify",
          not keys.verify(keys.TOOL_KEY, pipeline.tool_payload(r),
                          keys.sign(keys.ATTACKER_KEY, pipeline.tool_payload(r))))

    # 10. a tool hash missing from the store: evidence unavailable, not F_T
    tau, sig, _, _ = run(pick(["F_T"]), [])
    h = tau["t_calls_h"]["returned"]["value_hash"]
    saved = arc.blob_by_hash.pop(h)
    got = verify_all(sig, arc)
    check("missing store entry gives 'unavailable', not F_T",
          got.unavailable and "F_T" not in got.classes, str(got.evidence))
    arc.blob_by_hash[h] = saved

    # 11. Part B smoke: a clean disputed decision is not blamed on the library
    by_hash = {sha256(qq.text): qq for qq in queries}
    env = ReplayEnv(
        generate=lambda p, th: backend.generate(p, th, random.Random(int(th["seed"]) + 7)).text,
        render_context=render_context,
        apply_policy_of_record=lambda raw: apply_policy(raw)[0],
        tool_replay=lambda xh, a: call_tool(by_hash[xh], docs, {})["returned"]["value"],
        registered_description=pipeline.TOOL_DESCRIPTION)
    q = next(qq for qq in queries if not qq.needs_tool and qq.query_id not in restricted)
    tau, sig, _, _ = run(q, [])
    fnd = investigate(sig, arc, tau["y"], lambda o: answer(o, q), env, budget=10)
    check("Part B runs and reproduces a clean decision", fnd.reproduced is True, fnd.verdict)

    # 12. the investigator module imports no ground truth
    src = open("msfs/replay.py").read()
    check("replay.py imports no sealing, faults or attacks",
          not any(f"import {m}" in src or f".{m} import" in src
                  for m in ("sealing", "faults", "attacks")))

    print(f"\n{len(FAILS)} failed" if FAILS else "\nall checks passed")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
