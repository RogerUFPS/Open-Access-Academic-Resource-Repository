#!/usr/bin/env python3
from biblioteca_agent.catalog import load_snapshot
from biblioteca_agent.cli import require_ids, run


def handler(args):
    requested = require_ids(args.get("programas"), "programas")
    data = load_snapshot()
    programs = {item["id"]: item for item in data["programas"]}
    areas = {item["id"]: item["nombre"] for item in data["areas"]}
    unknown = sorted(set(requested) - programs.keys())
    if unknown:
        raise ValueError(f"Programas inexistentes: {unknown}")
    return {"programas": [
        {
            "programa_id": program_id,
            "areas": [
                {"area_id": area_id, "nombre": areas[area_id]}
                for area_id in programs[program_id].get("areas", []) if area_id in areas
            ],
        }
        for program_id in requested
    ]}


if __name__ == "__main__":
    run(handler)
