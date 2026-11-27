"""Alcance académico y decisiones por faceta; independientes de revistas/modelos."""
from functools import lru_cache
from collections import Counter
import json
import re

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from .config import RESOURCES_DIR
from .relevance import area_evidence
from .text import area_label, normalize_text


class Facet(BaseModel):
    model_config = ConfigDict(extra='forbid')
    texto: str = Field(min_length=1, max_length=220)
    areas: list[int] = Field(max_length=3)
    relacion: Literal['directa', 'parcial', 'sin_correspondencia']
    razon: str = Field(min_length=1, max_length=160)


class FacetVerdict(BaseModel):
    model_config = ConfigDict(extra='forbid')
    facetas: list[Facet] = Field(min_length=1, max_length=4)


class NamedFacet(Facet):
    areas: list[str] = Field(max_length=3)


class NamedFacetVerdict(BaseModel):
    model_config = ConfigDict(extra='forbid')
    facetas: list[NamedFacet] = Field(min_length=1, max_length=4)


def named_catalog(areas):
    enriched = enrich_areas(areas)
    counts = Counter(a['nombre'] for a in enriched)
    original = {a['id']: a['nombre'] for a in areas}
    names = {a['nombre'] if counts[a['nombre']] == 1 else original[a['id']]: a['id'] for a in enriched}
    if len(names) != len(areas):
        raise ValueError('Etiquetas académicas indistinguibles')
    keys = {value: key for key, value in names.items()}
    context = [{'nombre': keys[a['id']], **{k: a[k] for k in ('alcance', 'general') if k in a}}
               for a in enriched]
    return names, sorted(context, key=lambda a: a['nombre'])


def decode_named(verdict, names):
    rows = []
    for facet in verdict.facetas:
        if set(facet.areas) - names.keys():
            raise ValueError('Etiqueta académica ajena al catálogo')
        rows.append({**facet.model_dump(), 'areas': list(dict.fromkeys(names[name] for name in facet.areas))})
    return FacetVerdict(facetas=rows)


@lru_cache(maxsize=1)
def scopes():
    with (RESOURCES_DIR / 'catalog/academic_scopes.json').open(encoding='utf-8') as source:
        data = json.load(source)
    result = {}
    for row in data['areas']:
        key = normalize_text(area_label(row['nombre']))
        if not key or key in result or not isinstance(row['general'], bool) or not 3 <= len(row['alcance']) <= 350:
            raise ValueError('Glosa académica inválida o duplicada')
        result[key] = row
    return result


def enrich_areas(areas):
    """Las glosas no crean ids, ni relaciones, ni cantidades del catálogo."""
    result = []
    for area in areas:
        label = area_label(area['nombre'])
        scope = scopes().get(normalize_text(label))
        result.append({'id': area['id'], 'nombre': label, **(
            {'alcance': scope['alcance'], 'general': scope['general']} if scope else {})})
    return result


def source_facets(topic):
    """Opciones extractivas para que el modelo no reescriba su evidencia."""
    words = normalize_text(topic).split()
    chunks, current = [], ''
    for word in words:
        if len(current) + len(word) + 1 > 220:
            chunks.append(current)
            current = ''
        current = (current + ' ' + word).strip()
    if current:
        chunks.append(current)
    clauses = re.split(r'\s+(?:y|and|mediante|using|para|con|with)\s+', normalize_text(topic))
    return list(dict.fromkeys(p for p in chunks + clauses if p and len(p) <= 220))[:8]


def resolve_facets(topic, verdict, areas, programs):
    by_id = {a['id']: a for a in enrich_areas(areas)}
    rows = []
    normalized = normalize_text(topic)
    seen = set()
    for facet in verdict.facetas:
        phrase = normalize_text(facet.texto)
        if f' {phrase} ' not in f' {normalized} ':
            raise ValueError('La faceta no es un fragmento único del tema')
        if set(facet.areas) - by_id.keys():
            raise ValueError('Área ajena al catálogo')
        normalized_decision = bool(facet.areas) == (facet.relacion == 'sin_correspondencia')
        # Una categoría paraguas no acredita un programa específico por sí sola.
        allowed = [a for a in facet.areas if facet.relacion != 'sin_correspondencia'
                   and (not by_id[a].get('general') or area_evidence(topic, [by_id[a]]))]
        if phrase in seen:
            prior = next(row for row in rows if normalize_text(row['texto']) == phrase)
            prior['areas'] = sorted(set(prior['areas']) | set(allowed)) if prior['areas'] and allowed else []
            prior['relacion'] = 'parcial' if prior['relacion'] != facet.relacion else prior['relacion']
            if not prior['areas']:
                prior['relacion'] = 'sin_correspondencia'
            continue
        seen.add(phrase)
        rows.append({**facet.model_dump(), 'areas': allowed,
                     'relacion': facet.relacion if allowed else 'sin_correspondencia',
                     'decision_normalizada': normalized_decision})
    accepted = {a for row in rows for a in row['areas']}
    matching = {p['id'] for p in programs if set(p.get('areas', [])) & accepted}
    return accepted, matching, rows


def facet_support(program_areas, facets):
    return [f['texto'] for f in facets if set(f['areas']) & set(program_areas)]


def select_diverse(candidates, programs, facets, limit=3):
    """Cubrir facetas distintas antes que llenar puestos con la misma evidencia."""
    by_id = {p['id']: p.get('areas', []) for p in programs}
    def evidence(program):
        return {(i, a) for i, facet in enumerate(facets) for a in facet['areas'] if a in by_id[program['id']]}
    remaining, chosen, covered = list(candidates), [], set()
    while remaining and len(chosen) < limit:
        best = max(remaining, key=lambda p: (
            len(evidence(p) - covered), p['puntuacion'], -p['id']))
        support = evidence(best)
        if not support - covered:
            break
        chosen.append(best)
        covered.update(support)
        remaining.remove(best)
    return chosen
