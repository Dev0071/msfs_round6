#!/usr/bin/env python3
"""
Experiment I: measure epsilon_int instead of assuming it.

v8 asserted epsilon_int = 1e-3 as an "operational allowance" and implemented
only BIND. This builds the integrity layer (msfs/integrity.py) and attacks it.

A storage adversary acts AFTER entries are sealed (condition C2 of the
composition theorem). Every in-model attack below must be detected on every
trial. The out-of-model attacks are run too, to measure the boundary rather
than state it: they are expected to go undetected, and the report says so.

No language model is needed. Records come from the mock backend on the
synthetic corpus; the integrity layer never looks at what the model said, only
at whether the stored record is the one that was sealed.

  python exp_integrity.py --trials 500 --out results_integrity

Outputs: integrity.json, integrity.md (detection per attack, which clauses
fired, clause necessity, and the measured epsilon_int bound).
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

from scipy.stats import beta

from msfs.backends import MockBackend
from msfs.integrity import (ANCHOR_EVERY, CLAUSES, GENESIS, SecureLog, audit,
                            authenticate_event, clone, entry_hash, evolve, key_at,
                            mac, make_bind_check, make_entry)
from msfs.pipeline import Fault, build_corpus, decision_class, execute
from msfs.state import SIGMA_HASH_PLUS
from msfs.util import sha256
from msfs.verifier import _canonical_prompt
from msfs.state import Sigma
from run_experiment import build_archive

ALPHA = 0.025          # one-sided, as registered in the paper (97.5% bounds)
REQUIRED = SIGMA_HASH_PLUS.elements


def cp_upper(k, n, alpha=ALPHA):
    return 1.0 if k == n else float(beta.ppf(1 - alpha, k + 1, n - k))


# --- record generation --------------------------------------------------------

def make_records(n, seed):
    docs, queries = build_corpus(seed=seed)
    arc = build_archive(docs, queries, auditor="archive")
    backend, rng = MockBackend(), random.Random(seed)
    recs = []
    for i in range(n):
        q = queries[i % len(queries)]
        tau = execute(q, docs, backend, Fault(), random.Random(seed + i),
                      {"temperature": 0.7, "top_p": 1.0, "max_tokens": 256})
        recs.append(({e: tau.get(e) for e in sorted(REQUIRED)}, tau["y"]))
    return recs, arc, docs


def build_log(records, k0):
    witness = []
    log = SecureLog(k0, witness)
    for r, _ in records:
        log.append(r)
    return log, witness


def retag_from(entries, start, keyfn):
    """Recompute hash, links and tags from `start` on; keyfn(i) gives the key used."""
    prev = entries[start - 1]["hash"] if start > 0 else GENESIS
    for i in range(start, len(entries)):
        e = entries[i]
        e["seq"], e["prev"] = i, prev
        body = {k: e[k] for k in ("schema", "seq", "prev", "record")}
        e["hash"] = entry_hash(body)
        e["tag"] = mac(keyfn(i), e["hash"])
        prev = e["hash"]
    return entries


def mutate(record, rng):
    """Change one stored element so that it carries a different meaning."""
    r = dict(record)
    key = rng.choice(sorted(k for k in r if r[k] is not None))
    v = r[key]
    if isinstance(v, str):
        j = rng.randrange(len(v))
        r[key] = v[:j] + ("0" if v[j] != "0" else "1") + v[j + 1:]
    elif isinstance(v, list) and v:
        v = list(v)
        j = rng.randrange(len(v))
        v[j] = (sha256(str(v[j]) + "x") if isinstance(v[j], str) else v[j] + 1)
        r[key] = v
    elif isinstance(v, dict):
        v = json.loads(json.dumps(v))
        if "verdict" in v:
            v["verdict"] = "ALLOW" if v["verdict"] == "BLOCK" else "BLOCK"
        elif "returned" in v:
            v["returned"]["value"] = f"{v['returned']['value']} (edited)"
        else:
            v["_edited"] = True
        r[key] = v
    else:
        r[key] = "edited"
    return r, key


def coherent_lie(record, arc, rng):
    """A false record that is internally consistent: other archived passages,
    and a context commitment recomputed over them."""
    r = dict(record)
    pool = list(arc.doc_text_by_hash)
    r["z_hashes"] = rng.sample(pool, len(r["z_hashes"]))
    canon = _canonical_prompt(Sigma("lie", r), arc)
    r["c_hash"] = sha256(canon)
    return r


# --- attacks -------------------------------------------------------------------
# Each takes (entries, witness, ctx, rng) and returns (entries, witness, claim).
# claim is a (x_hash, output) the attacker presents as a real decision, or None.

def a_edit_field(E, W, c, rng):
    i = rng.randrange(len(E))
    E[i]["record"], _ = mutate(E[i]["record"], rng)
    return E, W, None


def a_edit_rehash(E, W, c, rng):
    i = rng.randrange(len(E))
    E[i]["record"], _ = mutate(E[i]["record"], rng)
    stale = {j: E[j]["tag"] for j in range(len(E))}
    retag_from(E, i, lambda j: b"")
    for j in range(i, len(E)):
        E[j]["tag"] = stale[j]          # cannot produce valid tags without the key
    return E, W, None


def a_edit_rehash_own_key(E, W, c, rng):
    i = rng.randrange(len(E))
    E[i]["record"], _ = mutate(E[i]["record"], rng)
    retag_from(E, i, lambda j: b"attacker-key")
    return E, W, None


def a_delete_middle(E, W, c, rng):
    del E[rng.randrange(len(E) - 1)]
    return E, W, None


def a_delete_relink(E, W, c, rng):
    i = rng.randrange(len(E) - 1)
    del E[i]
    retag_from(E, i, lambda j: b"attacker-key")
    return E, W, None


def a_reorder(E, W, c, rng):
    i, j = rng.sample(range(len(E)), 2)
    E[i], E[j] = E[j], E[i]
    return E, W, None


def a_insert_forged(E, W, c, rng):
    i = rng.randrange(len(E))
    fake, _ = mutate(E[rng.randrange(len(E))]["record"], rng)
    E.insert(i, make_entry(i, E[i - 1]["hash"] if i else GENESIS, fake, b"attacker-key"))
    return E, W, None


def a_replay(E, W, c, rng):
    i = rng.randrange(len(E))
    E.insert(i + 1, clone([E[i]])[0])
    return E, W, None


def a_splice_foreign(E, W, c, rng):
    other, _ = build_log(c["records"], b"another-deployment-key")
    i = rng.randrange(len(E))
    E[i] = clone([other.entries[i]])[0]
    return E, W, None


def a_truncate_anchored(E, W, c, rng):
    last = max(n for n, _ in W)
    cut = rng.randrange(1, last)                    # drop into anchored territory
    return E[:cut], W, None


def a_drop_element(E, W, c, rng):
    i = rng.randrange(len(E))
    k = rng.choice(sorted(E[i]["record"]))
    E[i]["record"] = {kk: v for kk, v in E[i]["record"].items() if kk != k}
    retag_from(E, i, lambda j: b"attacker-key")
    return E, W, None


def a_key_compromise_past(E, W, c, rng):
    # The logger is compromised at time t; the attacker holds k_t and edits an
    # entry written before t, re-tagging everything it can.
    t = rng.randrange(2, len(E))
    i = rng.randrange(0, t)
    kt = key_at(c["k0"], t)
    E[i]["record"], _ = mutate(E[i]["record"], rng)
    keys = {}

    def keyfn(j):
        if j >= t:
            keys[j] = keys.get(j) or key_at(kt, j - t)
            return keys[j]
        return kt                         # best available guess for earlier keys
    retag_from(E, i, keyfn)
    return E, W, None


def a_false_flag(E, W, c, rng):
    # Claim a decision that never happened: a real input with an output the
    # pipeline never released (the false-flag exposure of Section 2.3).
    i = rng.randrange(len(E))
    real_out = c["outputs"][i]
    return E, W, (E[i]["record"]["x_hash"], real_out + " Guaranteed approval.")


def a_selective_capture(E, W, c, rng):
    # An honest-key logger that omits a retrieved passage from the record at
    # capture time, keeping the true context commitment (anti-selective
    # logging is what BIND is for).
    i = rng.randrange(len(E))
    r = dict(E[i]["record"])
    r["z_hashes"] = r["z_hashes"][:-1]
    r["z_ranks"] = r["z_ranks"][:-1]
    E[i]["record"] = r
    retag_from(E, i, lambda j: key_at(c["k0"], j))
    W[:] = [(n, E[n - 1]["hash"]) for n, _ in W]   # the logger publishes its own heads
    return E, W, None


def a_omit_element_capture(E, W, c, rng):
    # An honest-key logger that leaves a whole element out of the record at
    # capture time (e.g. never writes the policy witness).
    i = rng.randrange(len(E))
    k = rng.choice(sorted(E[i]["record"]))
    E[i]["record"] = {kk: v for kk, v in E[i]["record"].items() if kk != k}
    retag_from(E, i, lambda j: key_at(c["k0"], j))
    W[:] = [(n, E[n - 1]["hash"]) for n, _ in W]
    return E, W, None


# out of model: expected to go undetected

def o_truncate_unanchored(E, W, c, rng):
    last = max(n for n, _ in W)
    if last >= len(E):
        return E, W, None
    return E[:rng.randrange(last, len(E))], W, None


def o_compromise_rewrites_unanchored(E, W, c, rng):
    last = max(n for n, _ in W)
    if last >= len(E):
        return E, W, None
    kt = key_at(c["k0"], last)          # stolen at the last anchor, used later
    i = rng.randrange(last, len(E))
    E[i]["record"] = coherent_lie(E[i]["record"], c["arc"], rng)
    retag_from(E, i, lambda j: key_at(kt, j - last))
    return E, W, None


def o_capture_lie_coherent(E, W, c, rng):
    i = rng.randrange(len(E))
    E[i]["record"] = coherent_lie(E[i]["record"], c["arc"], rng)
    retag_from(E, i, lambda j: key_at(c["k0"], j))
    W[:] = [(n, E[n - 1]["hash"]) for n, _ in W]
    return E, W, None


IN_MODEL = {
    "edit_field": (a_edit_field, "change one stored element"),
    "edit_and_rehash": (a_edit_rehash, "change an element, recompute the hash chain, no key"),
    "edit_rehash_own_key": (a_edit_rehash_own_key, "change, recompute, re-tag with the attacker's key"),
    "delete_middle": (a_delete_middle, "delete an entry"),
    "delete_and_relink": (a_delete_relink, "delete an entry and relink the chain"),
    "reorder": (a_reorder, "swap two entries"),
    "insert_forged": (a_insert_forged, "insert a fabricated entry"),
    "replay": (a_replay, "duplicate an entry"),
    "splice_foreign": (a_splice_foreign, "substitute an entry from another deployment's log"),
    "truncate_anchored": (a_truncate_anchored, "truncate into anchored entries"),
    "drop_element": (a_drop_element, "remove one element from a record"),
    "key_compromise_past": (a_key_compromise_past, "steal the key at t, edit an entry written before t"),
    "false_flag": (a_false_flag, "present an output the pipeline never released"),
    "selective_capture": (a_selective_capture, "logger omits a passage at capture (honest key)"),
    "omit_element_capture": (a_omit_element_capture, "logger omits a whole element at capture (honest key)"),
}
OUT_OF_MODEL = {
    "truncate_unanchored": (o_truncate_unanchored, "drop entries written since the last anchor"),
    "compromise_rewrites_unanchored": (o_compromise_rewrites_unanchored,
                                       "key stolen at the last anchor; unanchored entries rewritten coherently"),
    "capture_lie_coherent": (o_capture_lie_coherent, "logger records a coherent false record at capture"),
}


def run(trials, log_len, seed):
    rng = random.Random(seed)
    records, arc, _ = make_records(max(400, log_len * 4), seed)
    bind = make_bind_check(arc)
    results = {}

    # sanity: an untampered log must pass every clause
    k0 = b"escrowed-initial-key"
    for _ in range(20):
        sample = rng.sample(records, log_len)
        log, W = build_log(sample, k0)
        res = audit(log.entries, k0, W, REQUIRED, bind)
        if not res.ok:
            raise SystemExit(f"untampered log failed audit: {res.failures}")

    for group, table in (("in_model", IN_MODEL), ("out_of_model", OUT_OF_MODEL)):
        for name, (fn, desc) in table.items():
            detected, fired, sole = 0, {c: 0 for c in CLAUSES}, {c: 0 for c in CLAUSES}
            applied = 0
            for t in range(trials):
                sample = rng.sample(records, log_len)
                k0 = f"escrowed-key-{seed}-{t}".encode()
                log, W = build_log(sample, k0)
                # no shutdown anchor: entries since the last anchor are exposed,
                # as after a crash or during an attack
                ctx = {"records": sample, "k0": k0, "arc": arc,
                       "outputs": [o for _, o in sample]}
                before = [e["hash"] for e in log.entries]
                E, W2, claim = fn(clone(log.entries), list(W), ctx, rng)
                if claim is None and [e.get("hash") for e in E] == before and \
                        all(a == b for a, b in zip(E, log.entries)):
                    continue                 # attack had nothing to act on this trial
                applied += 1
                res = audit(E, k0, W2, REQUIRED, bind)
                hit = not res.ok
                if claim is not None:
                    found = authenticate_event(E, *claim)
                    if found is None:
                        res.fail("CLASS", "no sealed entry opens to the disputed output")
                        hit = True
                detected += hit
                for cl in res.clauses:
                    fired[cl] += 1
                if len(res.clauses) == 1:
                    sole[res.clauses[0]] += 1
            results[name] = {"group": group, "description": desc, "n": applied,
                             "detected": detected,
                             "rate": round(detected / applied, 4) if applied else None,
                             "fired": fired, "only_clause": sole}
    return results


def bind_on_genuine_faults(seed, n=60):
    """
    BIND as an integrity clause, on records that were never tampered with but
    whose pipeline had a genuine fault. If BIND fires here, an integrity layer
    that includes it reports a real F_X/F_T fault as tampering (condition C1 of
    the composition theorem makes the verifier abort on it).
    """
    from msfs import attacks
    docs, queries = build_corpus(seed=seed)
    arc = build_archive(docs, queries, auditor="archive")
    bind = make_bind_check(arc)
    plain = [q for q in queries if not q.needs_tool]
    tool = [q for q in queries if q.needs_tool]
    rows = {}
    for fc, var in [("NONE", "clean"), ("F_R", "tail_reorder"), ("F_R", "suppression"),
                    ("F_X", "unregistered_prompt"), ("F_X", "context_truncation"),
                    ("F_T", "rug_pull"), ("F_T", "server_name_squatting"),
                    ("F_P", "policy_rollback")]:
        fired = 0
        for i in range(n):
            pool = tool if fc == "F_T" else plain
            q = pool[i % len(pool)]
            if var == "clean":
                f = Fault()
            elif var == "tail_reorder":
                f = attacks.IndexFault(fault_class="F_R", variant=var, params={})
            else:
                f = attacks.make_attack(fc, random.Random(seed + i), var)
            tau = execute(q, docs, MockBackend(), f, random.Random(seed + i))
            fired += not bind({e: tau.get(e) for e in REQUIRED})
        rows[f"{fc}/{var}"] = {"n": n, "bind_fired": fired}
    return rows


def report(results, trials, log_len, bind_rows=None):
    ins = [r for r in results.values() if r["group"] == "in_model"]
    n = sum(r["n"] for r in ins)
    miss = sum(r["n"] - r["detected"] for r in ins)
    up = cp_upper(miss, n)
    L = ["# Integrity layer under attack (epsilon_int)\n",
         f"{trials} trials per attack, logs of {log_len} entries, head anchored every "
         f"{ANCHOR_EVERY} entries, no shutdown anchor. Clauses implemented: "
         f"{', '.join(CLAUSES)}. ATTEST not implemented.\n",
         "## In-model attacks (storage adversary after sealing; must all be detected)\n",
         "| attack | what the attacker does | detected | clauses that fired | "
         "caught by one clause only |", "|---|---|---|---|---|"]
    for name, r in results.items():
        if r["group"] != "in_model":
            continue
        fired = ", ".join(f"{c} {k}" for c, k in r["fired"].items() if k)
        sole = ", ".join(f"{c} {k}" for c, k in r["only_clause"].items() if k) or "-"
        L.append(f"| {name} | {r['description']} | {r['detected']}/{r['n']} | "
                 f"{fired} | {sole} |")
    L += ["", f"**Measured epsilon_int (in-model): {miss} undetected in {n} attacks; "
              f"one-sided 97.5% upper bound {up:.2e}.** This bounds the "
              "implementation's failure rate on the attacks tested. HMAC-SHA256 "
              "forgery is negligible and is not what this measures.", "",
          "## Out-of-model attacks (expected to go undetected)\n",
          "| attack | what the attacker does | detected |", "|---|---|---|"]
    for name, r in results.items():
        if r["group"] == "out_of_model":
            L.append(f"| {name} | {r['description']} | {r['detected']}/{r['n']} |")
    L += ["", "Reading: integrity is measured for tampering after sealing. A logger "
              "that lies at capture time, or a key stolen before entries are anchored, "
              "is outside what any post-hoc check can catch; that residue is the "
              "Schneier-Kelsey capture-time concession, and needs ATTEST (a TEE) to close."]
    if bind_rows:
        L += ["", "## BIND on untampered records with a genuine pipeline fault\n",
              "If BIND is an integrity clause, it should never fire on an untampered "
              "record. It does whenever the fault changes the context:\n",
              "| fault | BIND fired |", "|---|---|"]
        for k, r in bind_rows.items():
            L.append(f"| {k} | {r['bind_fired']}/{r['n']} |")
        L += ["", "Consequence: with BIND inside INTEGRITY, condition C1 turns a genuine "
                  "F_X or rug-pull F_T fault into an 'integrity failure' verdict. With BIND "
                  "outside INTEGRITY (as a verifier check), a logger that omits a passage at "
                  "capture (selective_capture above) is reported as an F_X fault. From the "
                  "record alone, selective logging and a prompt-assembly fault are the same "
                  "observation."]
    return "\n".join(L), {"n": n, "undetected": miss, "eps_int_upper": up}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=500)
    ap.add_argument("--log-len", type=int, default=70,
                    help="not a multiple of the anchor interval, so a tail is unanchored")
    ap.add_argument("--seed", type=int, default=20261007)
    ap.add_argument("--out", default="results_integrity")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    results = run(a.trials, a.log_len, a.seed)
    bind_rows = bind_on_genuine_faults(a.seed)
    md, summary = report(results, a.trials, a.log_len, bind_rows)
    summary["bind_on_genuine_faults"] = bind_rows
    (out / "integrity.json").write_text(json.dumps(
        {"config": vars(a), "anchor_every": ANCHOR_EVERY, "results": results,
         "summary": summary, "seconds": round(time.time() - t0, 1)}, indent=2))
    (out / "integrity.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
