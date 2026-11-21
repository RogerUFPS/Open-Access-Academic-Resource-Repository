"""Catalog-backed public selections and immutable provider query snapshots."""
import hashlib
import json
import re

from rest_framework import serializers

OPENALEX_FIELDS = {"country"}
DOAJ_FIELDS = {"title", "publisher", "subject", "language"}


def normalize_filters(value):
    """Validate public input: catalog IDs, never provider codes or raw queries."""
    if not isinstance(value, dict) or set(value) - (OPENALEX_FIELDS | DOAJ_FIELDS):
        raise serializers.ValidationError("Filtros desconocidos; consulta filter-options.")
    normalized = {}
    for key, item in value.items():
        if key in {"country", "publisher", "language"}:
            if type(item) is not int or not 0 < item <= 9223372036854775807:
                raise serializers.ValidationError({key: "Debe ser un ID entero positivo del catálogo."})
        else:
            if not isinstance(item, str) or not item.strip() or len(item) > 120:
                raise serializers.ValidationError({key: "Debe ser texto de 1 a 120 caracteres."})
            item = item.strip().casefold()
        normalized[key] = item
    return dict(sorted(normalized.items()))


def _text(value):
    return " ".join(value.split()).casefold()


def resolve_filters(value):
    """Resolve once per validation/execution, never once per remote record."""
    from apps.catalog.models import Country, Editorial, Language

    value = normalize_filters(value)
    catalog_fields = {
        "country": (Country, "abbreviation", "country_code"),
        "publisher": (Editorial, "name", "publisher_exact"),
        "language": (Language, "abbreviation", "language"),
    }
    resolved = {}
    for key, item in value.items():
        if key not in catalog_fields:
            resolved[key] = item
            continue
        model, field, target = catalog_fields[key]
        entry = model.objects.filter(pk=item).values_list(field, flat=True).first()
        if entry is None:
            raise serializers.ValidationError({key: "El ID no existe o está archivado en el catálogo."})
        entry = _text(entry)
        if key == "country":
            if not re.fullmatch(r"[a-z]{2}", entry):
                raise serializers.ValidationError({key: "El país no tiene una abreviatura ISO de dos letras válida."})
            entry = entry.upper()
        elif key == "language":
            if not re.fullmatch(r"[a-z]{2,3}", entry):
                raise serializers.ValidationError({key: "El idioma no tiene una abreviatura ISO de dos o tres letras válida."})
        elif not entry:
            raise serializers.ValidationError({key: "La editorial no tiene un nombre válido."})
        resolved[target] = entry
    return dict(sorted(resolved.items()))


def filter_key(value):
    """Key provider values, preserving global and historical stream identities."""
    normalized = dict(value)
    if isinstance(normalized.get("country_code"), str):
        normalized["country_code"] = normalized["country_code"].strip().upper()
    return hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest() if normalized else ""


def openalex_filter(value):
    if not isinstance(value, dict) or set(value) - {"country_code"}:
        raise ValueError("Filtro incompatible con OpenAlex.")
    parts = ["type:journal"]
    if "country_code" in value:
        code = value["country_code"]
        if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z]{2}", code.strip()):
            raise ValueError("Código de país inválido para OpenAlex.")
        parts.append(f"country_code:{code.strip().upper()}")
    return ",".join(parts)


def openalex_matches(value, item):
    expected = value.get("country_code")
    return expected is None or (
        isinstance(item.get("country_code"), str)
        and item["country_code"].strip().upper() == expected.upper()
    )


def doaj_matches(harvester, record):
    for key, expected in harvester.harvest.resolved_filters.items():
        if key not in {"title", "publisher", "publisher_exact", "subject", "language"}:
            raise ValueError("Filtro incompatible con DOAJ.")
        field = "publisher" if key == "publisher_exact" else key
        values = [_text(v) for v in harvester._dc_values(record, field)]
        # publisher without suffix is retained for immutable historical snapshots.
        if not any(expected == v if key in {"language", "publisher_exact"} else expected in v for v in values):
            return False
    return True


def filter_options():
    def catalog(endpoint, resolved_field):
        return {
            "type": "integer", "catalog_endpoint": f"/api/catalog/{endpoint}/",
            "value_field": "id", "label_field": "name",
            "resolved_field": resolved_field, "match": "exact",
        }
    return {
        "openalex": {"country": catalog("countries", "abbreviation")},
        "doaj": {
            "publisher": catalog("editorials", "name"),
            "language": catalog("languages", "abbreviation"),
            "title": {"type": "string", "max_length": 120, "match": "contains"},
            "subject": {"type": "string", "max_length": 120, "match": "contains"},
        },
        "combination": "AND",
        "max_quantity_counts": "scanned records including skipped",
    }
