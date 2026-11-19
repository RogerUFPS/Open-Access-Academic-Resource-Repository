#!/usr/bin/env python3
from biblioteca_agent.catalog import load_snapshot
from biblioteca_agent.cli import run
from biblioteca_agent.text import normalize_text


def handler(_args):
    areas = load_snapshot()["areas"]
    return {"areas": [
        {"id": item["id"], "nombre": item["nombre"], "nombre_normalizado": normalize_text(item["nombre"])}
        for item in areas
    ]}


if __name__ == "__main__":
    run(handler)
