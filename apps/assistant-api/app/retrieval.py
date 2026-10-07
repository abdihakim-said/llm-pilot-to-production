"""BM25 retrieval over the policy manual, split by section heading.

The manual is small and changes through releases, so an in-memory index built
at startup keeps the system simple and fully reproducible per release.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

_TOKEN = re.compile(r"[a-z0-9£%]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass(frozen=True)
class Chunk:
    doc: str
    title: str
    section: str
    text: str

    @property
    def citation(self) -> str:
        return f"{self.title} › {self.section}"


def load_chunks(policy_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(policy_dir.glob("[0-9]*.md")):
        title, section, lines = path.stem, "Overview", []
        for line in path.read_text().splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
            elif line.startswith("## "):
                if lines:
                    chunks.append(Chunk(path.name, title, section, "\n".join(lines).strip()))
                section, lines = line[3:].strip(), []
            elif line.strip():
                lines.append(line)
        if lines:
            chunks.append(Chunk(path.name, title, section, "\n".join(lines).strip()))
    return chunks


class Retriever:
    def __init__(self, chunks: list[Chunk]):
        if not chunks:
            raise ValueError("no policy chunks loaded")
        self.chunks = chunks
        self._bm25 = BM25Okapi([_tokens(f"{c.title} {c.section} {c.text}") for c in chunks])

    def search(self, query: str, k: int = 3) -> list[Chunk]:
        scores = self._bm25.get_scores(_tokens(query))
        ranked = sorted(zip(scores, self.chunks), key=lambda x: x[0], reverse=True)
        return [c for s, c in ranked[:k] if s > 0]
