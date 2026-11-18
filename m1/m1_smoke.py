"""
M1, step 1: what do real instrumentation libraries actually emit?

Runs ONE question through a small LlamaIndex pipeline that has the same stages
as the MSFS harness (retriever, lookup tool, context, model, policy filter),
with one instrumentation stack switched on, and writes every emitted span to
JSONL. Nothing here is a result; it shows which attributes exist, so the
adapter (step 2) maps real span fields and nothing else.

    python m1_smoke.py otel        # OpenTelemetry GenAI, content off (default)
    python m1_smoke.py otel-content
    python m1_smoke.py oi          # OpenInference (LlamaIndex), its defaults

Needs Ollama running with llama3.1:8b (OpenAI-compatible API on :11434).
Output: spans_<mode>.jsonl (and logs_<mode>.jsonl for otel modes), plus a printed summary of span names and keys.
"""
import json
import os
import sys
from typing import List

MODE = sys.argv[1] if len(sys.argv) > 1 else "oi"
OUT = f"spans_{MODE}.jsonl"
API_BASE = os.environ.get("M1_API_BASE", "http://localhost:11434/v1")

# Content capture must be set before the instrumentor runs. With
# opentelemetry-instrumentation-openai-v2 2.3b0 the switch is "true", and the
# content goes to LOG RECORDS (events), not to span attributes, so a log
# pipeline must be configured or the content is silently lost. (The newer
# opentelemetry-util-genai reads mode names instead: SPAN_ONLY, EVENT_ONLY,
# SPAN_AND_EVENT. Pin versions and record them.)
if MODE == "otel-content":
    os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"
elif MODE == "otel":
    os.environ.pop("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", None)

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult


class JsonlExporter(SpanExporter):
    """Every span, as emitted: name, kind, parent, attributes, events."""

    def __init__(self, path):
        self.fh = open(path, "w")

    def export(self, spans):
        for s in spans:
            self.fh.write(json.dumps({
                "name": s.name,
                "kind": str(s.kind),
                "scope": s.instrumentation_scope.name if s.instrumentation_scope else None,
                "trace_id": f"{s.context.trace_id:032x}",
                "span_id": f"{s.context.span_id:016x}",
                "parent_id": f"{s.parent.span_id:016x}" if s.parent else None,
                "attributes": dict(s.attributes or {}),
                "events": [{"name": e.name, "attributes": dict(e.attributes or {})}
                           for e in s.events],
            }, default=str) + "\n")
        self.fh.flush()
        return SpanExportResult.SUCCESS


provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(JsonlExporter(OUT)))
trace.set_tracer_provider(provider)
LOGS = f"logs_{MODE}.jsonl"

if MODE.startswith("otel"):
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import (LogRecordExporter, LogRecordExportResult,
                                                SimpleLogRecordProcessor)

    class JsonlLogExporter(LogRecordExporter):
        """GenAI content events, as emitted, with the span they belong to."""

        def __init__(self, path):
            self.fh = open(path, "w")

        def export(self, batch):
            for item in batch:
                r = getattr(item, "log_record", item)
                self.fh.write(json.dumps({
                    "span_id": f"{r.span_id:016x}" if r.span_id else None,
                    "event_name": getattr(r, "event_name", None),
                    "attributes": dict(r.attributes or {}),
                    "body": r.body,
                }, default=str) + "\n")
            self.fh.flush()
            return LogRecordExportResult.SUCCESS

        def force_flush(self, timeout_millis=30000):
            self.fh.flush()
            return True

        def shutdown(self):
            self.fh.close()

    logs = LoggerProvider()
    logs.add_log_record_processor(SimpleLogRecordProcessor(JsonlLogExporter(LOGS)))
    from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
    OpenAIInstrumentor().instrument(tracer_provider=provider, logger_provider=logs)
else:
    from openinference.instrumentation.llama_index import LlamaIndexInstrumentor
    LlamaIndexInstrumentor().instrument(tracer_provider=provider)

from llama_index.core.base.llms.types import ChatMessage
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
from llama_index.core.tools import FunctionTool
from llama_index.llms.openai_like import OpenAILike

PASSAGES = [
    ("doc-1", "Scott Derrickson (born July 16, 1966) is an American director.", 0.82),
    ("doc-2", "Edward Davis Wood Jr. was an American filmmaker.", 0.79),
    ("doc-3", "Doctor Strange is a 2016 film directed by Scott Derrickson.", 0.71),
    ("doc-4", "Ed Wood is a 1994 film directed by Tim Burton.", 0.66),
]
QUESTION = "Were Scott Derrickson and Ed Wood of the same nationality?"


class HarnessRetriever(BaseRetriever):
    """Stand-in for the MSFS retriever. In step 2 this wraps msfs retrieval
    (with the F_R fault applied inside), so the framework sees the real call."""

    def _retrieve(self, q: QueryBundle) -> List[NodeWithScore]:
        return [NodeWithScore(node=TextNode(id_=i, text=t), score=s) for i, t, s in PASSAGES]


def lookup(entity: str) -> str:
    """Look up the registered record for an entity."""
    return f"{entity}: American (record of reference)"


tool = FunctionTool.from_defaults(fn=lookup, name="lookup",
                                  description="Look up the registered record for an entity.")
llm = OpenAILike(model="llama3.1:8b", api_base=API_BASE, api_key="ollama",
                 is_chat_model=True, temperature=0.0, max_tokens=64)
tracer = trace.get_tracer("msfs.m1")

with tracer.start_as_current_span("decision"):
    nodes = HarnessRetriever().retrieve(QUESTION)
    tool_out = tool.call(entity="Ed Wood")
    context = "\n".join(f"[DOC rank={k + 1}] {n.node.get_content()}" for k, n in enumerate(nodes))
    context += f"\n[TOOL lookup] {tool_out}\n\n[QUESTION] {QUESTION}"
    reply = llm.chat([ChatMessage(role="user", content=context)])
    answer = reply.message.content or ""
    # The policy filter. OpenInference has a GUARDRAIL span kind but no
    # guardrail attributes, so this is what a careful deployer would emit by hand.
    with tracer.start_as_current_span("policy_filter") as span:
        if MODE == "oi":
            span.set_attribute("openinference.span.kind", "GUARDRAIL")
            span.set_attribute("input.value", answer)
        released = answer
        if MODE == "oi":
            span.set_attribute("output.value", released)

provider.force_flush()
print(f"answer: {answer!r}\nwrote {OUT}\n")
if MODE.startswith("otel"):
    logs.force_flush()
    print(f"log records (GenAI events) in {LOGS}:")
    for line in open(LOGS):
        r = json.loads(line)
        print(f"  {r['event_name'] or r['attributes'].get('event.name')}: body = {str(r['body'])[:110]}")
    print()
for line in open(OUT):
    s = json.loads(line)
    print(f"- {s['name']}  [{s['attributes'].get('openinference.span.kind', s['kind'])}]")
    for k in sorted(s["attributes"]):
        v = str(s["attributes"][k]).replace("\n", " ")
        print(f"    {k} = {v[:90]}")
    for e in s["events"]:
        print(f"    event {e['name']}: {sorted(e['attributes'])}")
