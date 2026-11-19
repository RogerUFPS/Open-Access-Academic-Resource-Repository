import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT / "src"))

from biblioteca_agent.catalog import load_snapshot
from biblioteca_agent.rag import RagStore, read_jsonl, validate_documents


def run_tool(name, payload):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    environment["AGENT_CATALOG_SNAPSHOT"] = str(
        ROOT / "resources" / "catalog_snapshot.example.json"
    )
    environment.pop("AGENT_BACKEND_SNAPSHOT_URL", None)
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / f"{name}.py"), "--json", json.dumps(payload)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    if not result.stdout.strip():
        raise AssertionError(f"{name} no emitió JSON. stderr={result.stderr}")
    return result.returncode, json.loads(result.stdout)


class ScriptContractTests(unittest.TestCase):
    def test_normalization_is_canonical(self):
        code, body = run_tool("normalize_text", {"texto": "  Educación, IA  "})
        self.assertEqual(code, 0)
        self.assertEqual(body, {"prompt_normalizado": "educacion ia"})

    def test_catalog_and_relations(self):
        self.assertIn("programas", run_tool("get_academic_programs", {})[1])
        body = run_tool("get_areas_from_program", {"programas": [12]})[1]
        self.assertEqual(body["programas"][0]["programa_id"], 12)

    def test_syntax_does_not_invent_templates(self):
        body = run_tool("get_valid_sintaxis", {"plataformas": [3, 5]})[1]
        by_id = {item["plataforma_id"]: item for item in body["sintaxis"]}
        self.assertEqual(by_id[3]["campos"]["title"]["plantilla"], "ti({})")
        self.assertIsNone(by_id[5]["campos"]["title"]["plantilla"])
        self.assertIsNone(by_id[3]["frase_exacta"])

    def test_platform_filter_ids(self):
        code, body = run_tool(
            "get_platforms_related_to_programs",
            {"programas": [12], "filtros": {"1": ["es"], "3": "2020-2025"}},
        )
        self.assertEqual(code, 0)
        self.assertTrue(body["plataformas"])

    def test_unknown_id_is_error(self):
        code, body = run_tool("get_areas_from_program", {"programas": [9999]})
        self.assertEqual(code, 2)
        self.assertIn("error", body)

    def test_yake_returns_normalized_relevance(self):
        code, body = run_tool("yake_extract_keywords", {
            "prompt_normalizado": "inteligencia artificial aplicada a educacion",
            "texto_unificado": "aprendizaje automatico educacion tecnologia",
            "idioma_texto": "es",
            "umbral_relevancia": 0,
            "excluir_genericas": True,
        })
        self.assertEqual(code, 0)
        self.assertTrue(body["palabras_clave"])
        self.assertTrue(all(0 <= item["relevancia"] <= 1 for item in body["palabras_clave"]))


