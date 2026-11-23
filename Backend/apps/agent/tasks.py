"""Trabajos separados: inferencia no bloquea HTTP ni al controlador de cambios."""
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .client import AgentClient, AgentUnavailable
from .models import AgentState, ChatTurn
from .services import PENDING, error_response, finish_turn, locked_state


def validate_result(payload, model, snapshot):
    from .chat_serializers import AgentResultSerializer
    serializer = AgentResultSerializer(data=payload.get("respuesta"))
    serializer.is_valid(raise_exception=True)
    response = serializer.validated_data
    if payload.get("modelo") != model:
        raise ValueError("Modelo de respuesta incorrecto")
    programs = {p["id"]: p["nombre"] for p in snapshot["programas"]}
    areas = {a["id"]: a["nombre"] for a in snapshot["areas"]}
    platforms = {p["id"]: p["nombre"] for p in snapshot["plataformas"]}
    for p in response["programas_seleccionados"]:
        if programs.get(p["id"]) != p["nombre"]:
            raise ValueError("Programa ajeno al catálogo")
    for p in response["busquedas"]:
        if p["plataforma_id"] is not None and platforms.get(p["plataforma_id"]) != p["plataforma"]:
            raise ValueError("Plataforma ajena al catálogo")
    analysis = payload.get("analisis", {})
    for key, lookup in (("programas_consultados", programs), ("areas_consultadas", areas)):
        for item in analysis.get(key, []):
            if lookup.get(item["id"]) != item["nombre"]:
                raise ValueError("Clasificación ajena al catálogo")
    return response, analysis


@shared_task(name="apps.agent.process_turn")
def process_turn(turn_id):
    with transaction.atomic():
        locked_state()
        turn = ChatTurn.objects.select_for_update().filter(pk=turn_id, status="queued").first()
        if not turn:
            return  # Redelivery de Celery: no repetir una inferencia ya iniciada.
        turn.status = "running"
        turn.started_at = timezone.now()
        turn.save(update_fields=["status", "started_at"])
        previous = ChatTurn.objects.filter(conversation_id=turn.conversation_id,
            sequence__lt=turn.sequence, status="completed").order_by("-sequence").first()
        previous_prompt = (previous.analysis.get("consulta_resuelta") or previous.prompt) if previous else ""
        previous_topic = previous.analysis.get("tema", "") if previous else ""
    try:
        from .views import cached_public_snapshot
        snapshot, etag = cached_public_snapshot()
        with AgentClient(turn.model_name) as client:
            payload = client.query(turn.prompt, snapshot, etag, previous_prompt, previous_topic)
        response, analysis = validate_result(payload, turn.model_name, snapshot)
    except Exception:
        # La excepción de red puede contener headers. No serializarla ni registrarla.
        response, analysis = error_response(), {}
    finish_turn(turn_id, response, analysis)
    state = AgentState.objects.get(pk=1)
    if state.pending_model:
        from .services import enqueue_switch
        enqueue_switch(state.generation)


@shared_task(name="apps.agent.advance_switch")
def advance_switch(generation):
    with transaction.atomic():
        state = locked_state()
        if str(state.generation) != generation or not state.pending_model:
            return
        if ChatTurn.objects.filter(status__in=PENDING).exists():
            # finish_turn notifica al terminar; beat es la recuperación cada
            # 30 s. No crear cadenas de timers por cada evento duplicado.
            return
        # Solo una tarea puede ejecutar efectos remotos de esta generación.
        if state.phase == "switching" and state.updated_at > timezone.now() - timedelta(seconds=2 * settings.AGENT_TIMEOUT_SECONDS + 30):
            return
        state.phase = "switching"
        state.save(update_fields=["phase", "updated_at"])
        source, target, source_drained = state.active_model, state.pending_model, state.source_drained
    try:
        if not source_drained:
            with AgentClient(source) as old:
                drained = old.control("drain")
                if drained.get("inflight", -1) != 0:
                    raise AgentUnavailable("El modelo anterior todavía tiene peticiones en curso.")
            AgentState.objects.filter(pk=1, generation=generation).update(source_drained=True)
        with AgentClient(target) as new:
            new.verify()
            new.control("resume")
        with transaction.atomic():
            state = locked_state()
            if str(state.generation) != generation:
                return
            state.active_model = target
            state.pending_model = ""
            state.phase = "ready"
            state.last_error = ""
            state.save()
    except Exception:
        with transaction.atomic():
            state = locked_state()
            if str(state.generation) == generation:
                state.phase = "error"
                state.last_error = "Cambio pendiente: esperando drenaje o disponibilidad del modelo destino."
                state.save(update_fields=["phase", "last_error", "updated_at"])
        # El reconciliador periódico retoma esta generación sin multiplicar
        # temporizadores en fallos persistentes del proveedor.


@shared_task(name="apps.agent.reconcile")
def reconcile():
    """Repara publicaciones perdidas y peticiones huérfanas sin repetir inferencia."""
    from .services import enqueue_switch, enqueue_turn
    for turn_id in ChatTurn.objects.filter(status="queued", created_at__lt=timezone.now() - timedelta(seconds=15)).values_list("id", flat=True)[:100]:
        enqueue_turn(turn_id)
    expired = list(ChatTurn.objects.filter(status="running",
        started_at__lt=timezone.now() - timedelta(seconds=settings.AGENT_TIMEOUT_SECONDS + 120))[:100])
    for model in {turn.model_name for turn in expired}:
        try:
            with AgentClient(model) as client:
                idle = client.control().get("inflight", -1) == 0
        except AgentUnavailable:
            idle = False
        if idle:
            for turn in expired:
                if turn.model_name == model:
                    finish_turn(turn.pk, error_response())
    state = AgentState.objects.filter(pk=1).first()
    if state and state.pending_model:
        enqueue_switch(state.generation)
