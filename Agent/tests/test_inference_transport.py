"""Contrato real SDK/HTTP: solicitudes sucesivas sin reutilizar sockets cerrados."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from biblioteca_agent.runtime import AgentRuntime


class InferenceTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_successive_classifications_close_internal_connections(self):
        connections = []

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                connections.append(self.headers.get("Connection"))
                assert body["tool_choice"]["function"]["name"] == "classify_intent"
                assert "filtros" not in body["tools"][0]["function"]["parameters"]["properties"]
                response = json.dumps({"id": "chat-test", "object": "chat.completion", "created": 1,
                    "model": body["model"], "choices": [{"index": 0, "finish_reason": "tool_calls",
                    "message": {"role": "assistant", "content": None, "tool_calls": [{
                        "id": "call-test", "type": "function", "function": {"name": "classify_intent",
                        "arguments": json.dumps({"tipo": "buscar_literatura", "tema": "inteligencia artificial",
                            "idioma": "es", "areas_implicitas": [], "areas_ambiguas": []})}}]}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(response)
                self.close_connection = True

            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        runtime = AgentRuntime()
        try:
            with patch("biblioteca_agent.model.ModelDefinition.endpoint", return_value=(
                f"http://127.0.0.1:{server.server_port}/v1", "test-only")):
                for _ in range(3):
                    intent = await runtime.classify("inteligencia artificial", {"filtros": [], "areas": []})
                    self.assertEqual(intent.tipo, "buscar_literatura")
            self.assertEqual(connections, ["close"] * 3)
        finally:
            await runtime.stop()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
