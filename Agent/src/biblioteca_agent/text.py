"""Operaciones de texto compartidas por el RAG y las herramientas."""

import unicodedata
import re


def area_label(value: str) -> str:
    """Retira solo un prefijo numérico de clasificación de tres cifras.

    No modifica el nombre almacenado ni números propios de una etiqueta.
    """
    return re.sub(r"^\s*\d{3}(?:\.\d+)?(?:\s*[-–—:]\s*|\s+)(?=[^\d\s])", "", value).strip()


def thematic_tokens(value: str) -> set[str]:
    stopwords = set("de del la el las los en para por y e con sobre al a un una estudio estudios metodo metodos general generales".split())
    return {word.removesuffix("s") if len(word) > 5 and word.endswith("s") and not word.endswith("sis") else word
            for word in normalize_text(value).split() if len(word) > 2 and word not in stopwords}


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    cleaned = "".join(char if char.isalnum() else " " for char in without_marks)
    return " ".join(cleaned.split())
