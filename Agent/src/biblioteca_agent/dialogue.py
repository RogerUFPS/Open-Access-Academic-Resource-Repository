"""Transiciones de consulta; nunca se vuelve a interpretar todo el historial."""
import re
from .text import normalize_text


def resolve_turn(prompt, previous_topic, intent, claims, previous_claims, definitions):
    text = normalize_text(prompt)
    removed, filter_words = set(), set()
    deletion = bool(re.search(r"\b(?:sin|quita|quitar|elimina|eliminar|cualquier|without|remove|any)\b", text))
    if deletion:
        for definition in definitions:
            labels = {normalize_text(definition['nombre']), normalize_text(definition['clave']).replace('_', ' ')}
            labels.update(word for word in normalize_text(definition['nombre']).split() if len(word) >= 4)
            if definition['clave'] == 'idioma':
                labels.update({'idioma', 'idiomas', 'language', 'languages'})
            if definition['tipo'] == 'rango_anios':
                labels.update({'fecha', 'fechas', 'periodo', 'year', 'years', 'date', 'dates', 'anio', 'anos'})
            filter_words.update(word for label in labels for word in label.split())
            if any(label in text for label in labels):
                removed.add(definition['id'])
    residual = text
    for claim in claims:
        residual = residual.replace(normalize_text(claim.evidencia), ' ')
    connectors = set('y e and ahora solo solamente unicamente en in entre de del al el la los las con por favor quiero necesito que sean sin restriccion restricciones idioma idiomas language languages conserva conservar mismo misma tema todos todas cualquier quita quitar elimina eliminar filtro filtros a partir desde hasta remove without any restriction restrictions keep same topic'.split()) | filter_words
    filter_only = bool(previous_topic and (claims or removed) and set(residual.split()) <= connectors)
    independent = bool(re.search(r'\b(?:busco|investigo|investigar|investigaciones|literatura|research|looking)\b', text)) and not filter_only
    marker = bool(re.match(r'^(?:y|e|and|ademas|tambien|ahora|solo|solamente|unicamente|pero|mejor|lo mismo|esas|esos)\b', text))
    follow = bool(previous_topic and not independent and (filter_only or marker and intent.es_seguimiento or intent.operacion in {'refinar', 'filtros'}))
    if intent.operacion == 'nueva' and not filter_only:
        follow = False
    if follow:
        overridden = {c.id for c in claims} | removed
        claims = [c for c in previous_claims if c.id not in overridden] + claims
        if filter_only or intent.operacion == 'filtros':
            intent.tema = previous_topic
            intent.conceptos = []
            intent.areas_implicitas = []
            intent.areas_ambiguas = []
            intent.evidencias_areas = {}
            intent.tipo = 'buscar_literatura'
    intent.es_seguimiento = follow
    return claims, follow, removed


def render_state(topic, programs, claims):
    """Representación compatible con clientes antiguos, sin instrucciones previas."""
    restrictions = [('idioma: ' if isinstance(c.valor, list) and all(len(v) == 2 for v in c.valor) else '') + c.evidencia for c in claims]
    return '\n'.join([topic, *('para ' + p['nombre'] for p in programs), *restrictions])[-4000:]
