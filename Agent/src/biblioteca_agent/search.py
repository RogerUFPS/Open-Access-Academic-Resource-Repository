"""Constructor conservador: conceptos verificados y capacidades del catálogo."""
import re

from .text import normalize_text


def build_topic_query(topic, concepts, keywords, syntax, destinations=()):
    topic = normalize_text(topic)
    groups = list(dict.fromkeys(normalize_text(c) for c in concepts if normalize_text(c)))
    groups = [g for g in groups if re.search(r"(?<!\w)" + re.escape(g) + r"(?!\w)", topic)]
    destinations = {normalize_text(d) for d in destinations}
    groups = [g for g in groups if g not in destinations or re.search(r"(?<!\w)" + re.escape(g) + r"(?!\w)", topic)]
    # Eliminar conceptos contenidos, sin confundir substrings de palabras.
    groups = [g for g in groups if not any(g != other and re.search(r"(?<!\w)" + re.escape(g) + r"(?!\w)", other) for other in groups)]
    # El clasificador no puede añadir conceptos ni perder palabras temáticas.
    noise = set("de del la el las los en para por y e con sobre al a un una and or in for of the with on e ou em".split())
    tokens = set(topic.split()) - noise
    represented = set(" ".join(groups).split())
    if not groups or any(not set(g.split()) <= set(topic.split()) for g in groups):
        groups = [topic]
    elif not tokens <= represented:
        # El modelo puede omitir modificadores como 'efectividad' o 'prevenir'.
        # Recuperarlos del tema, no de títulos ni de sinónimos generados.
        spans = [re.search(r"(?<!\w)" + re.escape(g) + r"(?!\w)", topic) for g in groups]
        if any(span is None for span in spans):
            groups = [topic]
        else:
            ordered = sorted(spans, key=lambda span: span.start())
            recovered, end = [], 0
            for span in ordered:
                if span.start() < end:
                    recovered = []
                    break
                gap = topic[end:span.start()].strip()
                recovered.append((gap + " " if set(gap.split()) - noise else "") + span.group())
                end = span.end()
            tail = topic[end:].strip()
            if recovered and set(tail.split()) - noise:
                recovered[-1] += " " + tail
            groups = recovered if recovered and tokens <= set(" ".join(recovered).split()) else [topic]
    # YAKE prioriza grupos completos; nunca añade términos de otras revistas.
    scores = {normalize_text(k["termino"]): k["relevancia"] for k in keywords if k["origen"] == "prompt"}
    groups.sort(key=lambda g: -max((score for term, score in scores.items() if term in g), default=0))
    if not syntax["operadores"].get("AND"):
        return topic
    query = " AND ".join(groups)
    if not query.strip() or query.endswith(" AND"):
        raise ValueError("Cadena temática inválida")
    return query
