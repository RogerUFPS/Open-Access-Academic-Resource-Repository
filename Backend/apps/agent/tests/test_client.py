from unittest.mock import patch

import httpx
from django.test import SimpleTestCase, override_settings

from apps.agent.client import AgentClient, AgentUnavailable


@override_settings(AGENT_ENDPOINTS={"qwen": "http://qwen"}, AGENT_TIMEOUT_SECONDS=60)
class AgentClientTests(SimpleTestCase):
    def test_cold_start_retries_only_safe_preparation(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(503 if len(calls) == 1 else 200, json={"available": True})
        with AgentClient("qwen") as client:
            client.http.close()
            client.http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://qwen")
            with patch("apps.agent.client.time.sleep") as sleep:
                self.assertTrue(client.call("GET", "/v1/catalog/snapshots/example")["available"])
                sleep.assert_called_once_with(2)
        self.assertEqual(len(calls), 2)

    def test_unknown_query_outcome_never_repeats_inference(self):
        calls = []
        def handler(request):
            calls.append(request)
            raise httpx.ReadError("Respuesta perdida", request=request)
        with AgentClient("qwen") as client:
            client.http.close()
            client.http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://qwen")
            with patch("apps.agent.client.time.sleep") as sleep:
                with self.assertRaises(AgentUnavailable):
                    client.call("POST", "/v1/query", json={"prompt": "IA"})
                sleep.assert_not_called()
        self.assertEqual(len(calls), 1)
