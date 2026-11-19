"""Repositorio RAG local respaldado por SQLite FTS5."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .text import normalize_text


INTENT_FIELDS = {
    "tipo",
    "tema",
    "programas_explicitos",
    "areas_explicitas",
    "areas_implicitas",
    "areas_ambiguas",
    "filtros",
}


def validate_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not documents:
        raise ValueError("El lote RAG no puede estar vacío.")
    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, document in enumerate(documents, 1):
        if not isinstance(document, dict):
            raise ValueError(f"El documento {index} debe ser un objeto JSON.")
        document_id = str(document.get("id", "")).strip()
        prompt = str(document.get("prompt", "")).strip()
        notes = str(document.get("notas", "")).strip()
        response = document.get("respuesta")
        if not document_id or document_id in seen:
            raise ValueError(f"ID RAG vacío o duplicado en el documento {index}.")
        if len(prompt) < 3:
            raise ValueError(f"Prompt inválido en {document_id}.")
        if not isinstance(response, dict) or set(response) != INTENT_FIELDS:
            raise ValueError(f"Respuesta de intención inválida en {document_id}.")
        if response["tipo"] not in {"buscar_literatura", "fuera_de_tema"}:
            raise ValueError(f"Tipo de intención inválido en {document_id}.")
        if not isinstance(response["tema"], str) or not isinstance(response["filtros"], dict):
            raise ValueError(f"Tema o filtros inválidos en {document_id}.")
        for field in (
            "programas_explicitos",
            "areas_explicitas",
            "areas_implicitas",
            "areas_ambiguas",
        ):
            values = response[field]
            if not isinstance(values, list) or any(type(value) is not int for value in values):
                raise ValueError(f"{field} debe ser una lista de enteros en {document_id}.")
            if values:
                raise ValueError(
                    f"{field} debe quedar vacío en {document_id}; los ids provienen del catálogo activo."
                )
        seen.add(document_id)
        validated.append({"id": document_id, "prompt": prompt, "respuesta": response, "notas": notes})
    return validated


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    documents = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                documents.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON inválido en {path.name}:{line_number}: {exc.msg}") from exc
    return validate_documents(documents)


class RagStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS rag_documents (
                    id TEXT PRIMARY KEY,
                    prompt TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT ''
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS rag_documents_fts USING fts5(
                    id UNINDEXED, prompt, notes, content='rag_documents', content_rowid='rowid'
                );
                CREATE TRIGGER IF NOT EXISTS rag_ai AFTER INSERT ON rag_documents BEGIN
                    INSERT INTO rag_documents_fts(rowid, id, prompt, notes)
                    VALUES (new.rowid, new.id, new.prompt, new.notes);
                END;
                CREATE TRIGGER IF NOT EXISTS rag_ad AFTER DELETE ON rag_documents BEGIN
                    INSERT INTO rag_documents_fts(rag_documents_fts, rowid, id, prompt, notes)
                    VALUES ('delete', old.rowid, old.id, old.prompt, old.notes);
                END;
                CREATE TRIGGER IF NOT EXISTS rag_au AFTER UPDATE ON rag_documents BEGIN
                    INSERT INTO rag_documents_fts(rag_documents_fts, rowid, id, prompt, notes)
                    VALUES ('delete', old.rowid, old.id, old.prompt, old.notes);
                    INSERT INTO rag_documents_fts(rowid, id, prompt, notes)
                    VALUES (new.rowid, new.id, new.prompt, new.notes);
                END;
            """)

    def upsert(self, documents: list[dict[str, Any]]) -> int:
        documents = validate_documents(documents)
        with self._lock, self._connect() as connection:
            for document in documents:
                connection.execute(
                    """INSERT INTO rag_documents(id, prompt, response_json, notes)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET
                         prompt=excluded.prompt,
                         response_json=excluded.response_json,
                         notes=excluded.notes""",
                    (
                        document["id"],
                        document["prompt"],
                        json.dumps(document["respuesta"], ensure_ascii=False),
                        document["notas"],
                    ),
                )
        return len(documents)

    def replace_all(self, documents: list[dict[str, Any]]) -> int:
        documents = validate_documents(documents)
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM rag_documents")
            for document in documents:
                connection.execute(
                    "INSERT INTO rag_documents(id, prompt, response_json, notes) VALUES (?, ?, ?, ?)",
                    (
                        document["id"],
                        document["prompt"],
                        json.dumps(document["respuesta"], ensure_ascii=False),
                        document["notas"],
                    ),
                )
            connection.execute("INSERT INTO rag_documents_fts(rag_documents_fts) VALUES ('optimize')")
        return len(documents)

    def count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM rag_documents").fetchone()[0])

    def search(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        tokens = [token for token in normalize_text(query).split() if len(token) > 1]
        if not tokens:
            return []
        expression = " OR ".join(f'"{token}"' for token in tokens[:16])
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT d.id, d.prompt, d.response_json, d.notes,
                          bm25(rag_documents_fts) AS rank
                   FROM rag_documents_fts
                   JOIN rag_documents d ON d.rowid = rag_documents_fts.rowid
                   WHERE rag_documents_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (expression, max(1, min(limit, 10))),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "prompt": row["prompt"],
                "respuesta": json.loads(row["response_json"]),
                "notas": row["notes"],
                "relevancia_fts": round(-float(row["rank"]), 6),
            }
            for row in rows
        ]
