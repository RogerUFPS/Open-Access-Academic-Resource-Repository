#!/usr/bin/env python3
import json

import yake

from biblioteca_agent.cli import run
from biblioteca_agent.config import RESOURCES_DIR
from biblioteca_agent.text import normalize_text


GENERIC_PATH = RESOURCES_DIR / "palabras_genericas.json"


def _extract(text, language, origin, limit=20):
    if not text.strip():
        return []
    extractor = yake.KeywordExtractor(lan=language, n=3, dedupLim=0.85, top=limit)
    raw = extractor.extract_keywords(text)
    if not raw:
        return []
    scores = [score for _term, score in raw]
    low, high = min(scores), max(scores)
    return [
        {
            "termino": normalize_text(term),
            "relevancia": round(1.0 if high == low else 1 - ((score - low) / (high - low)), 4),
            "origen": origin,
        }
        for term, score in raw
        if normalize_text(term)
    ]


def handler(args):
    prompt = args.get("prompt_normalizado", "")
    platform_text = args.get("texto_unificado", "")
    language = args.get("idioma_texto", "es")
    threshold = float(args.get("umbral_relevancia", 0.5))
    if not 0 <= threshold <= 1:
        raise ValueError("'umbral_relevancia' debe estar entre 0 y 1.")
    if language not in {"es", "en", "pt"}:
        language = "es"
    keywords = _extract(prompt, "es", "prompt") + _extract(platform_text, language, "plataforma")
    generic = set()
    if args.get("excluir_genericas", True):
        with GENERIC_PATH.open(encoding="utf-8") as source:
            generic = {normalize_text(item) for item in json.load(source)}
    best = {}
    for item in keywords:
        if item["relevancia"] < threshold or item["termino"] in generic:
            continue
        key = (item["termino"], item["origen"])
        if key not in best or best[key]["relevancia"] < item["relevancia"]:
            best[key] = item
    ordered = sorted(best.values(), key=lambda item: (-item["relevancia"], item["termino"], item["origen"]))
    return {"palabras_clave": ordered}


if __name__ == "__main__":
    run(handler)
