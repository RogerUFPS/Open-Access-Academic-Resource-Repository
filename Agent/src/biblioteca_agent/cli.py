"""Contrato JSON común para las herramientas ejecutables de la skill."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable


def require_ids(value: Any, field: str) -> list[int]:
    if not isinstance(value, list) or any(type(item) is not int for item in value):
        raise ValueError(f"'{field}' debe ser una lista de enteros.")
    return list(dict.fromkeys(value))


def _read_args() -> dict[str, Any]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", help="Objeto JSON de entrada; si se omite se lee stdin.")
    namespace = parser.parse_args()
    raw = namespace.json if namespace.json is not None else sys.stdin.read()
    if not raw.strip():
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("La entrada debe ser un objeto JSON.")
    return value


def run(handler: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    try:
        result = handler(_read_args())
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, separators=(",", ":")))
        raise SystemExit(2) from exc
