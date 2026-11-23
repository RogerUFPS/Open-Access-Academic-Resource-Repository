import hashlib
import secrets
import unicodedata
from datetime import datetime

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import CustomPageNumberPagination
from .chat_serializers import (AdminTurnSerializer, ChatTurnSerializer, ConversationSerializer, CreatedConversationSerializer,
    SubmitMessageSerializer, SwitchModelSerializer)
from .client import AgentClient, AgentUnavailable, configured_models
from .models import AgentState, ChatTurn, Conversation, QueryTopic
from .privacy import digest, redact
from .services import PENDING, enqueue_turn, locked_state, request_switch


def paginated(view, queryset, serializer, request):
    paginator = CustomPageNumberPagination()
    page = paginator.paginate_queryset(queryset, request, view=view)
    return paginator.get_paginated_response(serializer(page, many=True).data)


def conversation_for(request, conversation_id):
    token = request.headers.get("X-Chat-Token", "")
    conversation = Conversation.objects.filter(pk=conversation_id).first()
    expected = conversation.access_digest if conversation else "0" * 64
    if not secrets.compare_digest(digest(token), expected) or not conversation:
        raise NotFound("Conversación no encontrada.")
    return conversation


class PublicChatView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]


class CreateConversationView(PublicChatView):
    @extend_schema(request=None, responses={201: CreatedConversationSerializer}, tags=["Agente - Chat público"])
    def post(self, request):
        if request.data:
            raise ValidationError("No se aceptan datos personales ni identificadores de cuenta.")
        token = secrets.token_urlsafe(32)
        conversation = Conversation.objects.create(access_digest=digest(token))
        return Response({**ConversationSerializer(conversation).data, "access_token": token}, status=201)


class PublicMessagesView(PublicChatView):
    @extend_schema(responses=ChatTurnSerializer(many=True), tags=["Agente - Chat público"])
    def get(self, request, conversation_id):
        conversation = conversation_for(request, conversation_id)
        return paginated(self, conversation.turns.order_by("sequence"), ChatTurnSerializer, request)

    @extend_schema(request=SubmitMessageSerializer, responses={202: ChatTurnSerializer}, tags=["Agente - Chat público"])
    def post(self, request, conversation_id):
        conversation_for(request, conversation_id)
        serializer = SubmitMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        prompt = redact(serializer.validated_data["prompt"])
        message_id = serializer.validated_data["client_message_id"]
        with transaction.atomic():
            state = locked_state()
            conversation = Conversation.objects.select_for_update().get(pk=conversation_id)
            previous = conversation.turns.filter(client_message_id=message_id).first()
            if previous:
                return Response(ChatTurnSerializer(previous).data, status=202 if previous.status in PENDING else 200)
            if state.pending_model or state.phase != "ready":
                return Response({"code": "model_switch_pending", "detail": "Se está cambiando el modelo. Intente después."}, status=503, headers={"Retry-After": "10"})
            if not configured_models().get(state.active_model):
                return Response({"code": "agent_unavailable", "detail": "El agente no está configurado."}, status=503)
            if conversation.turns.filter(status__in=PENDING).exists():
                return Response({"code": "conversation_busy", "detail": "Espere la respuesta anterior."}, status=409)
            if ChatTurn.objects.filter(status__in=PENDING).count() >= settings.AGENT_MAX_PENDING:
                return Response({"code": "agent_busy", "detail": "El servicio está ocupado."}, status=429, headers={"Retry-After": "10"})
            normalized = " ".join(unicodedata.normalize("NFKC", prompt).casefold().split())
            turn = ChatTurn.objects.create(conversation=conversation, client_message_id=message_id,
                sequence=conversation.turn_count + 1, prompt=prompt,
                prompt_key=hashlib.sha256(normalized.encode()).hexdigest(), model_name=state.active_model)
            conversation.turn_count += 1
            conversation.updated_at = timezone.now()
            conversation.save(update_fields=["turn_count", "updated_at"])
            transaction.on_commit(lambda: enqueue_turn(turn.pk))
        return Response(ChatTurnSerializer(turn).data, status=202, headers={"Retry-After": "2"})


class PublicMessageView(PublicChatView):
    @extend_schema(responses=ChatTurnSerializer, tags=["Agente - Chat público"])
    def get(self, request, conversation_id, turn_id):
        conversation = conversation_for(request, conversation_id)
        turn = conversation.turns.filter(pk=turn_id).first()
        if not turn:
            raise NotFound()
        return Response(ChatTurnSerializer(turn).data)


