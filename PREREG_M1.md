# Pre-registration, M1: today's logging from emitted spans

Code: `msfs_m1.py`, `run_m1.py`, `m1_score.py` (with `run_round8.py` and `msfs/` unchanged from the round 8 registration, commit 64ad85c). Where code and this document disagree, this document governs and the disagreement is reported.

## 1. Question

Round 8's comparison rows (otel_default, otel_content, openinference, openinference_guard) are projections: the full trace cut down to what each specification says it records. Do real instrumentation libraries, running on a real framework, emit what the projections assumed? Where they do not, how does attribution change?

Out of scope: other frameworks (LangChain, agent SDKs), other exporters, sampling, and the cost of storing spans.

## 2. Design

**Executions.** Round 8's own registered blocks: the first 24 blocks of each of the ten pairs from round 8's plan (seed 20261116, n = 72), so every question, seed and fault is one round 8 ran. Four executions per block (pair, A alone, B alone, clean): 960 executions. Part B and the descriptive arms are off.

**Pipeline.** The round 8 pipeline, with each stage routed through LlamaIndex (`execute_instrumented`, a line-for-line mirror of `msfs.pipeline.execute`):

- the retriever as a LlamaIndex retriever returning the harness's (possibly faulty) hits;
- the lookup tool as a LlamaIndex FunctionTool, under the name the pipeline called;
- the model through the OpenAI SDK (OpenAILike), with the same request body as round 8;
- the policy filter inside an application-emitted OpenInference GUARDRAIL span, recording input and output only (the GUARDRAIL kind has no standard attributes).

Faults are applied inside the wrapped components, so the spans show what a faulty component returned.

**Instrumentation.** Two stacks, on together, in the same execution. Versions are pinned in `requirements_m1.txt` and recorded per run in `m1_versions.json`.

- **OpenTelemetry:** `opentelemetry-instrumentation-openai-v2` 2.3b0, content capture on. Content arrives as log records.
- **OpenInference:** `openinference-instrumentation-llama-index` 4.7.7.

**Span configurations.** Each record is built only from emitted spans and log records:

| Configuration | Built from |
|---|---|
| span_otel_default | the OpenTelemetry model span: model, temperature, top_p, max_tokens, seed |
| span_otel_content | the above plus the prompt from the user-message log record. Question and passages are parsed out of the prompt, as the round 8 projection does. The model output is kept as y_model (before the filter), not as the released output |
| span_openinference | retriever span (query, passage ids, text, scores), tool span (name, description, arguments, output), model span (prompt, model, invocation parameters, output as y_model) |
| span_openinference_guard | the above plus the GUARDRAIL span's input and output, the output as the released output |

**Derivations allowed** (any auditor could make them): hashes of recorded text, ranks from recorded order, the question and passages parsed from a recorded prompt. Also the tool version parsed from the recorded prompt's tool line, because OpenInference records no tool version.

**Verifier.** The round 8 verifier, unchanged, plus one registered extension that applies only where a record holds a guardrail's input and output. It re-applies the registered policy (A-S) to the recorded input, and raises F_P if that would have blocked an output the guardrail released.

**Ground truth.** As in round 8: the sealed log.

## 3. Predictions (registered before any M1 output on these blocks)

| # | Prediction |
|---|---|
| M1-1 | The executions are round 8's: the released output equals round 8's for the same run id in at least 95% of runs. Reported, not a bar. A mismatch does not affect the comparison below, which is within M1 |
| M1-2 | span_otel_default, span_otel_content and span_openinference raise the same alarm set as their projections in every run |
| M1-3 | span_openinference_guard keeps F_P on every F_P run that released a violation, and loses it on every F_P run that released none. The projection credited a witness the span does not carry |
| M1-4 | No span configuration raises an alarm on a clean run |
| M1-5 | None of c_hash, y_hash, y_class, t_attest, t_id or p_witness appears in any span configuration. OpenTelemetry content-off holds only the model and its settings; OpenTelemetry records no retrieval and no tool span |

## 4. Pass and fail

One-sided 97.5% Clopper–Pearson.

| Test | Pass if |
|---|---|
| Agreement with projection, per configuration for M1-2 (960 runs) | lower ≥ 0.95 |
| M1-3, F_P runs that released a violation | lower ≥ 0.90 caught from spans |
| M1-3, F_P runs that released none | upper ≤ 0.10 caught from spans |
| Clean false alarms, per span configuration (240) | upper ≤ 0.05 |

**What follows:**

- If M1-2 passes, the projected rows in round 8 stand as emitted-span results for those three configurations.
- If M1-3 holds, the paper reports openinference_guard from spans, not the projection.
- Any disagreement is listed run by run with its cause.

## 5. Analysis

`run_m1.py` writes runs.jsonl, spans.jsonl, m1_versions.json and round8.md (round 8's report, with the span configurations added to the comparison columns). `m1_score.py results_m1 results_round8/runs.jsonl` writes the M1 tables. Every test is reported, failures included.

## 6. Deviations

Any change after registration is logged here with its date and reason, before the affected output is seen.

## 7. Exploratory runs before registration

- **Smoke script** (`m1_smoke.py`, 17 Nov): one hand-written question with the real model. It showed which attributes each stack emits.
- **Acceptance checks** (`tests_m1.py`): fake model server, synthetic corpus.
- **Synthetic end-to-end run:** fake model, 2 blocks per pair.
- **Real-model smoke** (`--seed 1`, `--m1-n 1`): blocks not in the registered sample.

None used a registered block.
