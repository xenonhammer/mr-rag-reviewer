# -*- coding: utf-8 -*-
"""RAG по репозиторию: чанки файлов, эмбеддинги, поиск релевантного контекста."""

import logging
from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim

log = logging.getLogger("rag")


CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".css", ".scss",
    ".html", ".json", ".yaml", ".yml", ".md", ".rb", ".go", ".rs",
    ".java", ".kt", ".c", ".cpp", ".h", ".hpp", ".cs", ".php",
    ".sql", ".sh", ".bash", ".mjs", ".cjs",
}


def is_code_file(path: str) -> bool:
    return any(path.lower().endswith(ext) for ext in CODE_EXTENSIONS)


def skip_path(path: str) -> bool:
    parts = path.replace("\\", "/").lower().split("/")
    skip = {"node_modules", "venv", ".git", "__pycache__", "dist", "build", ".next"}
    return any(p in skip for p in parts)


def chunk_text(text: str, path: str, max_chars: int = 1200) -> list[tuple[str, str]]:
    lines = text.split("\n")
    chunks = []
    current = []
    current_len = 0
    for line in lines:
        line_len = len(line) + 1
        if current_len + line_len > max_chars and current:
            chunks.append(("\n".join(current), path))
            overlap = current[-2:] if len(current) >= 2 else current
            current = overlap
            current_len = sum(len(l) + 1 for l in overlap)
        current.append(line)
        current_len += line_len
    if current:
        chunks.append(("\n".join(current), path))
    return chunks


class RepoRAG:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        log.info("Загрузка модели эмбеддингов: %s", model_name)
        self.model = SentenceTransformer(model_name)
        self.chunks: list[tuple[str, str]] = []
        self.embeddings = None

    def index_files(self, file_contents: list[tuple[str, str]]) -> None:
        self.chunks = []
        for path, content in file_contents:
            if not is_code_file(path) or skip_path(path):
                continue
            try:
                if isinstance(content, bytes):
                    content = content.decode("utf-8", errors="replace")
                for chunk, chunk_path in chunk_text(content, path):
                    self.chunks.append((chunk, chunk_path))
            except Exception:
                continue
        if not self.chunks:
            self.embeddings = None
            log.warning("Нет чанков для индексации")
            return
        texts = [c[0] for c in self.chunks]
        self.embeddings = self.model.encode(texts, show_progress_bar=len(texts) > 50)
        log.info("Индекс RAG: чанков=%s", len(self.chunks))

    def retrieve(self, query: str, top_k: int = 12) -> list[tuple[str, str]]:
        if not self.chunks or self.embeddings is None:
            return []
        q_emb = self.model.encode([query])
        sim = cos_sim(self.embeddings, q_emb)
        if hasattr(sim, "cpu"):
            sim = sim.cpu().numpy()
        scores = sim.ravel()
        indices = scores.argsort()[-top_k:][::-1]
        seen_paths = set()
        result = []
        for i in indices:
            text, path = self.chunks[i]
            if path not in seen_paths or len(result) < top_k // 2:
                result.append((text, path))
                seen_paths.add(path)
            if len(result) >= top_k:
                break
        return result

    def format_context(self, chunks: list[tuple[str, str]]) -> str:
        out = []
        for text, path in chunks:
            out.append(f"--- {path} ---\n{text}\n")
        return "\n".join(out)
