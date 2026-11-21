"""Cliente privado. Nunca reenvía cookies, IP ni credenciales del visitante."""
import json
import time
from urllib.parse import urlparse

import httpx
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder


class AgentUnavailable(Exception):
    pass


def configured_models():
    def available(name):
        url = settings.AGENT_ENDPOINTS.get(name, "")
        parsed = urlparse(url)
        return bool(parsed.scheme in {"http", "https"} and parsed.hostname
            and (not parsed.hostname.endswith(".modal.direct") or settings.AGENT_MODAL_KEY and settings.AGENT_MODAL_SECRET))
    return {name: available(name) for name in ("qwen", "glm", "llama")}


class AgentClient:
    def __init__(self, name):
        url = settings.AGENT_ENDPOINTS.get(name, "").rstrip("/")
        if not url:
            raise AgentUnavailable("El modelo no tiene un endpoint configurado.")
        headers = {"Connection": "close"}
        if settings.AGENT_SERVICE_API_KEY:
            headers["X-API-Key"] = settings.AGENT_SERVICE_API_KEY
        if settings.AGENT_MODAL_KEY and settings.AGENT_MODAL_SECRET:
            headers.update({"Modal-Key": settings.AGENT_MODAL_KEY, "Modal-Secret": settings.AGENT_MODAL_SECRET})
        self.name = name
        self.deadline = time.monotonic() + settings.AGENT_TIMEOUT_SECONDS
        self.http = httpx.Client(base_url=url, headers=headers, follow_redirects=False,
            timeout=httpx.Timeout(settings.AGENT_TIMEOUT_SECONDS, connect=15), trust_env=False)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.http.close()

    def call(self, method, path, **kwargs):
        # Solo repetir operaciones idempotentes, nunca POST /v1/query: una
        # desconexión allí no permite saber si ya se ejecutó la inferencia.
        retry_safe = method == "GET" or path == "/v1/catalog/snapshots"
        delay = 2
        while True:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise AgentUnavailable("Se agotó el tiempo de espera del agente.")
            try:
                response = self.http.request(method, path,
                    timeout=httpx.Timeout(remaining, connect=min(15, remaining)), **kwargs)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                transient = isinstance(exc, httpx.TransportError) or (
                    isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {408, 425, 429, 502, 503, 504})
                if retry_safe and transient and self.deadline - time.monotonic() > delay:
                    time.sleep(delay)
                    delay = min(delay * 2, 10)
                    continue
                # No registrar URL, headers, cuerpo ni credenciales.
                raise AgentUnavailable("El servicio del modelo no está disponible o devolvió datos inválidos.") from exc

    def sync_catalog(self, snapshot, etag):
        digest = etag.strip('"')
        status = self.call("GET", f"/v1/catalog/snapshots/{digest}")
        if not status.get("available"):
            payload = json.loads(json.dumps(snapshot, cls=DjangoJSONEncoder))
            self.call("POST", "/v1/catalog/snapshots", json={"digest": digest, "snapshot": payload})
        return digest

    def query(self, prompt, snapshot, etag, previous_prompt="", previous_topic=""):
        digest = self.sync_catalog(snapshot, etag)
        return self.call("POST", "/v1/query", json={"prompt": prompt, "model_name": self.name,
            "catalog_digest": digest, "previous_prompt": previous_prompt,
            "previous_topic": previous_topic, "return_analysis": True})

    def control(self, action="status"):
        return self.call("GET" if action == "status" else "POST", f"/v1/control/{action}")

    def verify(self):
        status = self.call("GET", "/v1/models")
        if status.get("modelo_predeterminado") != self.name:
            raise AgentUnavailable("El endpoint sirve un modelo distinto al solicitado.")
