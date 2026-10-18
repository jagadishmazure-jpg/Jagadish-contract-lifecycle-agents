"""Tiny TF-IDF retrieval over the 4 SOP docs, with citations.

Chunks are `docs/sops/*.md` sections. Answers cite `<file> §<section>`.
Title-only intro chunks are skipped (they caused false positives in a
sibling repo). Unknown questions get an explicit not-found, never a guess.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

_DOCS_DIR = Path(__file__).resolve().parents[1] / "docs" / "sops"


def _tokens(text: str):
    return re.findall(r"[a-z0-9]+", text.lower())


def load_chunks(docs_dir: Path | None = None):
    docs_dir = docs_dir or _DOCS_DIR
    chunks = []
    for md in sorted(docs_dir.glob("*.md")):
        section = None
        buf = []
        for line in md.read_text().splitlines():
            if line.startswith("## "):
                if section and [b for b in buf if len(_tokens(b)) > 4]:
                    chunks.append({
                        "file": md.name,
                        "section": section,
                        "text": "\n".join(buf).strip(),
                    })
                section = line[3:].strip()
                buf = []
            else:
                buf.append(line)
        if section and [b for b in buf if len(_tokens(b)) > 4]:
            chunks.append({
                "file": md.name,
                "section": section,
                "text": "\n".join(buf).strip(),
            })
    return chunks


def _tfidf(chunks):
    df = Counter()
    tfs = []
    for ch in chunks:
        toks = _tokens(ch["text"])
        tf = Counter(toks)
        tfs.append(tf)
        for t in tf:
            df[t] += 1
    n = len(chunks)
    idf = {t: math.log((1 + n) / (1 + d)) + 1.0 for t, d in df.items()}
    vecs = [{t: c * idf[t] for t, c in tf.items()} for tf in tfs]
    return vecs, idf


def search(query: str, chunks, top_k: int = 2):
    vecs, idf = _tfidf(chunks)
    q = Counter(_tokens(query))
    qv = {t: c * idf.get(t, 1.0) for t, c in q.items()}
    scored = []
    for ch, v in zip(chunks, vecs):
        dot = sum(qv.get(t, 0.0) * w for t, w in v.items())
        n1 = math.sqrt(sum(w * w for w in qv.values())) or 1.0
        n2 = math.sqrt(sum(w * w for w in v.values())) or 1.0
        scored.append((dot / (n1 * n2), ch))
    scored.sort(key=lambda s: -s[0])
    return [(s, ch) for s, ch in scored[:top_k] if s > 0.05]


def answer(query: str, chunks=None):
    chunks = chunks if chunks is not None else load_chunks()
    hits = search(query, chunks)
    if not hits:
        return {
            "answer": "No SOP covers this question.",
            "citations": [],
            "found": False,
        }
    parts = []
    cites = []
    for _score, ch in hits:
        words = ch["text"].split()
        parts.append(" ".join(words[:60]))
        cites.append(f"{ch['file']} §{ch['section']}")
    return {"answer": " ".join(parts), "citations": cites, "found": True}
