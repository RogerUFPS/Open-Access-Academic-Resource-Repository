"""Evidencia léxica y especificidad del grafo, sin ids de catálogo fijos."""
from collections import Counter
import math

from .text import area_label, thematic_tokens


def area_evidence(topic, areas):
    tokens = thematic_tokens(topic)
    result = {}
    for area in areas:
        label = thematic_tokens(area_label(area["nombre"]))
        shared = tokens & label
        if label and shared and len(shared) / len(label) >= .65:
            result[area["id"]] = len(shared) / len(label)
    return result


def graph_specificity(programs):
    counts = Counter(a for p in programs for a in set(p.get("areas", [])))
    threshold = max(3, math.ceil(len(programs) * .05))
    return {a: 1 / math.sqrt(n) for a, n in counts.items()}, {a for a, n in counts.items() if n >= threshold}
