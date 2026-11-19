#!/usr/bin/env python3
from biblioteca_agent.catalog import journal_matches, load_snapshot
from biblioteca_agent.cli import require_ids, run


def handler(args):
    requested = require_ids(args.get("programas"), "programas")
    filters = args.get("filtros", {})
    if not isinstance(filters, dict):
        raise ValueError("'filtros' debe ser un objeto cuyas claves sean ids.")
    data = load_snapshot()
    known_programs = {item["id"] for item in data["programas"]}
    unknown = sorted(set(requested) - known_programs)
    if unknown:
        raise ValueError(f"Programas inexistentes: {unknown}")
    result = []
    for platform in data["plataformas"]:
        counts = []
        journals = [item for item in data["revistas"] if platform["id"] in item.get("plataformas", [])]
        for program_id in requested:
            count = sum(
                1 for journal in journals
                if program_id in journal.get("programas", [])
                and journal_matches(journal, filters, data["filtros"])
            )
            if count:
                counts.append({"programa_id": program_id, "cantidad_revistas": count})
        if counts:
            result.append({"plataforma_id": platform["id"], "nombre": platform["nombre"], "programas": counts})
    return {"plataformas": result}


if __name__ == "__main__":
    run(handler)
