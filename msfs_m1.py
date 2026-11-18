"""
M1: today's logging, from spans the real libraries emit (not projections).

Round 8's comparison rows (otel_default, otel_content, openinference,
openinference_guard) were projections: the full trace cut down to what each
specification says it records. This module runs the same executions through a
LlamaIndex pipeline with two instrumentation stacks switched on at once:

  OpenTelemetry   opentelemetry-instrumentation-openai-v2 (the official GenAI
                  instrumentation; it sees the model call only). Content capture
                  on: the prompt and the model output arrive as LOG RECORDS.
  OpenInference   openinference-instrumentation-llama-index (retriever, tool and
                  model spans), plus a GUARDRAIL span around the policy filter
                  that the application emits by hand, with input and output only:
                  the GUARDRAIL kind has no standard attributes.

Both stacks see the same execution, so one run gives every configuration. The
verifier then reads a record built ONLY from what the spans and logs hold.

What stays the same as round 8: the corpus, the faults (applied inside the
wrapped components, so the spans show what a faulty component returned), the
prompt, the model call (same body: model, messages, temperature, top_p,
max_tokens, seed) and the policy. execute_instrumented() mirrors
msfs.pipeline.execute() line for line; tests_m1.py checks that the two return
the same trace.
"""
from __future__ import annotations

import json
import os
import random
import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from opentelemetry import trace
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (LogRecordExporter, LogRecordExportResult,
                                            SimpleLogRecordProcessor)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

from msfs import pipeline as P
from msfs.backends import Generation
from msfs.real_world import passages_from_context
from msfs.state import Sigma
from msfs.util import sha256

OTEL_SCOPE = "opentelemetry.instrumentation.openai_v2"
OI_SCOPE = "openinference.instrumentation.llama_index"
CURRENT_PID: Optional[str] = None      # set by the runner when a run is sealed
DUMP = None                            # open file: one JSON line of spans per execution

# --- collection -----------------------------------------------------------------

_SPANS: List[Dict[str, Any]] = []
_LOGS: List[Dict[str, Any]] = []


class _SpanSink(SpanExporter):
    def export(self, spans):
        for s in spans:
            _SPANS.append({
                "name": s.name,
                "scope": s.instrumentation_scope.name if s.instrumentation_scope else None,
                "span_id": f"{s.context.span_id:016x}",
                "parent_id": f"{s.parent.span_id:016x}" if s.parent else None,
                "attributes": dict(s.attributes or {}),
            })
        return SpanExportResult.SUCCESS


class _LogSink(LogRecordExporter):
    def export(self, batch):
        for item in batch:
            r = getattr(item, "log_record", item)
            _LOGS.append({"event_name": getattr(r, "event_name", None)
                          or (r.attributes or {}).get("event.name"),
                          "span_id": f"{r.span_id:016x}" if r.span_id else None,
                          "body": r.body})
        return LogRecordExportResult.SUCCESS

    def force_flush(self, timeout_millis=30000):
        return True

    def shutdown(self):
        pass


_READY = False


def setup() -> None:
    """Switch both instrumentation stacks on, content capture included."""
    global _READY, _TRACER
    if _READY:
        return
    # openai-v2 2.3b0 reads "true" (newer util-genai reads mode names); content
    # goes to log records, so the log pipeline below is what keeps it.
    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"
    tp = TracerProvider()
    tp.add_span_processor(SimpleSpanProcessor(_SpanSink()))
    trace.set_tracer_provider(tp)
    lp = LoggerProvider()
    lp.add_log_record_processor(SimpleLogRecordProcessor(_LogSink()))
    from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
    OpenAIInstrumentor().instrument(tracer_provider=tp, logger_provider=lp)
    from openinference.instrumentation.llama_index import LlamaIndexInstrumentor
    LlamaIndexInstrumentor().instrument(tracer_provider=tp)
    _TRACER = trace.get_tracer("msfs.m1.app")
    _READY = True


def _harvest():
    spans, logs = list(_SPANS), list(_LOGS)
    _SPANS.clear()
    _LOGS.clear()
    return spans, logs


# --- the pipeline, through LlamaIndex ---------------------------------------------

