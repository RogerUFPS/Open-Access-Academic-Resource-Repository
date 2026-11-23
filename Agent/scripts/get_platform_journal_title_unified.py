#!/usr/bin/env python3
from biblioteca_agent.catalog import journal_matches, load_snapshot
from biblioteca_agent.cli import require_ids, run
from biblioteca_agent.text import normalize_text


def handler(args):
    platform_ids = require_ids(args.get("plataformas"), "plataformas")
    program_ids = set(require_ids(args.get("programas"), "programas"))
    filters = args.get("filtros", {})
    if not isinstance(filters, dict):
        raise ValueError("'filtros' debe ser un objeto.")
    data = load_snapshot()
    known_platforms = {item["id"] for item in data["plataformas"]}
    unknown = sorted(set(platform_ids) - known_platforms)
    if unknown:
        raise ValueError(f"Plataformas inexistentes: {unknown}")
    rows = []
    for platform_id in platform_ids:
        titles = {
            normalize_text(journal["titulo"])
            for journal in data["revistas"]
            if platform_id in journal.get("plataformas", [])
            and program_ids.intersection(journal.get("programas", []))
            and journal_matches(journal, filters, data["filtros"])
        }
        rows.append({"plataforma_id": platform_id, "texto": " ".join(sorted(titles))})
    return {"textos_unificados": rows}


if __name__ == "__main__":
    run(handler)
