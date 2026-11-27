import uuid
from contextlib import contextmanager
from unittest.mock import Mock, patch

from django.db.models import ForeignKey
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.account.models import User
from apps.agent.models import AgentState, ChatTurn, Conversation, QueryTopic
from apps.agent.services import finish_turn, request_switch
from apps.agent.tasks import advance_switch, process_turn


GOOD = {"estado": "ok", "mensaje": None, "programas_seleccionados": [
    {"id": 12, "nombre": "Sistemas", "puntuacion": 1, "razon": "Mención explícita y área IA."}],
    "busquedas": [{"plataforma_id": 3, "plataforma": "Plataforma", "cadena": "inteligencia artificial",
        "justificacion": "Dos revistas del programa."}], "filtros_no_aplicados": []}
SNAPSHOT = {"programas": [{"id": 12, "nombre": "Sistemas"}], "areas": [{"id": 7, "nombre": "IA"}],
    "plataformas": [{"id": 3, "nombre": "Plataforma"}]}


@override_settings(AGENT_ENDPOINTS={"qwen": "http://qwen", "glm": "http://glm", "llama": "http://llama"})
class AnonymousChatTests(APITestCase):
    def setUp(self):
        self.publisher = patch("apps.agent.services.enqueue_turn").start()
        self.switch_publisher = patch("apps.agent.services.enqueue_switch").start()
        self.addCleanup(patch.stopall)
        created = self.client.post("/api/agent/chat/conversations/", {}, format="json")
        self.assertEqual(created.status_code, 201)
        self.chat_id, self.token = created.data["id"], created.data["access_token"]
        self.url = f"/api/agent/chat/conversations/{self.chat_id}/messages/"
        self.admin = User.objects.create_user(email="chat-admin@example.com", permissions={"agent": {
            "models": {"view": True, "update": True}, "conversations": {"view": True}, "analytics": {"view": True}}})

    def submit(self, text="Inteligencia artificial para Sistemas", message_id=None):
        return self.client.post(self.url, {"prompt": text, "client_message_id": str(message_id or uuid.uuid4())},
            format="json", HTTP_X_CHAT_TOKEN=self.token)

    def test_public_access_and_capability_protect_history(self):
        response = self.submit()
        self.assertEqual(response.status_code, 202)
        self.assertNotIn("model_name", response.data)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.get(self.url, HTTP_X_CHAT_TOKEN="wrong").status_code, 404)
        history = self.client.get(self.url, HTTP_X_CHAT_TOKEN=self.token)
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data["total_items"], 1)
        self.assertEqual(history["Cache-Control"], "private, no-store")
        self.assertNotIn("Set-Cookie", history)

    def test_catalog_information_is_valid_and_not_an_unclear_answer(self):
        from apps.agent.chat_serializers import AgentResultSerializer
        result = {'estado': 'informacion_catalogo', 'mensaje': 'Plataforma: 0 revistas asociadas.',
            'programas_seleccionados': [], 'busquedas': [], 'filtros_no_aplicados': []}
        serializer = AgentResultSerializer(data=result)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        submitted = self.submit()
        finish_turn(submitted.data['id'], result)
        self.assertFalse(ChatTurn.objects.get(pk=submitted.data['id']).unclear)

    def test_no_user_relation_and_redaction_even_with_logged_in_account(self):
        self.client.force_login(self.admin)
        self.client.credentials(HTTP_X_FORWARDED_FOR="198.51.100.42", HTTP_USER_AGENT="private-browser")
        self.assertEqual(self.submit("Buscar IA; mi correo es person@example.com y celular 3001234567").status_code, 202)
        turn = ChatTurn.objects.get()
        self.assertNotIn("person@example.com", turn.prompt)
        self.assertNotIn("3001234567", turn.prompt)
        for model in (Conversation, ChatTurn, QueryTopic):
            for field in model._meta.fields:
                if isinstance(field, ForeignKey):
                    self.assertIsNot(field.related_model, User)
        stored = str(list(Conversation.objects.values())) + str(list(ChatTurn.objects.values()))
        self.assertNotIn("198.51.100.42", stored)
        self.assertNotIn("private-browser", stored)
        self.assertNotEqual(Conversation.objects.get().access_digest, self.token)

    def test_unknown_identity_fields_rejected(self):
        response = self.client.post(self.url, {"prompt": "hola IA", "client_message_id": str(uuid.uuid4()), "user_id": 5},
            format="json", HTTP_X_CHAT_TOKEN=self.token)
        self.assertEqual(response.status_code, 400)

    def test_idempotency_and_conversation_order(self):
        key = uuid.uuid4()
        first, repeated = self.submit(message_id=key), self.submit(message_id=key)
        self.assertEqual(first.data["id"], repeated.data["id"])
        self.assertEqual(ChatTurn.objects.count(), 1)
        self.assertEqual(self.submit().status_code, 409)
        finish_turn(first.data["id"], GOOD)
        self.assertEqual(self.submit(message_id=key).status_code, 200)
        self.assertEqual(self.submit().status_code, 202)
        self.assertEqual(list(ChatTurn.objects.values_list("sequence", flat=True)), [1, 2])

    def test_permissions_are_required_for_every_admin_endpoint(self):
        for url in ("/api/agent/models/", "/api/agent/conversations/", "/api/agent/analytics/topics/", "/api/agent/analytics/queries/"):
            self.assertIn(self.client.get(url).status_code, (401, 403))
        ordinary = User.objects.create_user(email="chat-reader@example.com", permissions={"agent": {"models": {"view": True}}})
        self.client.force_authenticate(ordinary)
        self.assertEqual(self.client.get("/api/agent/models/").status_code, 200)
        self.assertEqual(self.client.post("/api/agent/models/switch/", {"model": "glm"}).status_code, 403)
        self.assertEqual(self.client.get("/api/agent/conversations/").status_code, 403)

    def test_unclear_flag_survives_later_clear_answers_and_pagination(self):
        failed = self.submit()
        unclear = {"estado": "informacion_insuficiente", "mensaje": "Falta cobertura.",
            "programas_seleccionados": [], "busquedas": [], "filtros_no_aplicados": []}
        finish_turn(failed.data["id"], unclear)
        for _ in range(12):
            clear = self.submit()
            finish_turn(clear.data["id"], GOOD)
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/agent/conversations/?unclear=true")
        self.assertEqual(response.data["total_items"], 1)
        detail = self.client.get(f"/api/agent/conversations/{self.chat_id}/?page_size=5")
        self.assertEqual(detail.data["total_items"], 13)
        self.assertTrue(detail.data["results"][0]["unclear"])

    def test_topics_count_queries_not_recommendations_and_no_duplicate_retry(self):
        turn = self.submit()
        analysis = {"programas_consultados": [{"id": 12, "nombre": "Sistemas"}],
            "areas_consultadas": [{"id": 7, "nombre": "IA"}, {"id": 7, "nombre": "IA"}]}
        finish_turn(turn.data["id"], GOOD, analysis)
        finish_turn(turn.data["id"], GOOD, analysis)
        self.assertEqual(QueryTopic.objects.count(), 2)
        self.client.force_authenticate(self.admin)
        rank = self.client.get("/api/agent/analytics/topics/?kind=area")
        self.assertEqual(rank.data["results"][0]["queries"], 1)
        self.assertEqual(rank.data["results"][0]["tier"], 1)

    def test_drain_waits_for_queued_and_running_and_blocks_new_requests(self):
        turn = self.submit()
        state = request_switch("glm")
        generation = str(state.generation)
        with patch("apps.agent.tasks.AgentClient") as client, patch.object(advance_switch, "apply_async"):
            advance_switch.run(generation)
            client.assert_not_called()
            self.assertEqual(self.submit().status_code, 503)
            finish_turn(turn.data["id"], GOOD)
            old, new = Mock(), Mock()
            old.control.return_value = {"inflight": 1}
            client.return_value.__enter__.return_value = old
            advance_switch.run(generation)
            self.assertEqual(AgentState.objects.get().active_model, "qwen")
            old.control.return_value = {"inflight": 0}
            client.side_effect = [Mock(__enter__=Mock(return_value=old), __exit__=Mock()), Mock(__enter__=Mock(return_value=new), __exit__=Mock())]
            advance_switch.run(generation)
            self.assertEqual(AgentState.objects.get().active_model, "glm")
            self.assertEqual(AgentState.objects.get().pending_model, "")
            new.verify.assert_called_once()
            new.control.assert_called_once_with("resume")

    def test_inference_task_uses_backend_catalog_and_is_not_repeated(self):
        turn = self.submit()
        payload = {"respuesta": GOOD, "modelo": "qwen", "analisis": {"programas_consultados": [{"id": 12, "nombre": "Sistemas"}], "areas_consultadas": [{"id": 7, "nombre": "IA"}]}}
        with patch("apps.agent.views.cached_public_snapshot", return_value=(SNAPSHOT, '"etag"')):
            with patch("apps.agent.tasks.AgentClient") as client:
                client.return_value.__enter__.return_value.query.return_value = payload
                process_turn.run(str(turn.data["id"]))
                process_turn.run(str(turn.data["id"]))
                self.assertEqual(client.return_value.__enter__.return_value.query.call_count, 1)
        self.assertEqual(ChatTurn.objects.get().status, "completed")
        self.assertEqual(QueryTopic.objects.count(), 2)

    def test_failed_transport_is_persisted_and_flagged(self):
        turn = self.submit()
        with patch("apps.agent.views.cached_public_snapshot", side_effect=RuntimeError("offline")):
            process_turn.run(str(turn.data["id"]))
        self.assertEqual(ChatTurn.objects.get().response["estado"], "error_sistema")
        self.assertTrue(Conversation.objects.get().has_unclear)
