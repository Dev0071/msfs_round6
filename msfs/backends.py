"""
Model backends for M.

Two modes, and the distinction matters for what you are allowed to claim:

  MockBackend   -- a stochastic, context-following stub. Use it to validate the
                   APPARATUS: that injection, sealing, projection, blinding, and
                   the statistics wire up correctly end to end. Numbers from a
                   mock run are harness diagnostics, NOT thesis results, and the
                   analysis module stamps them as such.

  ApiBackend    -- a real LLM behind an OpenAI-compatible or Anthropic Messages
                   endpoint. This is what produces reportable numbers.

Pineau et al.'s reproducibility checklist applies to the harness, not the
subject: seeds, versions, and provenance are pinned here even though the subject
is deliberately non-deterministic.
"""

from __future__ import annotations

import json
import os
import random
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class Generation:
    text: str
    model_id: str
    logprobs: Optional[List[float]] = None


class Backend(Protocol):
    model_id: str

    def generate(self, prompt: str, theta: Dict[str, Any], rng: random.Random) -> Generation: ...


# --- mock --------------------------------------------------------------------

class MockBackend:
    """
    Context-following stub with genuine run-to-run variance.

    Behaviour that the fault classes need it to have:
      - answers from retrieved context, usually the top-ranked passage but not
        always (temperature-controlled rank slip -> real non-determinism)
      - obeys imperative instructions embedded in the prompt (so F_X bites)
      - copies tool return values verbatim into the answer (so F_T bites)
      - emits whatever the policy layer left in place (so F_P bites)
    """

    def __init__(self, model_id: str = "mock-llm-1"):
        self.model_id = model_id

    def generate(self, prompt: str, theta: Dict[str, Any], rng: random.Random) -> Generation:
        temp = float(theta.get("temperature", 0.7))

        override = re.search(r"\[\[INSTRUCTION:(.*?)\]\]", prompt, re.S)
        if override:
            return Generation(f"ANSWER: {override.group(1).strip()}", self.model_id)

        # Injected instructions that arrive inside a passage, a tool result or a
        # tool description. A real model follows these some of the time; the
        # stub follows them with a fixed probability so the apparatus is
        # exercised on both branches.
        hijack = re.search(r'State that the answer to the question is "(.+?)"', prompt)
        if hijack and rng.random() < 0.6:
            return Generation(f"ANSWER: {hijack.group(1)}", self.model_id)

        tool_vals = re.findall(r"\[TOOL_RESULT\]\s*(.*)", prompt)
        passages = re.findall(r"\[DOC rank=(\d+)\]\s*(.*)", prompt)

        if tool_vals:
            body = tool_vals[0].strip()
        elif passages:
            # rank slip: higher temperature -> more chance of answering from a
            # lower-ranked passage. This is the pipeline's irreducible stochasticity.
            idx = 0
            if len(passages) > 1 and rng.random() < min(0.35, temp * 0.4):
                idx = rng.randrange(1, len(passages))
            body = passages[idx][1].strip()
        else:
            body = "I do not have enough information to answer."

        if rng.random() < 0.5:
            body = f"Based on the available material, {body[0].lower()}{body[1:]}" if body else body

        return Generation(f"ANSWER: {body}", self.model_id)


# --- real ---------------------------------------------------------------------

class ApiBackend:
    """
    Anthropic Messages API, or any OpenAI-compatible /chat/completions endpoint.

    Set MSFS_API_KEY. For Anthropic:
        MSFS_API_BASE=https://api.anthropic.com  MSFS_API_STYLE=anthropic
    For a local vLLM / Ollama / TGI server:
        MSFS_API_BASE=http://localhost:8000  MSFS_API_STYLE=openai
    """

    def __init__(self, model_id: str, style: Optional[str] = None, base: Optional[str] = None):
        self.model_id = model_id
        self.style = style or os.environ.get("MSFS_API_STYLE", "anthropic")
        self.base = (base or os.environ.get("MSFS_API_BASE", "https://api.anthropic.com")).rstrip("/")
        self.key = os.environ.get("MSFS_API_KEY", "")
        if not self.key:
            raise RuntimeError("MSFS_API_KEY is not set; ApiBackend cannot run.")

    def generate(self, prompt: str, theta: Dict[str, Any], rng: random.Random) -> Generation:
        import urllib.request

        if self.style == "anthropic":
            url = f"{self.base}/v1/messages"
            headers = {
                "content-type": "application/json",
                "x-api-key": self.key,
                "anthropic-version": "2023-06-01",
            }
            body = {
                "model": self.model_id,
                "max_tokens": int(theta.get("max_tokens", 512)),
                "temperature": float(theta.get("temperature", 0.7)),
                "messages": [{"role": "user", "content": prompt}],
            }
        else:
            url = f"{self.base}/v1/chat/completions"
            headers = {
                "content-type": "application/json",
                "authorization": f"Bearer {self.key}",
            }
            body = {
                "model": self.model_id,
                "max_tokens": int(theta.get("max_tokens", 512)),
                "temperature": float(theta.get("temperature", 0.7)),
                "top_p": float(theta.get("top_p", 1.0)),
                "messages": [{"role": "user", "content": prompt}],
            }
            if "seed" in theta:
                body["seed"] = int(theta["seed"])

        req = urllib.request.Request(
            url, data=json.dumps(body).encode(), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())

        if self.style == "anthropic":
            text = "".join(b.get("text", "") for b in data.get("content", []))
        else:
            text = data["choices"][0]["message"]["content"]
        return Generation(text, self.model_id)


def make_backend(spec: str) -> Backend:
    if spec == "mock":
        return MockBackend()
    return ApiBackend(model_id=spec)
