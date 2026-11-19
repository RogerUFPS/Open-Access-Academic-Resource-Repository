#!/usr/bin/env python3
from biblioteca_agent.catalog import load_snapshot
from biblioteca_agent.cli import require_ids, run


FIELD_KEYS = ("title", "author", "subject", "issn", "language", "year")


def _field(value):
    if not value:
        return {"identificador": None, "plantilla": None}
    # El backend solo garantiza un identificador. Una plantilla es utilizable
    # únicamente cuando el administrador almacenó explícitamente `{}`.
    return {
        "identificador": value,
        "plantilla": value if "{}" in value else None,
    }


def handler(args):
    requested = require_ids(args.get("plataformas"), "plataformas")
    data = load_snapshot()
    platforms = {item["id"]: item for item in data["plataformas"]}
    unknown = sorted(set(requested) - platforms.keys())
    if unknown:
        raise ValueError(f"Plataformas inexistentes: {unknown}")
    result = []
    for platform_id in requested:
        platform = platforms[platform_id]
        syntax = platform.get("valid_sintaxis")
        if not syntax:
            result.append({"plataforma_id": platform_id, "configurada": False})
            continue
        operators = [str(item).upper() for item in syntax.get("booleans", [])]
        fields = syntax.get("fields", {})
        result.append({
            "plataforma_id": platform_id,
            "configurada": True,
            "operadores": {key: key in operators for key in ("AND", "OR", "NOT")},
            "parentesis": bool(syntax.get("parenthesis", False)),
            "campos": {key: _field(fields.get(key)) for key in FIELD_KEYS},
            "frase_exacta": None,
            "truncamiento": None,
            "caracteres_escape": None,
            "max_longitud": None,
            "idiomas": platform.get("idiomas", []),
            "idioma_principal": platform.get("idioma_principal"),
            "capacidades_no_modeladas": [
                "frase_exacta", "truncamiento", "caracteres_escape", "max_longitud"
            ],
        })
    return {"sintaxis": result}


if __name__ == "__main__":
    run(handler)
