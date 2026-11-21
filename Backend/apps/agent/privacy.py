"""Minimización de contenido. No pretende identificar nombres propios arbitrarios."""
import hashlib
import logging
import re


def redact(value):
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if not isinstance(value, str):
        return value
    value = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[correo omitido]", value)
    value = re.sub(r"(?<!\w)(?:\+57[\s.-]*)?3\d{2}[\s.-]*\d{3}[\s.-]*\d{4}(?!\d)", "[teléfono omitido]", value)
    value = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[dirección omitida]", value)
    value = re.sub(r"\b(?i:me llamo|mi nombre es)\s+[\wÁÉÍÓÚáéíóúÑñ]+(?:\s+(?!y\b|para\b|quiero\b)[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚáéíóúÑñ]+){0,3}", "[nombre omitido]", value)
    value = re.sub(r"\b(?i:cédula|cedula|identificación|identificacion)\s*[:#]?\s*[\d. -]{5,20}", "[documento omitido]", value)
    return value


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


class AnonymousChatMiddleware:
    """Antes de SessionMiddleware: el chat público nunca utiliza una sesión de cuenta."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info.startswith("/api/agent/chat/"):
            from auditlog.context import disable_auditlog
            request.COOKIES = {}
            with disable_auditlog():
                response = self.get_response(request)
            response["Cache-Control"] = "private, no-store"
            response["Referrer-Policy"] = "no-referrer"
            return response
        return self.get_response(request)


class AnonymousAccessFilter(logging.Filter):
    def filter(self, record):
        return "/api/agent/chat/" not in record.getMessage()