def _retriever(hits):
    from llama_index.core.retrievers import BaseRetriever
    from llama_index.core.schema import NodeWithScore, TextNode

    class HarnessRetriever(BaseRetriever):
        """The harness retriever, already run with the fault applied; the
        framework sees its call and its (possibly faulty) result."""

        def _retrieve(self, query_bundle):
            return [NodeWithScore(node=TextNode(id_=d.doc_id, text=d.text), score=float(s))
                    for d, s in hits]

    return HarnessRetriever()


def _tool(tool_result):
    from llama_index.core.tools import FunctionTool
    value = tool_result["returned"]["value"]

    def lookup(topic: str = "") -> str:
        return str(value)

    return FunctionTool.from_defaults(
        fn=lookup, name=tool_result["tool"],
        description=tool_result.get("_description", P.TOOL_DESCRIPTION))


def _generate(prompt: str, theta: Dict[str, Any], model_id: str) -> Generation:
    """The same request body as msfs.backends.ApiBackend (style openai)."""
    from llama_index.core.base.llms.types import ChatMessage
    from llama_index.llms.openai_like import OpenAILike
    base = os.environ.get("MSFS_API_BASE", "http://localhost:11434").rstrip("/")
    llm = OpenAILike(model=model_id, api_base=base + "/v1",
                     api_key=os.environ.get("MSFS_API_KEY", "ollama"),
                     is_chat_model=True, timeout=120.0, max_retries=0,
                     temperature=float(theta.get("temperature", 0.7)),
                     max_tokens=int(theta.get("max_tokens", 512)))
    extra = {"top_p": float(theta.get("top_p", 1.0))}
    if "seed" in theta:
        extra["seed"] = int(theta["seed"])
    reply = llm.chat([ChatMessage(role="user", content=prompt)], **extra)
    return Generation(reply.message.content or "", model_id)


def execute_instrumented(query, base_docs, backend, fault, rng, theta=None, top_k=4,
                         retriever=None, answer_check=None, gen_rng=None,
                         tool_store=None, signed_witness=False):
    """msfs.pipeline.execute(), with each stage routed through LlamaIndex and the
    model called through the OpenAI SDK, both instrumented. Same arguments, same
    random draws in the same order, same trace, plus _spans and _logs."""
    setup()
    _harvest()                                   # drop anything from outside this run
    theta = theta or {"temperature": 0.7, "top_p": 1.0, "max_tokens": 256}
    with _TRACER.start_as_current_span("decision"):
        docs = fault.on_kb(dict(base_docs), query, rng)
        hits = (retriever or P.retrieve)(query, docs, top_k, rng)
        hits = fault.on_retrieved(hits, query, rng)
        _retriever(hits).retrieve(query.text)

        tool_result = P.call_tool(query, base_docs, tool_store) if query.needs_tool else None
        if tool_result is not None:
            tool_result = fault.on_tool(tool_result, query, rng)
            _tool(tool_result).call(**tool_result["args"])

        prompt = P.compose_prompt(query, hits, tool_result)
        prompt = fault.on_prompt(prompt, query, rng)

        gen = _generate(prompt, theta, backend.model_id)
        override = fault.policy_override()
        with _TRACER.start_as_current_span("policy_filter") as span:
            # OpenInference GUARDRAIL: no standard attributes beyond input/output
            span.set_attribute("openinference.span.kind", "GUARDRAIL")
            span.set_attribute("input.value", gen.text)
            output, report = P.apply_policy(gen.text, **override)
            output, report = fault.on_policy(output, report, query, rng)
            span.set_attribute("output.value", output)
    spans, logs = _harvest()

    if signed_witness:
        loaded = override.get("rules")
        witness = P.witness_wrapper(
            report, override.get("version", P.POLICY_VERSION),
            ran=not override.get("fail_open", False),
            rules_loaded=len(P.BLOCKED if loaded is None else loaded))
    else:
        witness = report
    witness = fault.on_witness(witness, query, rng)

    if answer_check:
        correct = answer_check(output, query)
    elif isinstance(query.answer_value, (int, float)):
        correct = f"{query.answer_value:g}" in output
    else:
        correct = str(query.answer_value).lower() in output.lower()
    released_violation = any(b in output.lower() for b in P.BLOCKED)
    desc = tool_result.get("_description", P.TOOL_DESCRIPTION) if tool_result else None
    tau = {
        "execution_id": f"exec-{uuid.uuid4().hex[:12]}",
        "query_id": query.query_id, "topic": query.topic,
        "x_hash": sha256(query.text), "x_text": query.text, "c": prompt,
        "z_ids": [d.doc_id for d, _ in hits], "z_hashes": [d.content_hash for d, _ in hits],
        "z_ranks": list(range(1, len(hits) + 1)), "z_scores": [round(s, 4) for _, s in hits],
        "z_text": [d.text for d, _ in hits], "z_embed": None,
        "t_calls": ({k: v for k, v in tool_result.items() if k != "sig" and not k.startswith("_")}
                    if tool_result else None),
        "t_calls_h": (dict({k: v for k, v in tool_result.items()
                            if k not in ("sig", "returned") and not k.startswith("_")},
                           returned={"value_hash": P.value_hash(tool_result["returned"]["value"]),
                                     "unit": tool_result["returned"].get("unit")})
                      if tool_result else None),
        "t_id": P.TOOL_IDENTITY if tool_result is not None else None,
        "t_attest": tool_result.get("sig") if tool_result else None,
        "t_desc_hash": sha256(desc) if tool_result else None,
        "p_witness": witness, "m": gen.model_id, "theta": dict(theta), "logprobs": gen.logprobs,
        "y": output, "c_hash": sha256(prompt), "y_hash": sha256(output),
        "y_class": P.decision_class(output),
        "_outcome_correct": correct, "_outcome_bad": (not correct) or released_violation,
        "_released_violation": released_violation, "_gold_value": query.answer_value,
        "_store": ({P.value_hash(tool_result["returned"]["value"]): tool_result["returned"]["value"],
                    sha256(desc): desc} if tool_result else {}),
        "_spans": spans, "_logs": logs,
    }
    if DUMP is not None:
        DUMP.write(json.dumps({"pid": CURRENT_PID, "execution_id": tau["execution_id"],
                               "spans": spans, "logs": logs}, default=str) + "\n")
        DUMP.flush()
    return tau


