"""Strict provider selection contract; never accept raw remote query expressions."""
import hashlib
import json
import re

from rest_framework import serializers

OPENALEX_FIELDS = {"country_code"}
DOAJ_FIELDS = {"title", "publisher", "subject", "language"}


def normalize_filters(value):
    if not isinstance(value, dict) or set(value) - (OPENALEX_FIELDS | DOAJ_FIELDS):
        raise serializers.ValidationError("Filtros desconocidos; consulta filter-options.")
    normalized = {}
    for key, item in value.items():
        if not isinstance(item, str) or not item.strip() or len(item) > 120:
            raise serializers.ValidationError(f"{key} debe ser texto de 1 a 120 caracteres.")
        item = item.strip().casefold()
        if key == "country_code":
            if not re.fullmatch(r"[a-z]{2}", item):
                raise serializers.ValidationError("country_code debe ser ISO de dos letras.")
            item = item.upper()
        normalized[key] = item
    return dict(sorted(normalized.items()))


def filter_key(value):
    # Keep historical selections addressable even if their filters are retired.
    if isinstance(value, dict) and not set(value) - (OPENALEX_FIELDS | DOAJ_FIELDS):
        value = normalize_filters(value)
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest() if value else ""


def openalex_filter(value):
    value = normalize_filters(value)
    parts = ["type:journal"]
    for key, item in sorted(value.items()):
        if key not in OPENALEX_FIELDS:
            raise ValueError("Filtro incompatible con OpenAlex.")
        parts.append(f"{key}:{item}")
    return ",".join(parts)


def doaj_matches(harvester, record):
    for key, expected in harvester.harvest.selection_filters.items():
        if key not in DOAJ_FIELDS:
            raise ValueError("Filtro incompatible con DOAJ.")
        values = [v.casefold() for v in harvester._dc_values(record, key)]
        if not any(expected == v if key == "language" else expected in v for v in values):
            return False
    return True
