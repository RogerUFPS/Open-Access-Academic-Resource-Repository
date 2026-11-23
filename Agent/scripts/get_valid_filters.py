#!/usr/bin/env python3
from biblioteca_agent.catalog import load_snapshot
from biblioteca_agent.cli import run


def handler(_args):
    return {"filtros": load_snapshot()["filtros"]}


if __name__ == "__main__":
    run(handler)
