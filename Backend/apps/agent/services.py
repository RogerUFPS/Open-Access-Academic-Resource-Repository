import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import AgentState, ChatTurn, Conversation, QueryTopic
from .privacy import redact


PENDING = ("queued", "running")


def locked_state():
    AgentState.objects.get_or_create(pk=1, defaults={"active_model": settings.AGENT_DEFAULT_MODEL})
    return AgentState.objects.select_for_update().get(pk=1)


def error_response():
    return {"estado": "error_sistema", "mensaje": "No fue posible completar la consulta al agente.",
        "programas_seleccionados": [], "busquedas": [], "filtros_no_aplicados": []}


def finish_turn(turn_id, response, analysis=None):
    with transaction.atomic():
        locked_state()
        turn = ChatTurn.objects.select_related("conversation").get(pk=turn_id)
        conversation = Conversation.objects.select_for_update().get(pk=turn.conversation_id)
        turn = ChatTurn.objects.select_for_update().get(pk=turn_id)
        if turn.status not in PENDING:
            return
        turn.response = redact(response)
        turn.analysis = redact(analysis or {})
        turn.unclear = response["estado"] not in {"ok", "informacion_catalogo"} or bool(response.get("filtros_no_aplicados"))
        turn.status = "failed" if response["estado"] == "error_sistema" else "completed"
        turn.finished_at = timezone.now()
        turn.save(update_fields=["response", "analysis", "unclear", "status", "finished_at"])
        conversation.updated_at = turn.finished_at
        conversation.has_unclear = conversation.has_unclear or turn.unclear
        conversation.save(update_fields=["updated_at", "has_unclear"])
        for key, kind in (("programas_consultados", "program"), ("areas_consultadas", "area")):
            QueryTopic.objects.bulk_create([
                QueryTopic(turn=turn, kind=kind, catalog_id=item["id"], name=item["nombre"])
                for item in {item["id"]: item for item in turn.analysis.get(key, [])}.values()
            ], ignore_conflicts=True)


def enqueue_turn(turn_id):
    from .tasks import process_turn
    try:
        process_turn.delay(str(turn_id))
    except Exception:
        # Una publicación perdida se recupera mediante el barrido periódico.
        pass


def enqueue_switch(generation):
    from .tasks import advance_switch
    try:
        advance_switch.delay(str(generation))
    except Exception:
        pass


def request_switch(target):
    from .client import configured_models
    if not configured_models().get(target):
        raise ValueError("El modelo destino no tiene un endpoint configurado.")
    with transaction.atomic():
        state = locked_state()
        if state.pending_model:
            if state.pending_model == target:
                return state
            raise ValueError("Ya hay un cambio pendiente; espere o cancele ese cambio.")
        if target == state.active_model:
            return state
        state.pending_model = target
        state.phase = "draining"
        state.generation = uuid.uuid4()
        state.requested_at = timezone.now()
        state.last_error = ""
        state.source_drained = False
        state.save()
        transaction.on_commit(lambda: enqueue_switch(state.generation))
        return state
