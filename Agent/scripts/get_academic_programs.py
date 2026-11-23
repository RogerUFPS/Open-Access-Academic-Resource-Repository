#!/usr/bin/env python3
from biblioteca_agent.catalog import load_snapshot
from biblioteca_agent.cli import run
from biblioteca_agent.text import normalize_text


def handler(_args):
    programs = load_snapshot()["programas"]
    return {"programas": [
        {"id": item["id"], "nombre": item["nombre"], "nombre_normalizado": normalize_text(item["nombre"])}
        for item in programs
    ]}


if __name__ == "__main__":
    run(handler)
