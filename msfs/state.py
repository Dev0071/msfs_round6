"""
Omega: the candidate execution-state vocabulary.
sigma: a projection of a full trace onto a stored subset of Omega.

The whole experiment turns on one discipline: the verifier NEVER sees a trace.
It sees only sigma(tau). Projection is therefore destructive by construction --
`project()` returns a dict containing exactly the requested keys and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable

# --- Omega -------------------------------------------------------------------
# Every element carries an approximate per-execution storage cost in bytes,
# used for the storage-overhead analysis (RQ1 cost side).

OMEGA: Dict[str, int] = {
    "x_hash":     32,      # h(x), hash of the raw user input
    "x_text":     400,     # raw user input in the clear
    "c":          2200,    # composed context/prompt actually handed to M
    "z_ids":      64,      # identifiers of retrieved documents
    "z_hashes":   160,     # content hashes of retrieved documents
    "z_ranks":    20,      # ordered position of each retrieved document
    "z_scores":   40,      # retriever similarity scores
    "z_text":     4800,    # full retrieved document text
    "z_embed":    12288,   # retrieved document embeddings
    "t_calls":    600,     # tool call transcripts: name, args, return value
    "t_id":       48,      # tool identity + version
    "t_attest":   32,      # tool service attestation over its own response
    "p_witness":  96,      # policy witness: version hash, verdict, heartbeat
    "m":          32,      # model identity
    "theta":      24,      # sampling parameters
    "logprobs":   9000,    # token log-probabilities
    "y":          500,     # final output text
    # --- commitments: content-free counterparts of c and y ---
    "c_hash":     32,      # commitment to the composed context handed to M
    "y_hash":     32,      # commitment to the released output, com(o)
    "y_class":    1,       # decision class of the released output, delta(o)
    "t_desc_hash": 32,     # hash of the tool description the model was shown
}

ALL = frozenset(OMEGA)


# --- sigma configurations ----------------------------------------------------

@dataclass(frozen=True)
class SigmaConfig:
    name: str
    label: str
    elements: FrozenSet[str]

    def __post_init__(self) -> None:
        unknown = set(self.elements) - ALL
        if unknown:
            raise ValueError(f"{self.name}: elements not in Omega: {sorted(unknown)}")

    @property
    def bytes_per_execution(self) -> int:
        return sum(OMEGA[e] for e in self.elements)

    def drop(self, element: str) -> "SigmaConfig":
        """Single-element ablation (Proposition 1: |sigma*| ablations, not 2^|sigma*|)."""
        if element not in self.elements:
            raise ValueError(f"{element} not in {self.name}")
        return SigmaConfig(
            name=f"{self.name}-{element}",
            label=f"{self.label} minus {element}",
            elements=frozenset(self.elements - {element}),
        )


SIGMA_0 = SigmaConfig(
    name="sigma0",
    label="Input-output only (what most deployed systems log)",
    elements=frozenset({"x_hash", "y"}),
)

SIGMA_1 = SigmaConfig(
    name="sigma1",
    label="Conventional observability (adds provenance IDs and config)",
    elements=frozenset({"x_hash", "y", "z_ids", "m", "theta"}),
)

# The sigma* candidate under test. `m` is included deliberately so that the
# pre-registered prediction -- that model identity is NOT minimality-necessary
# under the four-class fault model -- is falsifiable by the ablation arm.
SIGMA_STAR = SigmaConfig(
    name="sigma_star",
    label="sigma* candidate",
    elements=frozenset({
        "x_hash", "c", "z_hashes", "z_ranks", "t_calls", "t_id",
        "p_witness", "m", "y",
    }),
)

SIGMA_MAX = SigmaConfig(
    name="sigma_max",
    label="Maximalist (Omega-style: store everything)",
    elements=ALL,
)

# Revised candidate. The pre-registered sigma* fails F_T because a tool
# transcript is self-reported: nothing in it distinguishes a faithful return
# from a tampered one. t_attest is the repair the experiment argues for.
SIGMA_STAR_PLUS = SigmaConfig(
    name="sigma_star_plus",
    label="sigma* + tool attestation (revised candidate)",
    elements=frozenset(SIGMA_STAR.elements | {"t_attest"}),
)

# Content-free candidate. The prompt, the retrieved passages and the output are
# stored as commitments only; their text lives once in the content-addressed
# archive, not in the per-execution record. The tool transcript is kept
# verbatim, because its attestation is checked over the transcript itself.
SIGMA_HASH = SigmaConfig(
    name="sigma_hash",
    label="sigma* with commitments in place of context and output text",
    elements=frozenset({
        "x_hash", "c_hash", "z_hashes", "z_ranks", "t_calls", "t_id", "t_attest",
        "p_witness", "m", "y_hash", "y_class",
    }),
)

# sigma_hash plus a commitment to the tool description the model was shown.
# Without it a changed description shows up only as a context mismatch, which
# the verifier can only blame on prompt assembly.
SIGMA_HASH_PLUS = SigmaConfig(
    name="sigma_hash_plus",
    label="sigma_hash + tool description hash",
    elements=frozenset(SIGMA_HASH.elements | {"t_desc_hash"}),
)

STANDARD_CONFIGS = [SIGMA_0, SIGMA_1, SIGMA_STAR, SIGMA_STAR_PLUS, SIGMA_MAX]


# --- projection --------------------------------------------------------------

@dataclass
class Sigma:
    """A stored forensic state. This is the ONLY thing the verifier may read."""
    config_name: str
    stored: Dict[str, Any] = field(default_factory=dict)

    def has(self, *elements: str) -> bool:
        return all(e in self.stored and self.stored[e] is not None for e in elements)

    def get(self, element: str, default: Any = None) -> Any:
        if element not in self.stored:
            raise KeyError(
                f"verifier requested {element!r}, which is not stored under "
                f"{self.config_name}. Guard the access with .has() first."
            )
        v = self.stored[element]
        return default if v is None else v

    @property
    def size_bytes(self) -> int:
        return sum(OMEGA[e] for e in self.stored)


def project(trace: Dict[str, Any], config: SigmaConfig) -> Sigma:
    """Destructive projection tau -> sigma(tau)."""
    return Sigma(
        config_name=config.name,
        stored={e: trace.get(e) for e in sorted(config.elements)},
    )


def elements_by_cost(config: SigmaConfig) -> Iterable[str]:
    return sorted(config.elements, key=lambda e: -OMEGA[e])
