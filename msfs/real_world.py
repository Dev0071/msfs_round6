"""
Real-world logging configurations, expressed as subsets of Omega.

Each configuration encodes what a tracing setup records for one pipeline
execution, mapped onto the harness vocabulary in state.OMEGA. The mapping is a
reading of the public specifications, and every row should be checked against
the current spec before it is cited.

  otel_default        OpenTelemetry GenAI semantic conventions with content
                      capture OFF, which is the specified default. Model name,
                      request parameters and tool name are attributes; prompts,
                      outputs, tool arguments/results, retrieval query text and
                      retrieved documents are Opt-In and therefore absent.

  otel_content        The same conventions with content capture opted in:
                      input/output messages, system instructions, tool call
                      arguments and result, retrieval query text and documents.

  openinference       OpenInference defaults (all HIDE_* flags False): input and
                      output values, LLM input messages, invocation parameters,
                      model name, retrieved documents with id/content/score,
                      tool name, parameters and output.

  openinference_guard The same, where the application also wraps its policy
                      filter in a GUARDRAIL span. Treated generously as carrying
                      the whole policy witness.

Tool description: the GenAI conventions define gen_ai.tool.description on the
tool-execution span and OpenInference defines tool.description. Both are read
here as recorded whenever a tool runs, in every configuration including the
content-off default, and the auditor hashes the text. This is the reading most
favourable to today's logging. CHECK the requirement level in the current spec
before citing it.

None of these records a content hash, a tool-response attestation, or token
log-probabilities. Hashes are DERIVABLE from stored text, and an auditor would
derive them, so `project_with_derivation` computes them. Without that step the
comparison would be an artefact of key names rather than of information.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .state import Sigma, SigmaConfig
from .util import sha256

OTEL_DEFAULT = SigmaConfig(
    name="otel_default",
    label="OpenTelemetry GenAI conventions, content capture off (default)",
    elements=frozenset({"m", "theta", "t_id", "t_desc_hash"}),
)

# gen_ai.retrieval.documents carries id and score for each document, not its
# content (semantic-conventions-genai, commit b9ecbae). Passage text is in the
# record only as part of the input messages, so the auditor recovers passages
# by parsing them out of the context (see project_with_derivation).
OTEL_CONTENT = SigmaConfig(
    name="otel_content",
    label="OpenTelemetry GenAI conventions, content capture opted in",
    elements=frozenset({"x_text", "c", "y", "z_ids", "z_scores",
                        "t_calls", "t_id", "t_desc_hash", "m", "theta"}),
)

OPENINFERENCE = SigmaConfig(
    name="openinference",
    label="OpenInference defaults (full content)",
    elements=frozenset({"x_text", "c", "y", "z_ids", "z_scores", "z_text",
                        "t_calls", "t_id", "t_desc_hash", "m", "theta"}),
)

OPENINFERENCE_GUARD = SigmaConfig(
    name="openinference_guard",
    label="OpenInference defaults plus a GUARDRAIL span around the policy filter",
    elements=frozenset(OPENINFERENCE.elements | {"p_witness"}),
)

REAL_WORLD_CONFIGS = [OTEL_DEFAULT, OTEL_CONTENT, OPENINFERENCE, OPENINFERENCE_GUARD]


def passages_from_context(context: str) -> List[str]:
    """Parse the passages out of a context built with the registered template."""
    body = context.split("\n\n[QUESTION]")[0]
    start = body.find("[DOC rank=")
    if start < 0:
        return []
    body = body[start:]
    tool = body.find("\n[TOOL ")
    if tool >= 0:
        body = body[:tool]
    return [p for p in re.split(r"(?:^|\n)\[DOC rank=\d+\] ", body) if p]


def project_with_derivation(trace: Dict[str, Any], config: SigmaConfig) -> Sigma:
    """
    Destructive projection, then the derivations any auditor could perform from
    what was stored: h(x) from the input text, content hashes from the retrieved
    text, and ranks from the stored order of the retrieved list.
    """
    stored = {e: trace.get(e) for e in sorted(config.elements)}
    if stored.get("x_text") is not None and "x_hash" not in stored:
        stored["x_hash"] = sha256(stored["x_text"])
    if "z_text" not in stored and "z_hashes" not in stored and stored.get("c"):
        # Passages recovered from the context the model was handed. They are
        # what assembly put in front of the model, not what retrieval returned,
        # so a retrieval fault and an assembly fault can no longer be told apart.
        texts = passages_from_context(stored["c"])
        stored["z_hashes"] = [sha256(t) for t in texts]
        stored["z_ranks"] = list(range(1, len(texts) + 1))
    if stored.get("z_text") is not None:
        if "z_hashes" not in stored:
            stored["z_hashes"] = [sha256(t) for t in stored["z_text"]]
        if "z_ranks" not in stored:
            stored["z_ranks"] = list(range(1, len(stored["z_text"]) + 1))
    return Sigma(config_name=config.name, stored=stored)
