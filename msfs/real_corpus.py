"""
Real RAG substrate.

Swaps the synthetic corpus and lexical stand-in for a dense retriever over a
real QA corpus, without touching execution, faults, projection, or the verifier.
The seam is `pipeline.Retriever`, and everything downstream still sees
(Doc, score) pairs.

Install:
    pip install datasets sentence-transformers faiss-cpu

Build the index once (a few minutes, then cached):
    python -c "from msfs.real_corpus import build; build(n_examples=2000)"

Then:
    python replicate.py --backend claude-sonnet-4-6 --replications 5 \\
        --n 300 --corpus hotpotqa --out results/confirmatory

NOTE: this module has not been executed in the environment where it was
written, which had no dataset or model access. Run `python -m msfs.real_corpus
--selftest` on a connected machine before trusting it, and read the numbers it
prints rather than assuming.
"""

from __future__ import annotations

import pickle
import random
import re
import string
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .pipeline import Doc, Query
from .util import sha256

CACHE = Path("corpus_cache")
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"   # RAGOrigin's encoder


# --- answer matching ----------------------------------------------------------

_ARTICLES = re.compile(r"\b(a|an|the)\b")
_PUNCT = str.maketrans("", "", string.punctuation)


def normalize_answer(s: str) -> str:
    """SQuAD-standard normalisation: lowercase, drop articles, punctuation, spacing."""
    s = s.lower().translate(_PUNCT)
    s = _ARTICLES.sub(" ", s)
    return " ".join(s.split())


def answer_match(output: str, query: Query) -> bool:
    """
    Did the released output contain the gold answer?

    This replaces the synthetic `f"{value:g}" in output` check. It is deliberately
    lenient — substring after normalisation — because the outcome variable only
    needs to separate 'the decision was right' from 'the decision was wrong', not
    to grade phrasing. State this choice in the thesis; a reviewer will ask.
    """
    gold = normalize_answer(str(query.answer_value))
    return bool(gold) and gold in normalize_answer(output)


# --- corpus construction ------------------------------------------------------

def build(n_examples: int = 2000, split: str = "validation",
          cache: Path = CACHE) -> Tuple[Dict[str, Doc], List[Query]]:
    """
    Pool every context paragraph across `n_examples` HotpotQA distractor examples
    into one knowledge base, then index it. At n_examples = 2000 the corpus is
    roughly 20k passages — small next to RAGOrigin's millions, large enough that
    retrieval is a genuine ranking problem rather than a lookup.
    """
    from datasets import load_dataset

    cache.mkdir(exist_ok=True)
    ds = load_dataset("hotpot_qa", "distractor", split=f"{split}[:{n_examples}]")

    docs: Dict[str, Doc] = {}
    queries: List[Query] = []
    seen: Dict[str, str] = {}          # content hash -> doc_id, for dedup

    for ex in ds:
        titles = ex["context"]["title"]
        sentence_lists = ex["context"]["sentences"]
        answer = ex["answer"]
        support_titles = set(ex["supporting_facts"]["title"])

        gold_id: Optional[str] = None
        for title, sents in zip(titles, sentence_lists):
            text = f"{title}. " + " ".join(sents)
            h = sha256(text)
            if h in seen:
                did = seen[h]
            else:
                did = f"hp:{len(docs):07d}"
                docs[did] = Doc(did, title, text, None)
                seen[h] = did
            # the gold passage is a supporting paragraph that actually contains
            # the answer string; if none does, the example is unusable
            if gold_id is None and title in support_titles \
               and normalize_answer(answer) in normalize_answer(text):
                gold_id = did

        if gold_id is None:
            continue

        queries.append(Query(
            query_id=f"hp-{len(queries):06d}",
            topic=docs[gold_id].topic,
            text=ex["question"],
            gold_doc=gold_id,
            answer_value=answer,
            needs_tool=(len(queries) % 2 == 0),
            tool_redundant=True,        # the gold passage asserts the answer
        ))

    with open(cache / "corpus.pkl", "wb") as f:
        pickle.dump((docs, queries), f)
    print(f"corpus: {len(docs)} passages, {len(queries)} usable questions")
    return docs, queries


