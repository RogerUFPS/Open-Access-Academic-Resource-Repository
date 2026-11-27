"""Regresiones del pipeline completo sin GPU: solo se simula el clasificador."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from biblioteca_agent.config import RESOURCES_DIR
from biblioteca_agent.contracts import QueryRequest
from biblioteca_agent.rag import RagStore, read_examples
from biblioteca_agent.runtime import AgentRuntime, Intent
from biblioteca_agent.relevance import area_evidence


class ClassificationFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_area_evidence_is_dropped_without_losing_intent(self):
        runtime = AgentRuntime()
        intent = Intent(tipo="buscar_literatura", tema="salud mental", idioma="es", areas_implicitas=[7], evidencias_areas={"7": "una frase inventada"})
        create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(finish_reason="tool_calls", message=SimpleNamespace(tool_calls=[SimpleNamespace(function=SimpleNamespace(name="classify_intent", arguments=intent.model_dump_json()))]))]))
        runtime.client_for = lambda _: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        result = await runtime.classify("Investigar salud mental", {"areas": [{"id": 7, "nombre": "Salud"}]})
        self.assertEqual(result.tipo, "buscar_literatura")
        self.assertEqual(result.areas_implicitas, [])

    async def test_education_is_recovered_with_or_without_classification_code(self):
        source = json.loads((RESOURCES_DIR.parent / "tests/fixtures/catalog.json").read_text())
        self.runtime.classify.return_value = Intent(tipo="buscar_literatura", tema="enseñanza de matemáticas en primaria", idioma="es")
        for label in ["510 Matemáticas", "Matemáticas"]:
            source["areas"][0]["nombre"] = label
            # Los catálogos de herramientas deben estar dentro de Agent.
            with tempfile.TemporaryDirectory(dir=RESOURCES_DIR.parent / "data") as folder:
                path = Path(folder) / "education.json"
                path.write_text(json.dumps(source))
                with patch.dict(os.environ, {"AGENT_CATALOG_SNAPSHOT": str(path)}):
                    result = await self.runtime.run(QueryRequest(prompt="Enseñanza de matemáticas en primaria"))
            self.assertEqual(result["estado"], "ok")
            self.assertTrue(result["programas_seleccionados"])

    async def test_broad_area_does_not_fill_secondary_programs(self):
        source = json.loads((RESOURCES_DIR.parent / "tests/fixtures/catalog.json").read_text())
        source["programas"][1]["areas"] = [15, 9]
        source["programas"].extend({"id": n, "nombre": f"Programa {n}", "areas": [15]} for n in range(100, 108))
        self.runtime.classify.return_value.areas_implicitas = [9]
        with tempfile.TemporaryDirectory(dir=RESOURCES_DIR.parent / "data") as folder:
            path = Path(folder) / "broad.json"
            path.write_text(json.dumps(source))
            with patch.dict(os.environ, {"AGENT_CATALOG_SNAPSHOT": str(path)}):
                result = await self.runtime.run(QueryRequest(prompt="Inteligencia artificial para Ingeniería de Sistemas"))
        self.assertEqual(result["estado"], "ok")
        self.assertEqual([p["id"] for p in result["programas_seleccionados"]], [12])

    async def test_general_topic_can_return_honest_exploratory_coverage(self):
        source = json.loads((RESOURCES_DIR.parent / "tests/fixtures/catalog.json").read_text())
        source["areas"][0]["nombre"] = "Educación"
        source["areas"][1]["nombre"] = "Astronomía"
        source["programas"].append({"id": 100, "nombre": "Otro programa", "areas": [7]})
        self.runtime.classify.return_value = Intent(tipo="buscar_literatura", tema="educacion", idioma="es")
        with tempfile.TemporaryDirectory(dir=RESOURCES_DIR.parent / "data") as folder:
            path = Path(folder) / "general.json"
            path.write_text(json.dumps(source))
            with patch.dict(os.environ, {"AGENT_CATALOG_SNAPSHOT": str(path)}):
                result = await self.runtime.run(QueryRequest(prompt="Investigación sobre educación"))
        self.assertEqual(result["estado"], "ok")
        self.assertIn("exploratoria", result["busquedas"][0]["justificacion"])

    async def test_common_articles_are_not_iso_language_requests(self):
        definitions = [{"id": 1, "clave": "idioma", "tipo": "lista", "valores_validos": ["el", "la", "de", "en", "es"]}]
        for prompt in ["salud mental en el personal de enfermería", "prevención en la población", "en el trabajo"]:
            self.assertEqual(self.runtime.extract_filters(prompt, definitions), [])
        self.assertEqual(self.runtime.extract_filters("idioma: el", definitions)[0].valor, ["el"])
        self.assertEqual(self.runtime.extract_filters("artículos en inglés", definitions)[0].valor, ["en"])

    async def test_recent_evidence_remains_success_without_inventing_years(self):
        result = await self.runtime.run(QueryRequest(prompt="Evidencia reciente sobre inteligencia artificial para Ingeniería de Sistemas"))
        self.assertEqual(result["estado"], "ok")
        self.assertIsNone(result["mensaje"])
        self.assertIn("rango de años", result["busquedas"][0]["justificacion"])

    async def test_article_dates_do_not_filter_journal_origin_dates(self):
        result = await self.runtime.run(QueryRequest(prompt="Inteligencia artificial para Ingeniería de Sistemas entre 2025 y 2026"))
        self.assertEqual(result["estado"], "ok")
        self.assertEqual({s["plataforma_id"] for s in result["busquedas"]}, {3, 5})

    async def test_nursing_population_is_preserved(self):
        topic = self.runtime.clean_topic("salud mental en personal de enfermería", [{"nombre_normalizado": "enfermeria"}], [])
        self.assertIn("personal de enfermeria", topic)
        self.assertEqual(self.runtime.clean_topic("salud mental en enfermería", [{"nombre_normalizado": "enfermeria"}], []), "salud mental en enfermeria")

    async def test_document_type_with_multiple_words(self):
        definitions = [{"id": 2, "clave": "tipo_documento", "tipo": "lista", "valores_validos": ["trabajo de grado"]}]
        claims = self.runtime.extract_filters("Busco un trabajo de grado sobre salud", definitions)
        self.assertEqual(claims[0].valor, ["trabajo de grado"])

    async def test_query_builder_preserves_all_concepts(self):
        from biblioteca_agent.search import build_topic_query
        syntax = {"operadores": {"AND": True}}
        topic = "salud mental en personal de enfermeria"
        result = build_topic_query(topic, ["salud mental", "personal de enfermeria"], [{"termino": "salud mental", "relevancia": 1, "origen": "prompt"}], syntax)
        self.assertEqual(result, "salud mental AND personal de enfermeria")
        self.assertEqual(build_topic_query(topic, ["salud mental"], [], syntax), topic)
        self.assertEqual(build_topic_query(topic, ["salud mental", "diabetes"], [], syntax), topic)
        nursing = build_topic_query("efectividad de las intervenciones de salud mental para prevenir el agotamiento profesional en el personal de enfermeria", ["intervenciones de salud mental", "agotamiento profesional", "personal de enfermeria"], [], syntax)
        self.assertIn("efectividad de las intervenciones de salud mental", nursing)
        self.assertIn("prevenir el agotamiento profesional", nursing)
        self.assertEqual(nursing.count(" AND "), 2)

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
        environment = patch.dict(os.environ, {"AGENT_CATALOG_SNAPSHOT": str(RESOURCES_DIR.parent / "tests/fixtures/catalog.json"), "AGENT_BACKEND_SNAPSHOT_URL": ""})
        environment.start()
        self.addCleanup(environment.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.runtime = AgentRuntime()
        self.runtime.classification_mode = 'facets'
        self.runtime.rag = RagStore(Path(self.directory.name) / "rag.sqlite3")
        self.runtime.rag.replace_all(read_examples(RESOURCES_DIR / "rag/approved_examples.json"))
        self.runtime.classify = AsyncMock(return_value=Intent(
            tipo="buscar_literatura", tema="inteligencia artificial", idioma="es", filtros=[]))
        self.runtime.verify_relevance = AsyncMock(side_effect=lambda topic, areas, programs: (set(self.runtime.classify.return_value.areas_implicitas) | set(area_evidence(topic, areas)), {p['id'] for p in programs}))

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
        self.assertEqual(scielo["cadena"], "inteligencia artificial AND la(es)")
        self.assertEqual({f["filtro"] for f in result["filtros_no_aplicados"]}, {"Idioma", "Fecha de publicación"})

    async def test_language_as_research_subject_is_not_a_language_filter(self):
        definitions = json.loads(((RESOURCES_DIR.parent / "tests" / "fixtures" / "catalog.json")).read_text())["filtros"]
        claims = self.runtime.extract_filters("Enseñanza del inglés para educación", definitions)
        self.assertEqual(claims, [])

    async def test_open_dates_are_never_silently_ignored(self):
        for expression in ["desde 2023", "hasta 2024", "antes de 2020", "después de 2021", "en 2022", "since 2023"]:
            with self.subTest(expression=expression):
                result = await self.runtime.run(QueryRequest(prompt="Inteligencia artificial para Ingeniería de Sistemas " + expression))
                self.assertEqual(result["estado"], "ok")
                self.assertEqual({f["plataforma_id"] for f in result["filtros_no_aplicados"] if f["filtro"] == "Fecha de publicación"}, {3, 5})
                self.assertNotIn("py(", str(result["busquedas"]))

    async def test_ambiguous_topic_requests_clarification(self):
        self.runtime.classify.return_value = Intent(tipo="buscar_literatura", tema="redes", idioma="es", aclaracion="¿Redes informáticas, sociales u otras?")
        result = await self.runtime.run(QueryRequest(prompt="Quiero investigar sobre redes"))
        self.assertEqual(result["estado"], "informacion_insuficiente")
        self.assertIn("informáticas", result["mensaje"])
        self.assertIsNone(result["busquedas"][0]["plataforma_id"])

    async def test_bare_networks_is_not_rejected_as_off_topic(self):
        for topic in ["redes", "quiero investigar sobre redes"]:
            self.runtime.classify.return_value = Intent(tipo="fuera_de_tema", tema=topic, idioma="es")
            result = await self.runtime.run(QueryRequest(prompt="Quiero investigar sobre redes, ¿qué plataforma me recomiendas?"))
            self.assertEqual(result["estado"], "informacion_insuficiente")
            self.assertIn("disciplina", result["mensaje"])

    async def test_generic_short_topics_request_scope_without_term_lists(self):
        for term in ['bancos', 'modelos', 'capital', 'redes']:
            self.runtime.classify.return_value = Intent(tipo='buscar_literatura', tema=term, idioma='es')
            result = await self.runtime.run(QueryRequest(prompt='Quiero investigar sobre ' + term))
            self.assertEqual(result['estado'], 'informacion_insuficiente')
            self.assertIn('disciplina', result['mensaje'])

    async def test_remove_language_preserves_theme_even_if_model_invents_one(self):
        self.runtime.classify.return_value = Intent(tipo='buscar_literatura', tema='otra cosa inventada', idioma='es', es_seguimiento=True)
        result = await self.runtime.run(QueryRequest(prompt='Ahora sin restricción de idioma, conserva el mismo tema', previous_prompt='Inteligencia artificial para Ingeniería de Sistemas en español', previous_topic='inteligencia artificial'))
        self.assertEqual(result['estado'], 'ok')
        self.assertTrue(all(s['cadena'] == 'inteligencia artificial' for s in result['busquedas']))

    async def test_new_request_with_temporal_marker_drops_old_program_and_filters(self):
        self.runtime.classify.return_value.es_seguimiento = True
        result = await self.runtime.run(QueryRequest(prompt='Ahora busco inteligencia artificial para Ingeniería de Sistemas', previous_prompt='Educación para Licenciatura en Informática en inglés desde 2023', previous_topic='educacion'))
        self.assertEqual(result['estado'], 'ok')
        self.assertEqual(result['filtros_no_aplicados'], [])
        self.assertEqual([p['id'] for p in result['programas_seleccionados']], [12])

    async def test_inverted_years_are_recoverable(self):
        result = await self.runtime.run(QueryRequest(prompt='Inteligencia artificial para Ingeniería de Sistemas entre 2026 y 2020'))
        self.assertEqual(result['estado'], 'informacion_insuficiente')
        self.assertIn('restricciones', result['mensaje'])

    async def test_catalog_question_returns_counts_without_search_chain(self):
        self.runtime.classify.return_value = Intent(tipo='consultar_catalogo', tema='revistas', idioma='es')
        result = await self.runtime.run(QueryRequest(prompt='¿Cuántas revistas tiene Dialnet (ejemplo) para Ingeniería de Sistemas?'))
        self.assertEqual(result['estado'], 'informacion_catalogo')
        self.assertIn('1 revista', result['mensaje'])
        self.assertEqual(result['busquedas'], [])

    async def test_quantitative_catalog_question_overrides_wrong_model_label(self):
        self.runtime.classify.return_value.tipo = 'buscar_literatura'
        result = await self.runtime.run(QueryRequest(prompt='Dime cuántas revistas tiene Dialnet (ejemplo) para Ingeniería de Sistemas'))
        self.assertEqual(result['estado'], 'informacion_catalogo')
        self.assertIn('1 revista', result['mensaje'])
        self.assertEqual(result['busquedas'], [])

    async def test_semantic_review_can_reject_a_literal_but_irrelevant_area(self):
        self.runtime.classify.return_value = Intent(tipo='buscar_literatura', tema='atmosferas de exoplanetas', idioma='es', areas_implicitas=[7])
        self.runtime.verify_relevance.return_value = (set(), set())
        self.runtime.verify_relevance.side_effect = None
        result = await self.runtime.run(QueryRequest(prompt='Investigar atmósferas de exoplanetas'))
        self.assertEqual(result['estado'], 'informacion_insuficiente')
        self.assertEqual(result['programas_seleccionados'], [])

    async def test_independent_verifier_rejects_foreign_catalog_ids(self):
        create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(finish_reason='tool_calls', message=SimpleNamespace(tool_calls=[SimpleNamespace(function=SimpleNamespace(name='verify_relevance', arguments=json.dumps({'facetas': [{'texto': 'tema', 'areas': ['Área ajena'], 'relacion': 'directa', 'razon': 'relación propuesta'}]})))]))]))
        self.runtime.client_for = lambda _: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with self.assertRaises(ValueError):
            await AgentRuntime.verify_relevance(self.runtime, 'tema', [{'id': 7, 'nombre': 'Área'}], [{'id': 12, 'nombre': 'Programa', 'areas': [7]}])

    async def test_stable_mode_dispatches_to_previous_verifier(self):
        self.runtime.classification_mode = 'stable'
        self.runtime.verify_stable = AsyncMock(return_value=({7}, {12}))
        result = await AgentRuntime.verify_relevance(self.runtime, 'tema', [], [])
        self.assertEqual(result, ({7}, {12}))
        self.runtime.verify_stable.assert_awaited_once_with('tema', [], [])

    async def test_stable_verifier_preserves_catalog_validation(self):
        self.runtime.classification_mode = 'stable'
        create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(finish_reason='tool_calls', message=SimpleNamespace(tool_calls=[SimpleNamespace(function=SimpleNamespace(name='verify_relevance', arguments=json.dumps({'areas': [7], 'programas': [12], 'razon': 'Conexión disciplinar'})))]))]))
        self.runtime.client_for = lambda _: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        args = ('tema', [{'id': 7, 'nombre': 'Área'}], [{'id': 12, 'nombre': 'Programa', 'areas': [7]}])
        self.assertEqual(await AgentRuntime.verify_relevance(self.runtime, *args), ({7}, {12}))
        create.return_value.choices[0].message.tool_calls[0].function.arguments = json.dumps({'areas': [999], 'programas': [12], 'razon': 'Ajena'})
        with self.assertRaises(ValueError):
            await AgentRuntime.verify_relevance(self.runtime, *args)

    async def test_independent_verifier_accepts_only_provided_ids(self):
        create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(finish_reason='tool_calls', message=SimpleNamespace(tool_calls=[SimpleNamespace(function=SimpleNamespace(name='verify_relevance', arguments=json.dumps({'facetas': [{'texto': 'tema', 'areas': ['Área'], 'relacion': 'directa', 'razon': 'conexión temática con objeto y método'}]})))]))]))
        self.runtime.client_for = lambda _: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        accepted = await AgentRuntime.verify_relevance(self.runtime, 'tema', [{'id': 7, 'nombre': 'Área'}], [{'id': 12, 'nombre': 'Programa', 'areas': [7]}])
        self.assertEqual(accepted, ({7}, {12}))
        sent = json.loads(create.call_args.kwargs['messages'][1]['content'])
        self.assertEqual(set(sent), {'tema', 'areas', 'fragmentos_permitidos'})

    async def test_public_recommendation_explains_uncovered_facets(self):
        from biblioteca_agent.request_context import analysis
        self.runtime.classify.return_value = Intent(tipo='buscar_literatura', tema='inteligencia artificial y otro aspecto', idioma='es')
        arguments = {'facetas': [
            {'texto': 'inteligencia artificial', 'areas': ['Inteligencia Artificial'], 'relacion': 'directa', 'razon': 'disciplina pertinente'},
            {'texto': 'otro aspecto', 'areas': [], 'relacion': 'sin_correspondencia', 'razon': 'sin área'}]}
        create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(finish_reason='tool_calls',
            message=SimpleNamespace(tool_calls=[SimpleNamespace(function=SimpleNamespace(name='verify_relevance', arguments=json.dumps(arguments)))]))]))
        self.runtime.client_for = lambda _: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        self.runtime.verify_relevance = AgentRuntime.verify_relevance.__get__(self.runtime)
        token = analysis.set({})
        try:
            result = await self.runtime.run(QueryRequest(prompt='Investigar inteligencia artificial y otro aspecto'))
            self.assertEqual(result['estado'], 'ok')
            self.assertIn('Cobertura temática parcial', result['busquedas'][0]['justificacion'])
            self.assertIn('otro aspecto', result['busquedas'][0]['justificacion'])
            self.assertIn('inteligencia artificial', result['programas_seleccionados'][0]['razon'])
            self.assertEqual(analysis.get()['cobertura_tematica'], 'parcial')
        finally:
            analysis.reset(token)

    async def test_verifier_cannot_replace_required_decisions_with_prose(self):
        from biblioteca_agent.academic import FacetVerdict
        with self.assertRaises(ValueError):
            FacetVerdict(razon='Las áreas son pertinentes, pero no se proporcionan sus ids.')


    async def test_english_connectors_do_not_become_search_concepts(self):
        from biblioteca_agent.search import build_topic_query
        result = build_topic_query("animal welfare and sustainable livestock production", ["animal welfare", "sustainable livestock production"], [], {"operadores": {"AND": True}})
        self.assertEqual(result, "animal welfare AND sustainable livestock production")

    async def test_recognized_program_without_journals_is_preserved(self):
        original = self.runtime.script
        async def script(name, args):
            if name == "get_platforms_related_to_programs":
                return {"plataformas": []}
            return await original(name, args)
        with patch.object(self.runtime, "script", side_effect=script):
            result = await self.runtime.run(QueryRequest(prompt="Inteligencia artificial para Ingeniería de Sistemas"))
        self.assertEqual(result["estado"], "informacion_insuficiente")
        self.assertEqual(result["programas_seleccionados"][0]["id"], 12)
        self.assertNotIn("filtros", result["mensaje"])

    async def test_destination_cleanup_preserves_population_and_subject(self):
        programs = [{"nombre_normalizado": "ingenieria electronica"}]
        topic = self.runtime.clean_topic("sensores de bajo consumo para monitoreo ambiental con internet de las cosas en ingenieria electronica", programs, [])
        self.assertNotIn("ingenieria electronica", topic)
        self.assertIn("sensores de bajo consumo", topic)
        self.assertEqual(self.runtime.clean_topic("plataformas con revistas sobre normas internacionales de informacion financiera", [], []), "normas internacionales de informacion financiera")
        self.assertEqual(self.runtime.clean_topic("investigaciones sobre ergonomia y prevencion de lesiones", [], []), "ergonomia y prevencion de lesiones")
        self.assertEqual(self.runtime.clean_topic("animal welfare and sustainable livestock production", [], []), "animal welfare and sustainable livestock production")

    async def test_new_topic_drops_previous_dates(self):
        result = await self.runtime.run(QueryRequest(prompt="Inteligencia artificial para Ingeniería de Sistemas", previous_prompt="Educación desde 2023 en inglés", previous_topic="educacion"))
        self.assertEqual(result["estado"], "ok")
        self.assertEqual(result["filtros_no_aplicados"], [])

    async def test_open_date_followup_keeps_previous_topic(self):
        self.runtime.classify.return_value.es_seguimiento = True
        result = await self.runtime.run(QueryRequest(prompt="Y desde 2023", previous_prompt="Inteligencia artificial para Ingeniería de Sistemas", previous_topic="inteligencia artificial"))
        self.assertEqual(result["estado"], "ok")
        self.assertTrue(all("inteligencia artificial" in s["cadena"] for s in result["busquedas"]))
        self.assertTrue(result["filtros_no_aplicados"])

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