class ModelStatusView(APIView):
    @extend_schema(tags=["Agente - Administración"])
    def get(self, request):
        state, _ = AgentState.objects.get_or_create(pk=1, defaults={"active_model": settings.AGENT_DEFAULT_MODEL})
        return Response({"active_model": state.active_model, "pending_model": state.pending_model or None,
            "phase": state.phase, "inflight": ChatTurn.objects.filter(status__in=PENDING).count(),
            "generation": state.generation, "last_error": state.last_error or None,
            "available_models": [{"name": name, "configured": available} for name, available in configured_models().items()]})


class SwitchModelView(APIView):
    @extend_schema(request=SwitchModelSerializer, tags=["Agente - Administración"])
    def post(self, request):
        serializer = SwitchModelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            state = request_switch(serializer.validated_data["model"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response({"active_model": state.active_model, "pending_model": state.pending_model or None,
            "phase": state.phase, "generation": state.generation}, status=202 if state.pending_model else 200)


class CancelSwitchView(APIView):
    @extend_schema(request=None, tags=["Agente - Administración"])
    def post(self, request):
        with transaction.atomic():
            state = locked_state()
            if state.phase == "switching":
                return Response({"detail": "El controlador está realizando el cambio; espere."}, status=409)
            import uuid
            state.phase = "switching"
            state.generation = uuid.uuid4()
            state.save(update_fields=["phase", "generation", "updated_at"])
            source, generation = state.active_model, state.generation
        try:
            with AgentClient(source) as client:
                client.control("resume")
        except AgentUnavailable:
            AgentState.objects.filter(pk=1, generation=generation).update(phase="error", last_error="No se pudo reactivar el modelo anterior.")
            return Response({"detail": "No se pudo reactivar el modelo anterior."}, status=503)
        with transaction.atomic():
            state = locked_state()
            if state.generation != generation:
                return Response({"detail": "El estado cambió; vuelva a consultarlo."}, status=409)
            state.generation = uuid.uuid4()
            state.pending_model = ""
            state.phase = "ready"
            state.last_error = ""
            state.save()
        return Response({"active_model": source, "phase": "ready"})


class AdminConversationsView(APIView):
    @extend_schema(responses=ConversationSerializer(many=True), tags=["Agente - Administración"])
    def get(self, request):
        queryset = Conversation.objects.all().order_by("-updated_at", "id")
        unclear = request.query_params.get("unclear")
        if unclear not in (None, "true", "false"):
            raise ValidationError("unclear debe ser true o false.")
        if unclear is not None:
            queryset = queryset.filter(has_unclear=unclear == "true")
        return paginated(self, queryset, ConversationSerializer, request)


class AdminConversationView(APIView):
    @extend_schema(responses=AdminTurnSerializer(many=True), tags=["Agente - Administración"])
    def get(self, request, conversation_id):
        if not Conversation.objects.filter(pk=conversation_id).exists():
            raise NotFound()
        return paginated(self, ChatTurn.objects.filter(conversation_id=conversation_id).order_by("sequence"), AdminTurnSerializer, request)


class TopicRankingView(APIView):
    @extend_schema(tags=["Agente - Administración"])
    def get(self, request):
        kind = request.query_params.get("kind", "program")
        if kind not in {"program", "area"}:
            raise ValidationError("kind debe ser program o area.")
        queryset = QueryTopic.objects.filter(kind=kind)
        try:
            for param, lookup in (("since", "gte"), ("until", "lte")):
                if request.query_params.get(param):
                    date = datetime.strptime(request.query_params[param], "%Y-%m-%d").date()
                    queryset = queryset.filter(**{f"turn__created_at__date__{lookup}": date})
            limit = int(request.query_params.get("limit", "20"))
            if not 1 <= limit <= 100:
                raise ValueError()
        except ValueError:
            raise ValidationError("Fechas AAAA-MM-DD y limit entre 1 y 100.")
        rows = list(queryset.values("catalog_id").annotate(name=Max("name"), queries=Count("turn", distinct=True),
            conversations=Count("turn__conversation", distinct=True)).order_by("-queries", "catalog_id")[:limit])
        rank, last_count = 0, None
        for row in rows:
            if row["queries"] != last_count:
                rank += 1
                last_count = row["queries"]
            row["tier"] = rank
        return Response({"kind": kind, "results": rows})


class FrequentQueriesView(APIView):
    @extend_schema(tags=["Agente - Administración"])
    def get(self, request):
        rows = ChatTurn.objects.exclude(status__in=PENDING).values("prompt_key").annotate(
            prompt=Max("prompt"), queries=Count("id"), conversations=Count("conversation", distinct=True)
        ).order_by("-queries", "prompt_key")[:100]
        return Response({"results": list(rows)})
