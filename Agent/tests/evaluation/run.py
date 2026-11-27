"""Evaluación explícita desde el contenedor Backend. No persiste chats ni cambia modelos."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import threading
import time

from scoring import score


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', choices=['qwen', 'glm', 'llama'], default='qwen')
    parser.add_argument('--group', choices=['ajuste', 'reservado', 'todos'], default='ajuste')
    parser.add_argument('--ids', default='')
    parser.add_argument('--workers', type=int, choices=[1, 2], default=2)
    parser.add_argument('--timeout', type=int, default=900, help='Límite por consulta, incluido arranque en frío (1..900 s).')
    args = parser.parse_args()
    sys.path.insert(0, str(Path.cwd()))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.conf import settings
    if not 1 <= args.timeout <= 900:
        parser.error('--timeout debe estar entre 1 y 900')
    settings.AGENT_TIMEOUT_SECONDS = args.timeout
    from apps.agent.client import AgentClient
    from apps.agent.views import cached_public_snapshot
    from apps.agent.tasks import validate_result
    snapshot, etag = cached_public_snapshot()
    cases = json.loads(Path(__file__).with_name('cases.json').read_text())['casos']
    selected = set(args.ids.split(',')) if args.ids else None
    cases = [c for c in cases if (args.group == 'todos' or c['grupo'] == args.group) and (not selected or c['id'] in selected)]
    if not cases:
        parser.error('No hay casos seleccionados')
    sessions = {}
    for case in cases:
        sessions.setdefault(case.get('sesion', case['id']), []).append(case)
    results = []
    unavailable = threading.Event()
    print(json.dumps({'modelo': args.model, 'digest': etag.strip('"'), 'casos': len(cases), 'grupo': args.group}), flush=True)

    def execute(group):
        previous_prompt = previous_topic = ''
        rows = []
        for case in group:
            if unavailable.is_set():
                rows.append({'id': case['id'], 'no_ejecutado': True, 'cumple_referencia': False})
                continue
            started = time.monotonic()
            row = {'id': case['id'], 'prompt': case['prompt'], 'modelo': args.model, 'tipo': case['tipo']}
            try:
                with AgentClient(args.model) as client:
                    payload = client.query(case['prompt'], snapshot, etag, previous_prompt, previous_topic)
                response, analysis = validate_result(payload, args.model, snapshot)
                if response['estado'] == 'error_sistema':
                    unavailable.set()
                counts = []
                for search in response['busquedas']:
                    pid = search['plataforma_id']
                    if pid is None:
                        continue
                    programs = {p['id'] for p in response['programas_seleccionados']}
                    journals = [j for j in snapshot['revistas'] if pid in j['plataformas'] and programs.intersection(j['programas'])]
                    for definition in snapshot['filtros']:
                        values = analysis.get('filtros_catalogo', {}).get(str(definition['id']))
                        if values and definition['clave'] == 'idioma':
                            journals = [j for j in journals if set(values).intersection(j['idiomas'])]
                    count = len({j['id'] for j in journals})
                    counts.append({'cantidad': count, 'correcto': f'Reúne {count} revista' in search['justificacion']})
                row.update(respuesta=response, analisis=analysis, conteos=counts, **score(case, response, analysis))
                previous_prompt, previous_topic = analysis.get('consulta_resuelta', case['prompt']), analysis.get('tema', '')
            except Exception as exc:
                row.update(error_tipo=type(exc).__name__, cumple_referencia=False)
                unavailable.set()
                # No imprimir excepciones, URLs, headers ni credenciales.
            row['segundos'] = round(time.monotonic() - started, 2)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            rows.append(row)
        return rows

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for rows in pool.map(execute, sessions.values()):
            results.extend(rows)
    print(json.dumps({'resumen': {'total': len(results), 'cumplen': sum(r['cumple_referencia'] for r in results),
        'falsos_positivos_fuera_cobertura': sum(r.get('falso_positivo_fuera_cobertura', False) for r in results),
        'rechazos_innecesarios': sum(r.get('rechazo_innecesario', False) for r in results),
        'errores_sistema': sum(r.get('respuesta', {}).get('estado') == 'error_sistema' or 'error_tipo' in r for r in results),
        'no_ejecutados': sum(r.get('no_ejecutado', False) for r in results),
        'conteos_incorrectos': sum(not c['correcto'] for r in results for c in r.get('conteos', []))}}), flush=True)


if __name__ == '__main__':
    main()