# --- from spans to a record -------------------------------------------------------

@dataclass(frozen=True)
class SpanConfig:
    """A comparison configuration whose record is built from emitted spans."""
    name: str
    label: str


SPAN_OTEL_DEFAULT = SpanConfig("span_otel_default", "OpenTelemetry openai-v2, content off")
SPAN_OTEL_CONTENT = SpanConfig("span_otel_content", "OpenTelemetry openai-v2, content on (log records)")
SPAN_OPENINFERENCE = SpanConfig("span_openinference", "OpenInference LlamaIndex, defaults")
SPAN_OPENINFERENCE_GUARD = SpanConfig("span_openinference_guard",
                                      "OpenInference LlamaIndex plus a GUARDRAIL span")
SPAN_CONFIGS = [SPAN_OTEL_DEFAULT, SPAN_OTEL_CONTENT, SPAN_OPENINFERENCE, SPAN_OPENINFERENCE_GUARD]
PROJECTION_OF = {"span_otel_default": "otel_default", "span_otel_content": "otel_content",
                 "span_openinference": "openinference",
                 "span_openinference_guard": "openinference_guard"}


def _question_from_context(c: str) -> Optional[str]:
    m = re.search(r"^\[QUESTION\] (.*)$", c, re.M)
    return m.group(1) if m else None


def _tool_version_from_context(c: str, name: str) -> Optional[str]:
    m = re.search(r"^\[TOOL " + re.escape(name) + r"@([^\]]+)\]", c or "", re.M)
    return m.group(1) if m else None


def _content_of(body) -> Optional[str]:
    if isinstance(body, dict):
        if "content" in body:
            return body["content"]
        msg = body.get("message") or {}
        return msg.get("content")
    return None