def load(cache: Path = CACHE) -> Tuple[Dict[str, Doc], List[Query]]:
    with open(cache / "corpus.pkl", "rb") as f:
        return pickle.load(f)


# --- dense retriever ----------------------------------------------------------

class DenseRetriever:
    """
    FAISS inner-product index over normalised MiniLM embeddings.

    Injected documents are embedded on the fly rather than pre-indexed, because
    a poisoned passage that the harness added mid-run is not in the index yet.
    That is also what makes retrieval-optimised poison behave the way PoisonedRAG
    describes: it is crafted against the query, so it scores high on arrival.
    """

    def __init__(self, docs: Dict[str, Doc], cache: Path = CACHE,
                 model_name: str = MODEL_NAME, batch_size: int = 256):
        import faiss
        import numpy as np
        from sentence_transformers import SentenceTransformer

        self.np = np
        self.model = SentenceTransformer(model_name)
        self.doc_ids = sorted(docs)
        emb_path = cache / "embeddings.npy"

        if emb_path.exists():
            emb = np.load(emb_path)
            if emb.shape[0] != len(self.doc_ids):
                raise RuntimeError("cached embeddings do not match the corpus; "
                                   "delete corpus_cache/embeddings.npy and rebuild")
        else:
            texts = [docs[d].text for d in self.doc_ids]
            emb = self.model.encode(texts, batch_size=batch_size,
                                    normalize_embeddings=True,
                                    show_progress_bar=True).astype("float32")
            cache.mkdir(exist_ok=True)
            np.save(emb_path, emb)

        self.index = faiss.IndexFlatIP(emb.shape[1])
        self.index.add(emb)
        self.position = {d: i for i, d in enumerate(self.doc_ids)}
        self._qcache: Dict[str, Any] = {}

    def _encode(self, text: str):
        if text not in self._qcache:
            self._qcache[text] = self.model.encode(
                [text], normalize_embeddings=True).astype("float32")
        return self._qcache[text]

    def __call__(self, query: Query, docs: Dict[str, Doc], k: int,
                 rng: random.Random) -> List[Tuple[Doc, float]]:
        qv = self._encode(query.text)
        scores, idx = self.index.search(qv, k * 3)
        hits: List[Tuple[Doc, float]] = []
        for j, s in zip(idx[0], scores[0]):
            did = self.doc_ids[j]
            if did in docs:                     # respects suppression
                hits.append((docs[did], float(s)))

        # documents present in this execution's KB but absent from the index --
        # i.e. injected by the harness -- are scored live
        extra = [d for d in docs if d not in self.position]
        if extra:
            vecs = self.model.encode([docs[d].text for d in extra],
                                     normalize_embeddings=True).astype("float32")
            for d, v in zip(extra, vecs):
                hits.append((docs[d], float(self.np.dot(qv[0], v))))

        hits.sort(key=lambda p: -p[1])
        return hits[:k]


# --- selftest -----------------------------------------------------------------

def _selftest() -> None:
    docs, queries = build(n_examples=200)
    r = DenseRetriever(docs)
    hit_at_1 = hit_at_4 = 0
    sample = queries[:100]
    for q in sample:
        got = [d.doc_id for d, _ in r(q, docs, 4, random.Random(0))]
        hit_at_1 += q.gold_doc == got[0] if got else 0
        hit_at_4 += q.gold_doc in got
    print(f"gold@1 = {hit_at_1/len(sample):.3f}   gold@4 = {hit_at_4/len(sample):.3f}")
    print("If gold@4 is below ~0.8 the retriever is too weak for the fault model: "
          "F_R suppression and rank manipulation stop being distinguishable from "
          "ordinary retrieval failure, and the completeness numbers are not "
          "measuring what they claim to measure.")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest()
    else:
        build()
