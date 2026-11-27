import unittest

from biblioteca_agent.text import area_label
from biblioteca_agent.relevance import area_evidence, graph_specificity
from biblioteca_agent.search import build_topic_query


class RelevanceTests(unittest.TestCase):
    def test_only_classification_prefix_is_removed(self):
        for raw, expected in [("610.73 Enfermería", "Enfermería"), ("004 Ciencia de la computación", "Ciencia de la computación"), ("Enfermería", "Enfermería"), ("Salud 4.0", "Salud 4.0"), ("2024 tendencias", "2024 tendencias"), ("3D y manufactura", "3D y manufactura"), ("510 - Matemáticas", "Matemáticas")]:
            self.assertEqual(area_label(raw), expected)

    def test_coded_and_uncoded_labels_recover_same_evidence(self):
        query = "estrategias para la enseñanza de matemáticas en primaria"
        for name in ["510 Matemáticas", "Matemáticas"]:
            self.assertIn(271, area_evidence(query, [{"id": 271, "nombre": name}]))

    def test_generic_area_is_less_specific_without_using_its_id(self):
        programs = [{"areas": [111, n]} for n in range(10, 20)]
        specificity, broad = graph_specificity(programs)
        self.assertIn(111, broad)
        self.assertLess(specificity[111], specificity[10])

    def test_partial_label_does_not_change_research_domain(self):
        self.assertEqual(area_evidence("protección de datos personales", [{"id": 25, "nombre": "006.312 Minería de datos"}]), {})
        areas = [{"id": 1, "nombre": "Educación preescolar"}, {"id": 2, "nombre": "Estadística (matemáticas estadísticas)"}]
        self.assertEqual(area_evidence("enseñanza de matemáticas en educación primaria", areas), {})

    def test_destination_does_not_discard_valid_concepts(self):
        result = build_topic_query("deteccion de intrusiones mediante aprendizaje automatico", ["detección de intrusiones", "aprendizaje automático", "Ingeniería de Sistemas"], [], {"operadores": {"AND": True}}, ["Ingeniería de Sistemas"])
        self.assertIn(" AND ", result)
        self.assertNotIn("ingenieria", result)

    def test_contained_concepts_are_not_duplicated(self):
        result = build_topic_query("proteccion de datos personales y derecho a la privacidad", ["protección de datos personales", "derecho a la privacidad", "derecho"], [], {"operadores": {"AND": True}})
        self.assertEqual(result.count("derecho"), 1)

    def test_invented_variant_does_not_discard_valid_groups(self):
        result = build_topic_query("estrategias pedagogicas para la ensenanza de matematicas en educacion primaria", ["estrategias pedagógicas", "enseñanza de matemáticas", "educación primaria", "estrategias educativas"], [], {"operadores": {"AND": True}})
        self.assertEqual(result.count(" AND "), 2)
        self.assertNotIn("educativas", result)
