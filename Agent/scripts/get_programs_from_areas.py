#!/usr/bin/env python3
from biblioteca_agent.catalog import load_snapshot
from biblioteca_agent.cli import require_ids, run


def handler(args):
    requested = require_ids(args.get("areas"), "areas")
    data = load_snapshot()
    known = {item["id"] for item in data["areas"]}
    unknown = sorted(set(requested) - known)
    if unknown:
        raise ValueError(f"Áreas inexistentes: {unknown}")
    result = []
    requested_set = set(requested)
    for program in data["programas"]:
        matches = sorted(requested_set.intersection(program.get("areas", [])))
        if matches:
            result.append({
                "programa_id": program["id"],
                "nombre": program["nombre"],
                "areas_coincidentes": matches,
                "cantidad_areas_coincidentes": len(matches),
            })
    result.sort(key=lambda item: (-item["cantidad_areas_coincidentes"], item["programa_id"]))
    return {"programas": result}


if __name__ == "__main__":
    run(handler)
