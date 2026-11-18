"""
M1 acceptance checks. No Ollama needed: a fake OpenAI-compatible server on a
local port answers every call, so the checks are about plumbing, not the model.

    python tests_m1.py

1. execute_instrumented() returns the same trace as msfs.pipeline.execute(),
   for a clean run and every round 8 fault class.
2. Spans were emitted by both stacks, for every run.
3. The span-built records hold what the spans hold, and it is the real thing:
   passage hashes, prompt, question hash and tool call equal the trace's.
4. Content-off OpenTelemetry holds the model and its settings, nothing else.
5. The guardrail re-evaluation fires exactly when the filter released a violation.
"""
import json
import os
import random
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 18765


class Fake(BaseHTTPRequestHandler):
    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
        prompt = req["messages"][-1]["content"]
        # a deterministic answer that depends on the prompt: the tool result if
        # there is one, else the first passage's first words
        lines = prompt.split("\n")
        tool = [l for l in lines if l.startswith("[TOOL_RESULT]")]
        docs = [l for l in lines if l.startswith("[DOC rank=1]")]
        text = (tool[0][14:] if tool else (" ".join(docs[0].split()[2:8]) if docs else "unknown"))
        body = json.dumps({"id": "fake", "object": "chat.completion", "created": 0,
                           "model": req["model"],
                           "choices": [{"index": 0, "finish_reason": "stop",
                                        "message": {"role": "assistant", "content": text}}],
                           "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                                     "total_tokens": 2}}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


server = HTTPServer(("127.0.0.1", PORT), Fake)
threading.Thread(target=server.serve_forever, daemon=True).start()
os.environ.update(MSFS_API_STYLE="openai", MSFS_API_BASE=f"http://127.0.0.1:{PORT}",
                  MSFS_API_KEY="test")

import msfs_m1  # noqa: E402
from msfs import attacks, keys, pipeline as P  # noqa: E402
from msfs.attacks import CompositeFault  # noqa: E402
from msfs.backends import ApiBackend  # noqa: E402
from msfs.pipeline import Fault, build_corpus  # noqa: E402

msfs_m1.setup()
fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        fails.append(name)


docs, queries = build_corpus()
P.register_restricted([q.answer_value for q in queries[:5]])   # some restricted answers
backend = ApiBackend("llama3.1:8b")
VARIANTS = {"F_R": "suppression", "F_X": "context_truncation",
            "F_T": "server_name_squatting", "F_P": "fail_open", "F_D": "poison_ingested_d5"}
attacks.GENERATOR = None
SKIP = {"execution_id", "_spans", "_logs", "logprobs"}

cases = [("clean", None)] + [(c, v) for c, v in VARIANTS.items()]
tool_q = [q for q in queries if q.needs_tool][:3]
plain_q = [q for q in queries if not q.needs_tool][:3]
n_runs = 0
for cls, var in cases:
    for q in (tool_q + plain_q):
        def fault():
            if cls == "clean":
                return Fault()
            return CompositeFault([attacks.make_attack(cls, random.Random(0), var)],
                                  member_seeds=[7])
        theta = {"temperature": 0.0, "top_p": 1.0, "max_tokens": 64, "seed": 3}
        kw = dict(top_k=4, signed_witness=True)
        a = P.execute(q, docs, backend, fault(), random.Random(11), dict(theta),
                      gen_rng=random.Random(18), **kw)
        b = msfs_m1.execute_instrumented(q, docs, backend, fault(), random.Random(11), dict(theta),
                                         gen_rng=random.Random(18), **kw)
        n_runs += 1
        diff = [k for k in a if k not in SKIP and a[k] != b.get(k)]
        check(f"1 same trace: {cls} {q.query_id}", not diff, f"differs in {diff}")
        scopes = {s["scope"] for s in b["_spans"]}
        check(f"2 both stacks emitted: {cls} {q.query_id}",
              msfs_m1.OTEL_SCOPE in scopes and msfs_m1.OI_SCOPE in scopes, str(scopes))

        oi = msfs_m1.sigma_from_spans(b, "span_openinference").stored
        ok = (oi.get("z_hashes") == b["z_hashes"] and oi.get("c") == b["c"]
              and oi.get("x_hash") == b["x_hash"] and oi.get("m") == b["m"])
        if b["t_calls"]:
            tc = oi.get("t_calls") or {}
            ok = ok and (tc.get("tool"), tc.get("version"), tc.get("args"),
                         str(tc.get("returned", {}).get("value"))) == (
                b["t_calls"]["tool"], b["t_calls"]["version"], b["t_calls"]["args"],
                str(b["t_calls"]["returned"]["value"]))
            ok = ok and oi.get("t_desc_hash") == b["t_desc_hash"]
        else:
            ok = ok and "t_calls" in oi and oi["t_calls"] is None
        check(f"3 openinference record is the real thing: {cls} {q.query_id}", ok)

        oc = msfs_m1.sigma_from_spans(b, "span_otel_content").stored
        check(f"3 otel content record: {cls} {q.query_id}",
              oc.get("c") == b["c"] and oc.get("x_hash") == b["x_hash"]
              and oc.get("y_model") is not None and "y" not in oc)

        od = msfs_m1.sigma_from_spans(b, "span_otel_default").stored
        check(f"4 otel default holds model and settings only: {cls} {q.query_id}",
              set(od) == {"m", "theta"} and od["m"] == "llama3.1:8b"
              and od["theta"].get("temperature") == 0.0, str(sorted(od)))

        g = msfs_m1.sigma_from_spans(b, "span_openinference_guard")
        fired = bool(msfs_m1.guard_signals(g))
        check(f"5 guardrail check fires iff a violation was released: {cls} {q.query_id}",
              fired == b["_released_violation"], f"fired={fired}")

print(f"\n{n_runs} paired executions. " + ("all checks passed" if not fails else f"{len(fails)} FAILED"))
server.shutdown()
raise SystemExit(1 if fails else 0)