class RagTests(unittest.TestCase):
    def test_explicit_ingestion_and_search(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RagStore(Path(directory) / "rag.sqlite3")
            store.upsert([{
                "id": "one",
                "prompt": "inteligencia artificial en educación",
                "respuesta": {
                    "tipo": "buscar_literatura",
                    "tema": "inteligencia artificial en educacion",
                    "programas_explicitos": [],
                    "areas_explicitas": [],
                    "areas_implicitas": [],
                    "areas_ambiguas": [],
                    "filtros": {},
                },
                "notas": "revisado",
            }])
            results = store.search("educación e inteligencia artificial")
            self.assertEqual(results[0]["id"], "one")

    def test_approved_examples_are_valid_and_searchable(self):
        documents = read_jsonl(ROOT / "resources" / "rag_examples.approved.jsonl")
        self.assertEqual(len(documents), 12)
        with tempfile.TemporaryDirectory() as directory:
            store = RagStore(Path(directory) / "rag.sqlite3")
            self.assertEqual(store.replace_all(documents), 12)
            self.assertEqual(store.count(), 12)
            self.assertEqual(store.search("bases de datos distribuidas")[0]["id"], "rag-002-sistemas-bases-datos")

    def test_invalid_batch_does_not_replace_existing_documents(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RagStore(Path(directory) / "rag.sqlite3")
            valid = [{
                "id": "existing",
                "prompt": "inteligencia artificial",
                "respuesta": {
                    "tipo": "buscar_literatura",
                    "tema": "inteligencia artificial",
                    "programas_explicitos": [],
                    "areas_explicitas": [],
                    "areas_implicitas": [],
                    "areas_ambiguas": [],
                    "filtros": {},
                },
                "notas": "revisado",
            }]
            store.upsert(valid)
            with self.assertRaises(ValueError):
                store.replace_all([{"id": "bad"}])
            self.assertEqual(store.count(), 1)

    def test_duplicate_ids_are_rejected(self):
        document = read_jsonl(ROOT / "resources" / "rag_examples.approved.jsonl")[0]
        with self.assertRaises(ValueError):
            validate_documents([document, document])


class ResponseContractTests(unittest.TestCase):
    def test_final_response_rejects_generic_justification_shape_errors(self):
        from biblioteca_agent.runtime import AgentRuntime

        valid = {
            "estado": "ok",
            "mensaje": None,
            "programas_seleccionados": [],
            "busquedas": [{
                "plataforma_id": 3,
                "plataforma": "Ejemplo",
                "cadena": "educacion AND tecnologia",
                "justificacion": "Tiene revistas relacionadas y admite AND.",
            }],
            "filtros_no_aplicados": [],
        }
        self.assertEqual(AgentRuntime.parse_final(json.dumps(valid))["estado"], "ok")
        valid["busquedas"][0]["justificacion"] = ""
        with self.assertRaises(ValueError):
            AgentRuntime.parse_final(json.dumps(valid))


class ModelConfigurationTests(unittest.TestCase):
    def test_requests_only_accept_versioned_registry(self):
        from biblioteca_agent.contracts import QueryRequest, model_registry

        self.assertEqual(
            QueryRequest(prompt="buscar sobre educación").model_name,
            "qwen",
        )
        self.assertEqual(
            {model.name for model in model_registry.definitions},
            {"qwen", "glm", "llama"},
        )
        self.assertEqual(
            QueryRequest(
                prompt="buscar sobre educación", model_name="llama3.1:8b"
            ).model_name,
            "llama3.1:8b",
        )
        with self.assertRaises(ValueError):
            QueryRequest(prompt="buscar sobre educación", model_name="modelo:no-configurado")

    def test_registry_never_exposes_endpoint_or_secret_values(self):
        from biblioteca_agent.contracts import model_registry

        with patch.dict(os.environ, {
            "QWEN_VLLM_BASE_URL": "https://private.example/v1",
            "QWEN_VLLM_API_KEY": "secret-value",
        }, clear=False):
            serialized = json.dumps(model_registry.status())
        self.assertNotIn("private.example", serialized)
        self.assertNotIn("secret-value", serialized)


class VllmAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_openai_tool_call_id_is_preserved_in_next_round(self):
        from biblioteca_agent.contracts import QueryRequest
        from biblioteca_agent.runtime import AgentRuntime

        tool_call = SimpleNamespace(
            id="call-rag-1",
            function=SimpleNamespace(
                name="rag_search",
                arguments=json.dumps({"query": "educacion", "limit": 1}),
            ),
        )
        valid_result = {
            "estado": "ok",
            "mensaje": None,
            "programas_seleccionados": [],
            "busquedas": [],
            "filtros_no_aplicados": [],
        }
        create = AsyncMock(side_effect=[
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content="",
                tool_calls=[tool_call],
            ))]),
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content=json.dumps(valid_result),
                tool_calls=[],
            ))]),
        ])
        runtime = AgentRuntime.__new__(AgentRuntime)
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        runtime.client_for = lambda _model: client
        runtime.rag = SimpleNamespace(search=lambda _query, _limit: [{"id": "rag-1"}])
        runtime.runtime_prompt = "Prompt de prueba"

        result = await runtime.run(QueryRequest(prompt="buscar sobre educación"))

        self.assertEqual(result["estado"], "ok")
        self.assertEqual(create.await_args_list[0].kwargs["model"], "biblioteca-qwen3-8b")
        second_messages = create.await_args_list[1].kwargs["messages"]
        tool_messages = [item for item in second_messages if item["role"] == "tool"]
        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(tool_messages[0]["tool_call_id"], "call-rag-1")


class ConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_saturated_replica_returns_retryable_429(self):
        from biblioteca_agent import api
        from fastapi import HTTPException

        previous_slots = api.runtime.request_slots
        api.runtime.request_slots = api.asyncio.Semaphore(1)
        await api.runtime.request_slots.acquire()
        try:
            with patch.object(api, "settings", SimpleNamespace(concurrency_wait_seconds=0.05)):
                with self.assertRaises(HTTPException) as raised:
                    await api.run_query(api.QueryRequest(prompt="buscar sobre educación"))
            self.assertEqual(raised.exception.status_code, 429)
            self.assertEqual(raised.exception.headers["Retry-After"], "1")
        finally:
            api.runtime.request_slots.release()
            api.runtime.request_slots = previous_slots


class CatalogApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_summary_reports_active_source(self):
        from biblioteca_agent.api import catalog_summary

        with patch.dict(os.environ, {
            "AGENT_BACKEND_SNAPSHOT_URL": "",
            "AGENT_CATALOG_SNAPSHOT": str(ROOT / "resources" / "catalog_snapshot.example.json"),
        }, clear=False):
            result = await catalog_summary()
        self.assertEqual(result["fuente"], "archivo_configurado")
        self.assertEqual(result["conteos"]["programas"], 2)
        self.assertTrue(result["plataformas"])


class BackendSnapshotRepositoryTests(unittest.TestCase):
    def test_backend_snapshot_is_downloaded_once_and_shared_from_disk_cache(self):
        payload = (ROOT / "resources" / "catalog_snapshot.example.json").read_bytes()

        class Handler(BaseHTTPRequestHandler):
            calls = 0

            def do_GET(self):
                type(self).calls += 1
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("ETag", '"snapshot-test"')
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, _format, *_args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        data_root = ROOT / "data"
        data_root.mkdir(exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(dir=data_root) as directory:
                cache_path = Path(directory) / "snapshot.json"
                environment = {
                    "AGENT_CATALOG_SNAPSHOT": "",
                    "AGENT_BACKEND_SNAPSHOT_URL": (
                        f"http://127.0.0.1:{server.server_port}/api/agent/v1/snapshot/"
                    ),
                    "AGENT_BACKEND_CACHE_PATH": str(cache_path),
                    "AGENT_BACKEND_CACHE_TTL": "300",
                }
                with patch.dict(os.environ, environment, clear=False):
                    first = load_snapshot()
                    second = load_snapshot()
                self.assertEqual(first, second)
                self.assertEqual(Handler.calls, 1)
                self.assertTrue(cache_path.exists())
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
