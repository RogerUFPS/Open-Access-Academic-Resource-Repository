#!/usr/bin/env python3
from biblioteca_agent.cli import run
from biblioteca_agent.text import normalize_text


def handler(args):
    text = args.get("texto")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("'texto' debe ser una cadena no vacía.")
    return {"prompt_normalizado": normalize_text(text)}


if __name__ == "__main__":
    run(handler)
