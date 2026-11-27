import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parent / 'evaluation'
spec = importlib.util.spec_from_file_location('evaluation_scoring', ROOT / 'scoring.py')
scoring = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scoring)


class EvaluationTests(unittest.TestCase):
    def test_corpus_has_disjoint_groups_and_no_cross_group_sessions(self):
        cases = json.loads((ROOT / 'cases.json').read_text())['casos']
        self.assertEqual(len({c['id'] for c in cases}), len(cases))
        self.assertEqual({c['grupo'] for c in cases}, {'ajuste', 'reservado'})
        for session in {c.get('sesion') for c in cases} - {None}:
            self.assertEqual(len({c['grupo'] for c in cases if c.get('sesion') == session}), 1)

    def test_metrics_separate_false_positive_and_unnecessary_refusal(self):
        case = {'tipo': 'sin_cobertura', 'estados': ['informacion_insuficiente'], 'sin_programas': True}
        response = {'estado': 'ok', 'programas_seleccionados': [{'nombre': 'Programa'}]}
        self.assertTrue(scoring.score(case, response, {})['falso_positivo_fuera_cobertura'])
        self.assertFalse(scoring.score(case, response, {})['cumple_referencia'])
        case = {'tipo': 'pertinente', 'estados': ['ok'], 'requeridos': [['matemáticas']]}
        response = {'estado': 'informacion_insuficiente', 'programas_seleccionados': []}
        self.assertTrue(scoring.score(case, response, {})['rechazo_innecesario'])
