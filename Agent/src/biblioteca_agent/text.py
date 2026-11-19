"""Operaciones de texto compartidas por el RAG y las herramientas."""

import unicodedata


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    cleaned = "".join(char if char.isalnum() else " " for char in without_marks)
    return " ".join(cleaned.split())
