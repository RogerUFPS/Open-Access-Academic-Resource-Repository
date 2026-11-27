"""Métricas observables, no evaluadas por otro LLM."""
import unicodedata


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))


def score(case, response, analysis):
    failures = []
    names = [normalized(p['nombre']) for p in response['programas_seleccionados']]
    if response['estado'] not in case['estados']:
        failures.append('estado_no_esperado')
    if case.get('sin_programas') and names:
        failures.append('programas_no_justificados')
    for alternatives in case.get('requeridos', []):
        if not any(normalized(label) in name for label in alternatives for name in names):
            failures.append('faceta_sin_programa:' + '|'.join(alternatives))
    if case.get('sin_filtros_catalogo') and analysis.get('filtros_catalogo'):
        failures.append('filtros_heredados')
    # Ids de filtros dependen del catálogo; comprobar idioma por valor, no id fijo.
    if case.get('filtros_esperados') and not any(v == ['en'] for v in analysis.get('filtros_catalogo', {}).values()):
        failures.append('idioma_no_conservado')
    return {'cumple_referencia': not failures, 'fallos': failures,
        'falso_positivo_fuera_cobertura': case['tipo'] == 'sin_cobertura' and bool(names),
        'rechazo_innecesario': case['tipo'] == 'pertinente' and response['estado'] == 'informacion_insuficiente'}
