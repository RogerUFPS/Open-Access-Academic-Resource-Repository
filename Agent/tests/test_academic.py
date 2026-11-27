import unittest
from biblioteca_agent.academic import FacetVerdict, enrich_areas, resolve_facets, facet_support, scopes, select_diverse, source_facets
from biblioteca_agent.academic import named_catalog, NamedFacetVerdict, decode_named


class AcademicTests(unittest.TestCase):
    def test_matching_mode_defaults_to_stable(self):
        import os
        from unittest.mock import patch
        from biblioteca_agent.config import _classification_mode
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_classification_mode(), 'stable')
        with patch.dict(os.environ, {'AGENT_CLASSIFICATION_MODE': 'facets'}):
            self.assertEqual(_classification_mode(), 'facets')

    def test_invalid_matching_mode_is_rejected(self):
        import os
        from unittest.mock import patch
        from biblioteca_agent.config import _classification_mode
        with patch.dict(os.environ, {'AGENT_CLASSIFICATION_MODE': 'typo'}), self.assertRaises(RuntimeError):
            _classification_mode()
    def verdict(self, **changes):
        return FacetVerdict(facetas=[{'texto': 'tema', 'areas': [7], 'relacion': 'directa', 'razon': 'conexión', **changes}])

    def test_scopes_cover_catalog_labels_without_depending_on_ids_or_codes(self):
        self.assertEqual(len(scopes()), 58)
        rows = enrich_areas([{'id': 999, 'nombre': '510 Matemáticas'}, {'id': 43, 'nombre': 'Matemáticas'}])
        self.assertEqual(rows[0]['alcance'], rows[1]['alcance'])
        self.assertEqual(rows[0]['id'], 999)
        self.assertNotIn('alcance', enrich_areas([{'id': 1, 'nombre': 'Especialidad nueva'}])[0])

    def test_relevance_does_not_depend_on_journal_availability(self):
        areas = [{'id': 7, 'nombre': 'Área específica'}]
        programs = [{'id': 99, 'areas': [7]}]
        accepted, matched, rows = resolve_facets('tema', self.verdict(), areas, programs)
        self.assertEqual((accepted, matched), ({7}, {99}))
        self.assertEqual(facet_support([7], rows), ['tema'])

    def test_invented_or_foreign_evidence_is_rejected(self):
        for changes in [{'texto': 'otro tema'}, {'areas': [888]}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                resolve_facets('tema', self.verdict(**changes), [{'id': 7, 'nombre': 'Área'}], [])

    def test_contradictory_decision_abstains_instead_of_system_error(self):
        for changes in [{'areas': [], 'relacion': 'directa'}, {'relacion': 'sin_correspondencia'}]:
            accepted, matched, rows = resolve_facets('tema', self.verdict(**changes), [{'id': 7, 'nombre': 'Área'}], [{'id': 1, 'areas': [7]}])
            self.assertEqual((accepted, matched), (set(), set()))
            self.assertEqual(rows[0]['relacion'], 'sin_correspondencia')
            self.assertTrue(rows[0]['decision_normalizada'])

    def test_named_decisions_are_mapped_to_catalog_ids_without_guessing(self):
        names, context = named_catalog([{'id': 999, 'nombre': '004 Computación'}, {'id': 3, 'nombre': 'Biología'}])
        self.assertTrue(all('id' not in row for row in context))
        verdict = NamedFacetVerdict(facetas=[{'texto': 'tema', 'areas': ['Computación'], 'relacion': 'directa', 'razon': 'conexión'}])
        self.assertEqual(decode_named(verdict, names).facetas[0].areas, [999])
        with self.assertRaises(ValueError):
            decode_named(verdict, {'Otra área': 1})

    def test_duplicate_clean_labels_do_not_overwrite_catalog_entries(self):
        names, _ = named_catalog([{'id': 1, 'nombre': '510 Matemáticas'}, {'id': 2, 'nombre': 'Matemáticas'}])
        self.assertEqual(set(names.values()), {1, 2})

    def test_broad_family_cannot_justify_unrelated_specific_program(self):
        accepted, matched, facets = resolve_facets('tema especializado', self.verdict(texto='tema especializado'),
            [{'id': 7, 'nombre': '500 Ciencias naturales y matemáticas'}], [{'id': 1, 'areas': [7]}])
        self.assertEqual((accepted, matched), (set(), set()))
        self.assertEqual(facets[0]['relacion'], 'sin_correspondencia')

    def test_uncovered_facet_is_retained_not_silently_dropped(self):
        verdict = FacetVerdict(facetas=[{'texto': 'tema', 'areas': [7], 'relacion': 'directa', 'razon': 'conexión'},
            {'texto': 'otro aspecto', 'areas': [], 'relacion': 'sin_correspondencia', 'razon': 'sin correspondencia'}])
        _, _, facets = resolve_facets('tema y otro aspecto', verdict, [{'id': 7, 'nombre': 'Área'}], [])
        self.assertEqual(len(facets), 2)
        self.assertEqual(facets[1]['texto'], 'otro aspecto')

    def test_selection_preserves_distinct_facets_even_with_lower_score(self):
        facets = [{'texto': 'aspecto uno', 'areas': [1]}, {'texto': 'aspecto dos', 'areas': [2]}]
        programs = [{'id': 1, 'areas': [1]}, {'id': 2, 'areas': [1]}, {'id': 3, 'areas': [2]}]
        candidates = [{'id': 1, 'puntuacion': .9}, {'id': 2, 'puntuacion': .8}, {'id': 3, 'puntuacion': .1}]
        self.assertEqual([p['id'] for p in select_diverse(candidates, programs, facets)], [1, 3])
        # Dos áreas justificadas de una misma faceta tampoco son intercambiables.
        self.assertEqual([p['id'] for p in select_diverse(candidates, programs, [{'texto': 'interdisciplinario', 'areas': [1, 2]}])], [1, 3])

    def test_usage_is_request_scoped_and_can_be_unavailable(self):
        from types import SimpleNamespace
        from biblioteca_agent.runtime import AgentRuntime
        from biblioteca_agent.request_context import analysis
        token = analysis.set({})
        try:
            AgentRuntime.record_usage('intencion', SimpleNamespace())
            self.assertIsNone(analysis.get()['inferencias'][0]['tokens_total'])
            AgentRuntime.record_usage('pertinencia', SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)))
            self.assertEqual(analysis.get()['inferencias'][1]['tokens_total'], 15)
        finally:
            analysis.reset(token)

    def test_source_facets_are_literal_bounded_and_duplicates_are_merged(self):
        from biblioteca_agent.text import normalize_text
        topic = 'Un objeto mediante un método y otro aspecto'
        for phrase in source_facets(topic):
            self.assertIn(phrase, normalize_text(topic))
            self.assertLessEqual(len(phrase), 220)
        verdict = FacetVerdict(facetas=[self.verdict().facetas[0], self.verdict().facetas[0]])
        _, _, rows = resolve_facets('tema', verdict, [{'id': 7, 'nombre': 'Área'}], [])
        self.assertEqual(len(rows), 1)
