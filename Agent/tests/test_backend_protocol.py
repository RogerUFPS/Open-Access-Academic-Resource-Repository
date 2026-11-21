import asyncio
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from biblioteca_agent import api, snapshots
from biblioteca_agent.config import PROJECT_ROOT, RESOURCES_DIR
from biblioteca_agent.contracts import QueryRequest
from biblioteca_agent.request_context import catalog_path
from biblioteca_agent.tool_runner import run_script


class BackendProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_drain_counts_running_and_admitted_waiters_and_rejects_new_queries(self):
        started, release = asyncio.Event(), asyncio.Event()
        previous_slots = api.runtime.request_slots
        api.runtime.request_slots = asyncio.Semaphore(1)
        async def respond(_request):
            started.set()
            await release.wait()
            return {"estado": "fuera_de_tema"}
        await api.resume()
        tasks = []
        try:
            with patch.object(api.runtime, "run", side_effect=respond), patch.object(api, "settings", SimpleNamespace(concurrency_wait_seconds=2)):
                tasks.append(asyncio.create_task(api.run_query(QueryRequest(prompt="consulta uno"))))
                await started.wait()
                tasks.append(asyncio.create_task(api.run_query(QueryRequest(prompt="consulta dos"))))
                await asyncio.sleep(0)
                state = await api.drain()
                self.assertEqual(state["inflight"], 2)
                with self.assertRaises(HTTPException) as rejected:
                    await api.run_query(QueryRequest(prompt="consulta nueva"))
                self.assertEqual(rejected.exception.status_code, 503)
                release.set()
                await asyncio.gather(*tasks)
                self.assertEqual((await api.control_status())["inflight"], 0)
        finally:
            release.set()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            api.runtime.request_slots = previous_slots
            await api.resume()

    async def test_catalogs_are_hash_checked_and_isolated_between_concurrent_requests(self):
        root = PROJECT_ROOT / "data"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory, patch.object(snapshots, "ROOT", Path(directory)):
            async def read_catalog(name):
                data = json.loads((RESOURCES_DIR / "catalog_snapshot.example.json").read_text())
                data["programas"][0]["nombre"] = name
                digest = hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                path = snapshots.install(digest, data)
                token = catalog_path.set(path)
                try:
                    result = await asyncio.to_thread(run_script, "get_academic_programs", {})
                    return result["programas"][0]["nombre"]
                finally:
                    catalog_path.reset(token)
            self.assertEqual(await asyncio.gather(read_catalog("Catálogo A"), read_catalog("Catálogo B")), ["Catálogo A", "Catálogo B"])
            with self.assertRaises(ValueError):
                snapshots.install("0" * 64, {"schema_version": 1})

    async def test_missing_snapshot_never_runs_inference(self):
        with patch.object(api.runtime, "run") as run:
            with self.assertRaises(HTTPException) as missing:
                await api.run_query(QueryRequest(prompt="consulta de prueba", catalog_digest="0" * 64))
            self.assertEqual(missing.exception.status_code, 409)
            run.assert_not_called()
