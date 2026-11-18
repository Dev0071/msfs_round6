"""
M1 runner: round 8's registered blocks, re-run with real instrumentation.

Uses run_round8.py unchanged, with four substitutions:
  - execute()                  -> msfs_m1.execute_instrumented()
  - the comparison list        += the four span configurations
  - project_with_derivation()  builds span configurations from emitted spans only
  - verify_all()               adds the guardrail re-evaluation (span configs only)
and one restriction: the first --m1-n blocks of each of the ten pairs, taken from
round 8's own plan (n = 72), so every block, question and seed is one round 8 ran.
Part B and the descriptive arms are off.

    python run_m1.py --backend llama3.1:8b --corpus hotpotqa --out results_m1
    python run_m1.py ... --m1-n 2 --out m1_smoke      # a quick check first

Writes everything run_round8 writes, plus spans.jsonl (every span and log
record per execution) and m1_versions.json.
"""
import json
import sys
from importlib import metadata
from pathlib import Path

import msfs_m1
import run_round8 as R
from msfs.sealing import SealedLog
from msfs.verifier import PRIORITY, VerdictSet

M1_N = 24
argv = sys.argv[1:]
if "--m1-n" in argv:
    i = argv.index("--m1-n")
    M1_N = int(argv[i + 1])
    del argv[i:i + 2]
out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else Path("results_m1")
if "--out" not in argv:
    argv += ["--out", str(out)]
if "--pairs" not in argv:
    argv += ["--pairs", ",".join(R.PAIRS)]
if "--no-part-b" not in argv:
    argv.append("--no-part-b")
if "--n" in argv:
    raise SystemExit("Leave --n alone: blocks come from round 8's plan (n = 72); use --m1-n.")
sys.argv = [sys.argv[0]] + argv
out.mkdir(parents=True, exist_ok=True)

# --- substitutions ----------------------------------------------------------------

R.execute = msfs_m1.execute_instrumented
R.COMPARE = list(R.COMPARE) + msfs_m1.SPAN_CONFIGS

_project = R.project_with_derivation


def project(trace, config):
    if isinstance(config, msfs_m1.SpanConfig):
        return msfs_m1.sigma_from_spans(trace, config.name)
    return _project(trace, config)


R.project_with_derivation = project

_verify_all = R.verify_all


def verify_all(sigma, arc):
    vs = _verify_all(sigma, arc)
    extra = msfs_m1.guard_signals(sigma)
    if not extra:
        return vs
    signals = sorted(vs.signals + extra, key=lambda s: (s[1], PRIORITY[s[0]]), reverse=True)
    return VerdictSet(frozenset(vs.classes | {c for c, _, _ in extra}), signals, vs.unavailable)


R.verify_all = verify_all


class PidLog(SealedLog):
    def seal(self, pid, *a, **k):
        msfs_m1.CURRENT_PID = pid
        return super().seal(pid, *a, **k)


R.SealedLog = PidLog

_plan = R.plan_blocks


def plan_blocks(args, queries, restricted):
    args.n = 72                                    # round 8's plan, exactly
    blocks = [b for b in _plan(args, queries, restricted) if b["block"] % 1000 < M1_N]
    return blocks


R.plan_blocks = plan_blocks

# --- record versions, open the span dump, run -------------------------------------

PKGS = ["opentelemetry-sdk", "opentelemetry-instrumentation-openai-v2", "opentelemetry-util-genai",
        "wrapt", "openinference-instrumentation-llama-index", "openinference-semantic-conventions",
        "llama-index-core", "llama-index-llms-openai-like", "openai"]
versions = {}
for p in PKGS:
    try:
        versions[p] = metadata.version(p)
    except metadata.PackageNotFoundError:
        versions[p] = None
(out / "m1_versions.json").write_text(json.dumps({"m1_n": M1_N, "packages": versions}, indent=2))
msfs_m1.DUMP = open(out / "spans.jsonl", "w")
msfs_m1.setup()
raise SystemExit(R.main())
