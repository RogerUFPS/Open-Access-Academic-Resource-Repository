from rest_framework import serializers

from .models import ChatTurn, Conversation


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError({"non_field_errors": ["La solicitud contiene campos no permitidos."]})
        return super().to_internal_value(data)


class SubmitMessageSerializer(StrictSerializer):
    prompt = serializers.CharField(min_length=3, max_length=4000, trim_whitespace=True)
    client_message_id = serializers.UUIDField()

    def validate_client_message_id(self, value):
        if value.version != 4:
            raise serializers.ValidationError("Use un UUID v4 aleatorio, sin datos del dispositivo o usuario.")
        return value


class SwitchModelSerializer(StrictSerializer):
    model = serializers.ChoiceField(choices=["qwen", "glm", "llama"])


class ChatTurnSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatTurn
        fields = ["id", "client_message_id", "sequence", "prompt", "status", "response", "unclear", "created_at", "finished_at"]


class AdminTurnSerializer(ChatTurnSerializer):
    class Meta(ChatTurnSerializer.Meta):
        fields = ChatTurnSerializer.Meta.fields + ["model_name"]


class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ["id", "created_at", "updated_at", "has_unclear", "turn_count"]


class CreatedConversationSerializer(ConversationSerializer):
    access_token = serializers.CharField(read_only=True)

    class Meta(ConversationSerializer.Meta):
        fields = ConversationSerializer.Meta.fields + ["access_token"]


class SelectedProgramSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    nombre = serializers.CharField(max_length=500)
    puntuacion = serializers.FloatField(min_value=0, max_value=1)
    razon = serializers.CharField(max_length=4000)


class SearchSerializer(serializers.Serializer):
    plataforma_id = serializers.IntegerField(min_value=1, allow_null=True)
    plataforma = serializers.CharField(max_length=500)
    cadena = serializers.CharField(max_length=8000)
    justificacion = serializers.CharField(max_length=8000)


class UnappliedSerializer(serializers.Serializer):
    plataforma_id = serializers.IntegerField(min_value=1, allow_null=True)
    plataforma = serializers.CharField(max_length=500)
    filtro = serializers.CharField(max_length=500)


class AgentResultSerializer(serializers.Serializer):
    estado = serializers.ChoiceField(choices=["ok", "informacion_catalogo", "fuera_de_tema", "informacion_insuficiente", "error_sistema"])
    mensaje = serializers.CharField(allow_null=True, max_length=4000)
    programas_seleccionados = SelectedProgramSerializer(many=True)
    busquedas = SearchSerializer(many=True)
    filtros_no_aplicados = UnappliedSerializer(many=True)

    def validate(self, data):
        if data["estado"] == "ok" and (data["mensaje"] is not None or not data["programas_seleccionados"] or not data["busquedas"]):
            raise serializers.ValidationError("Recomendación incompleta.")
        if data["estado"] != "ok" and not data["mensaje"]:
            raise serializers.ValidationError("Falta explicación.")
        if data["estado"] in {"fuera_de_tema", "error_sistema"} and any(data[k] for k in ("programas_seleccionados", "busquedas", "filtros_no_aplicados")):
            raise serializers.ValidationError("Rechazo con recomendaciones.")
        return data