def sigma_from_spans(tau: Dict[str, Any], config_name: str) -> Sigma:
    """The record an auditor holds under this configuration: only fields present in
    the emitted spans and log records, plus the derivations any auditor could make
    (hashes of recorded text, ranks from recorded order, passages and the question
    parsed out of a recorded prompt). Nothing is read from tau except _spans/_logs."""
    spans, logs = tau.get("_spans", []), tau.get("_logs", [])
    st: Dict[str, Any] = {}
    if config_name.startswith("span_otel"):
        chat = next((s for s in spans if s["scope"] == OTEL_SCOPE), None)
        if chat:
            a = chat["attributes"]
            st["m"] = a.get("gen_ai.response.model") or a.get("gen_ai.request.model")
            st["theta"] = {k.split(".")[-1]: a[k] for k in (
                "gen_ai.request.temperature", "gen_ai.request.top_p",
                "gen_ai.request.max_tokens", "gen_ai.request.seed") if k in a}
        if config_name == "span_otel_content":
            user = next((l for l in logs if l["event_name"] == "gen_ai.user.message"), None)
            choice = next((l for l in logs if l["event_name"] == "gen_ai.choice"), None)
            c = _content_of(user["body"]) if user else None
            if c:
                st["c"] = c
                q = _question_from_context(c)
                if q is not None:
                    st["x_hash"] = sha256(q)
                texts = passages_from_context(c)
                st["z_hashes"] = [sha256(t) for t in texts]
                st["z_ranks"] = list(range(1, len(texts) + 1))
            if choice:
                st["y_model"] = _content_of(choice["body"])   # before the filter
        return Sigma(config_name=config_name, stored=st)

    oi = [s for s in spans if s["scope"] == OI_SCOPE]
    ret = next((s for s in oi if any(k.startswith("retrieval.documents.")
                                     for k in s["attributes"])), None)
    if ret:
        a = ret["attributes"]
        n = 1 + max(int(k.split(".")[2]) for k in a if k.startswith("retrieval.documents."))
        texts = [a.get(f"retrieval.documents.{i}.document.content") for i in range(n)]
        if "input.value" in a:
            st["x_hash"] = sha256(a["input.value"])
        st["z_ids"] = [a.get(f"retrieval.documents.{i}.document.id") for i in range(n)]
        st["z_scores"] = [a.get(f"retrieval.documents.{i}.document.score") for i in range(n)]
        st["z_hashes"] = [sha256(t) for t in texts]
        st["z_ranks"] = list(range(1, n + 1))
    llm = next((s for s in oi if "llm.input_messages.0.message.content" in s["attributes"]), None)
    if llm:
        a = llm["attributes"]
        st["c"] = a["llm.input_messages.0.message.content"]
        st["m"] = a.get("llm.model_name")
        try:
            st["theta"] = json.loads(a.get("llm.invocation_parameters", "{}"))
        except ValueError:
            pass
        st["y_model"] = a.get("llm.output_messages.0.message.content")
    tool = next((s for s in oi if s["attributes"].get("openinference.span.kind") == "TOOL"), None)
    if tool:
        a = tool["attributes"]
        name = a.get("tool.name")
        try:
            args = json.loads(a.get("input.value", "{}")).get("kwargs", {})
        except ValueError:
            args = {}
        try:
            out = json.loads(a.get("output.value", "{}"))
            value = out.get("raw_output")
            if value is None:
                value = "".join(b.get("text", "") for b in out.get("blocks", []))
        except ValueError:
            value = a.get("output.value")
        st["t_calls"] = {"tool": name,
                         # OpenInference records no tool version; recovered from the
                         # recorded prompt's tool line (a derivation, disclosed)
                         "version": _tool_version_from_context(st.get("c"), name),
                         "args": args, "returned": {"value": value, "unit": None}}
        if a.get("tool.description") is not None:
            st["t_desc_hash"] = sha256(a["tool.description"])
    elif llm:
        st["t_calls"] = None                     # spans were emitted, and no tool was called
    if config_name == "span_openinference_guard":
        g = next((s for s in spans if s["attributes"].get("openinference.span.kind")
                  == "GUARDRAIL"), None)
        if g:
            st["y"] = g["attributes"].get("output.value")
            st["guard_io"] = {"input": g["attributes"].get("input.value"),
                              "output": g["attributes"].get("output.value")}
    return Sigma(config_name=config_name, stored=st)


def guard_signals(sigma) -> List[tuple]:
    """The one check a GUARDRAIL span with input and output allows: re-apply the
    registered policy (Assumption A-S) to the recorded input; if that would have
    blocked an output the guardrail released, the filter failed. Registered as an
    M1 verifier extension; it applies only where the record holds guard_io."""
    if not sigma.has("guard_io"):
        return []
    io = sigma.get("guard_io")
    if io.get("input") is None or io.get("output") is None:
        return []
    expected, _ = P.apply_policy(io["input"])
    if expected != io["output"]:
        return [("F_P", 0.90, "the guardrail released an output that the registered "
                              "policy, applied to the guardrail's recorded input, blocks")]
    return []
