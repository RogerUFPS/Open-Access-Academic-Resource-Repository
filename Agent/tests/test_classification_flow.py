"""Regresiones del pipeline completo sin GPU: solo se simula el clasificador."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from biblioteca_agent.config import RESOURCES_DIR
from biblioteca_agent.contracts import QueryRequest
from biblioteca_agent.rag import RagStore, read_examples
from biblioteca_agent.runtime import AgentRuntime, Intent


class ClassificationFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_autonomous_prompt_does_not_inherit_previous_language(self):
        self.runtime.classify.return_value.es_seguimiento = True
        result = await self.runtime.run(QueryRequest(
            prompt="Inteligencia artificial para Ingeniería de Sistemas",
            previous_prompt="Educación en inglés", previous_topic="educacion"))
        self.assertEqual(result["estado"], "ok")
        self.assertTrue(all(s["cadena"] == "inteligencia artificial" for s in result["busquedas"]))

    async def test_classifier_cannot_select_entire_catalog_as_implicit_areas(self):
        with self.assertRaises(ValueError):
            Intent(tipo="buscar_literatura", tema="IA", idioma="es", areas_implicitas=list(range(1, 59)))

    async def test_filter_only_followup_cannot_replace_topic_with_rag_example(self):
        with patch.object(self.runtime, "classify", return_value=Intent(
            tipo="buscar_literatura", tema="métodos de aprendizaje para educación",
            idioma="es", es_seguimiento=False)):
            result = await self.runtime.run(QueryRequest(prompt="Y en inglés",
                previous_prompt="Inteligencia artificial para Ingeniería de Sistemas",
                previous_topic="inteligencia artificial"))
        self.assertEqual(result["estado"], "ok")
        self.assertTrue(all("inteligencia artificial" in search["cadena"] for search in result["busquedas"]))
        self.assertNotIn("aprendizaje", str(result["busquedas"]))

    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.runtime = AgentRuntime()
        self.runtime.rag = RagStore(Path(self.directory.name) / "rag.sqlite3")
        self.runtime.rag.replace_all(read_examples(RESOURCES_DIR / "rag/approved_examples.json"))
        self.runtime.classify = AsyncMock(return_value=Intent(
            tipo="buscar_literatura", tema="inteligencia artificial", idioma="es", filtros=[]))

    async def asyncTearDown(self):
        self.directory.cleanup()

    async def test_original_regression_has_grounded_programs_platforms_and_no_filters(self):
        result = await self.runtime.run(QueryRequest(prompt="Inteligencia artificial para Ingeniería de Sistemas"))
        self.assertEqual(result["estado"], "ok")
        self.assertEqual(result["programas_seleccionados"][0]["id"], 12)
        self.assertEqual(result["programas_seleccionados"][0]["puntuacion"], 1)
        self.assertEqual({s["plataforma_id"] for s in result["busquedas"]}, {3, 5})
        self.assertTrue(all(s["cadena"] == "inteligencia artificial" for s in result["busquedas"]))
        self.assertEqual(result["filtros_no_aplicados"], [])
        context = self.runtime.classify.await_args.args[1]
        self.assertEqual(context["rag"][0]["id"], "rag-006-ia-sistemas")
        self.assertTrue(context["programas"] and context["areas"] and context["filtros"])

    async def test_off_topic_is_classified_only_after_catalog_and_rag(self):
        self.runtime.classify.return_value = Intent(tipo="fuera_de_tema", tema="clima", idioma="es", filtros=[])
        result = await self.runtime.run(QueryRequest(prompt="Qué clima hará mañana"))
        self.assertEqual(result["estado"], "fuera_de_tema")
        self.assertEqual(result["busquedas"], [])
        self.assertIn("programas", self.runtime.classify.await_args.args[1])

    async def test_unknown_academic_area_returns_generic_not_off_topic(self):
        self.runtime.classify.return_value = Intent(tipo="buscar_literatura", tema="geologia lunar", idioma="es", filtros=[])
        result = await self.runtime.run(QueryRequest(prompt="Artículos sobre geología lunar"))
        self.assertEqual(result["estado"], "informacion_insuficiente")
        self.assertIsNone(result["busquedas"][0]["plataforma_id"])

    async def test_implicit_area_uses_valid_catalog_relations(self):
        self.runtime.classify.return_value = Intent(tipo="buscar_literatura", tema="aprendizaje automatico",
            idioma="es", filtros=[], areas_implicitas=[7])
        result = await self.runtime.run(QueryRequest(prompt="Artículos sobre aprendizaje automático"))
        self.assertEqual(result["estado"], "ok")
        self.assertEqual({p["id"] for p in result["programas_seleccionados"]}, {12, 31})

    async def test_platform_coverage_deduplicates_journals_across_programs(self):
        from biblioteca_agent.tool_runner import run_script
        result = run_script("get_platforms_related_to_programs", {"programas": [12, 31], "filtros": {}})
        scielo = next(p for p in result["plataformas"] if p["plataforma_id"] == 3)
        self.assertEqual(scielo["cantidad_revistas_total"], 2)
        self.assertEqual(sum(p["cantidad_revistas"] for p in scielo["programas"]), 3)

    async def test_explicit_filters_are_applied_only_where_supported(self):
        self.runtime.classify.return_value = Intent(tipo="buscar_literatura", tema="inteligencia artificial", idioma="es",
            filtros=[{"id": 1, "valor": ["es"], "evidencia": "en español"}])
        result = await self.runtime.run(QueryRequest(prompt="Inteligencia artificial para Ingeniería de Sistemas en español"))
        self.assertEqual(result["estado"], "ok")
        chains = {s["plataforma_id"]: s["cadena"] for s in result["busquedas"]}
        self.assertEqual(chains[3], "inteligencia artificial AND la(es)")
        self.assertEqual(chains[5], "inteligencia artificial")
        self.assertEqual([f["plataforma_id"] for f in result["filtros_no_aplicados"]], [5])

    async def test_fabricated_filter_evidence_cannot_enter_search(self):
        self.runtime.classify.return_value = Intent(tipo="buscar_literatura", tema="inteligencia artificial", idioma="es",
            filtros=[{"id": 1, "valor": ["es"], "evidencia": "inteligencia artificial"}])
        result = await self.runtime.run(QueryRequest(prompt="inteligencia artificial"))
        self.assertEqual(result["estado"], "ok")
        self.assertTrue(all(s["cadena"] == "inteligencia artificial" for s in result["busquedas"]))
        self.assertEqual(result["filtros_no_aplicados"], [])

    async def test_spanish_and_year_range_come_from_prompt_not_model(self):
        self.runtime.classify.return_value.tema = "inteligencia artificial para ingeniería de sistemas en español entre 2020 y 2025"
        result = await self.runtime.run(QueryRequest(prompt="Inteligencia artificial para Ingeniería de Sistemas en español entre 2020 y 2025"))
        self.assertEqual(result["estado"], "ok")
        scielo = next(s for s in result["busquedas"] if s["plataforma_id"] == 3)
        self.assertEqual(scielo["cadena"], "inteligencia artificial AND la(es) AND py(2020-2025)")
        self.assertEqual({f["filtro"] for f in result["filtros_no_aplicados"]}, {"Idioma", "Fecha de publicación"})

    async def test_language_as_research_subject_is_not_a_language_filter(self):
        definitions = json.loads(((RESOURCES_DIR.parent / "tests" / "fixtures" / "catalog.json")).read_text())["filtros"]
        claims = self.runtime.extract_filters("Enseñanza del inglés para educación", definitions)
        self.assertEqual(claims, [])

    async def test_language_list_and_year_range_are_grounded(self):
        definitions = json.loads(((RESOURCES_DIR.parent / "tests" / "fixtures" / "catalog.json")).read_text())["filtros"]
        claims = self.runtime.extract_filters("Artículos en español e inglés entre 2020 y 2025", definitions)
        intent = Intent(tipo="buscar_literatura", tema="educacion", idioma="es", filtros=claims)
        self.assertEqual(self.runtime.valid_filters(intent, "Artículos en español e inglés entre 2020 y 2025", definitions),
            {"1": ["es", "en"], "2": ["articulo"], "3": "2020-2025"})

    async def test_backend_material_names_and_null_publication_dates(self):
        from biblioteca_agent.catalog import journal_matches
        definitions = [{"id": 2, "clave": "tipo_documento", "tipo": "lista", "valores_validos": ["articulo de revista"]}]
        claims = self.runtime.extract_filters("Artículos sobre sistemas", definitions)
        self.assertEqual(claims[0].valor, ["articulo de revista"])
        years = [{"id": 3, "clave": "fecha_publicacion", "tipo": "rango_anios"}]
        self.assertFalse(journal_matches({"fecha_publicacion": None}, {"3": "2020-2025"}, years))

    async def test_followup_retains_explicit_context_and_overrides_requested_language(self):
        self.runtime.classify.return_value.es_seguimiento = True
        result = await self.runtime.run(QueryRequest(prompt="Y en inglés", previous_prompt="Inteligencia artificial para Ingeniería de Sistemas en español"))
        self.assertEqual(result["estado"], "ok")
        self.assertEqual(result["programas_seleccionados"][0]["id"], 12)
        self.assertTrue(any(s["cadena"] == "inteligencia artificial AND la(en)" for s in result["busquedas"]))

    async def test_broken_script_retries_once_and_returns_controlled_error(self):
        with patch("biblioteca_agent.runtime.run_script", return_value={"error": "unavailable"}) as runner:
            result = await self.runtime.run(QueryRequest(prompt="inteligencia artificial"))
        self.assertEqual(result["estado"], "error_sistema")
        self.assertEqual(runner.call_count, 2)

    async def test_free_form_final_cannot_bypass_classifier_contract(self):
        runtime = AgentRuntime()
        create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(tool_calls=[], content=json.dumps({"estado": "fuera_de_tema"})))]))
        runtime.client_for = lambda _: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with self.assertRaises(ValueError):
            await runtime.classify("inteligencia artificial", {"filtros": []})
        self.assertEqual(create.await_count, 2)

    async def test_truncated_classifier_response_is_not_accepted(self):
        runtime = AgentRuntime()
        create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(finish_reason="length")]))
        runtime.client_for = lambda _: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with self.assertRaises(ValueError):
            await runtime.classify("inteligencia artificial", {"filtros": []})
        self.assertEqual(create.await_count, 2)
