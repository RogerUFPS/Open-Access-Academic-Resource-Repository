"""Chat sin relaciones de usuario ni metadatos de red o sesión."""
import uuid

from django.db import models
from django.db.models import Q


MODEL_CHOICES = [(name, name.upper()) for name in ("qwen", "glm", "llama")]


class AgentState(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    active_model = models.CharField(max_length=8, choices=MODEL_CHOICES, default="qwen")
    pending_model = models.CharField(max_length=8, choices=MODEL_CHOICES, blank=True)
    phase = models.CharField(max_length=16, default="ready", choices=[
        (name, name) for name in ("ready", "draining", "switching", "error")])
    generation = models.UUIDField(default=uuid.uuid4)
    requested_at = models.DateTimeField(null=True)
    last_error = models.CharField(max_length=200, blank=True)
    source_drained = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(id=1), name="agent_single_state")]


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    access_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True, db_index=True)
    has_unclear = models.BooleanField(default=False, db_index=True)
    turn_count = models.PositiveIntegerField(default=0)


class ChatTurn(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="turns")
    client_message_id = models.UUIDField()
    sequence = models.PositiveIntegerField()
    prompt = models.TextField()
    prompt_key = models.CharField(max_length=64, db_index=True)
    model_name = models.CharField(max_length=8, choices=MODEL_CHOICES)
    status = models.CharField(max_length=12, default="queued", choices=[
        (name, name) for name in ("queued", "running", "completed", "failed")], db_index=True)
    response = models.JSONField(null=True)
    analysis = models.JSONField(default=dict)
    unclear = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(fields=["conversation", "client_message_id"], name="agent_message_idempotent"),
            models.UniqueConstraint(fields=["conversation", "sequence"], name="agent_turn_sequence"),
        ]
        indexes = [models.Index(fields=["status", "created_at"], name="agent_pending_turns")]


class QueryTopic(models.Model):
    turn = models.ForeignKey(ChatTurn, on_delete=models.CASCADE, related_name="topics")
    kind = models.CharField(max_length=8, choices=[("program", "Programa"), ("area", "Área")])
    catalog_id = models.PositiveBigIntegerField()
    name = models.CharField(max_length=500)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["turn", "kind", "catalog_id"], name="agent_topic_once")]
        indexes = [models.Index(fields=["kind", "catalog_id"], name="agent_topic_ranking")]
