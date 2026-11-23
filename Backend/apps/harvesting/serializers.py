from datetime import timedelta

from django.utils.duration import duration_string
from rest_framework import serializers

from . import models
from .selection import normalize_filters, resolve_filters, OPENALEX_FIELDS, DOAJ_FIELDS

AUDIT_FIELDS = (
    "id",
    "created_by",
    "created_at",
    "updated_by",
    "updated_at",
    "deleted_by",
    "deleted_at",
    "delete_explanation",
)


class ScheduleSerializer(serializers.ModelSerializer):
    selection_filters = serializers.JSONField(
        required=False,
        help_text=(
            "OpenAlex: country=ID de Country. DOAJ: publisher=ID de Editorial, "
            "language=ID de Language; title y subject son texto. "
            "Consulta schedules/filter-options/ para los endpoints de catálogo."
        ),
    )

    def validate_selection_filters(self, value):
        value = normalize_filters(value)
        resolve_filters(value)
        return value

    platform_names = serializers.SlugRelatedField(
        source="platforms",
        slug_field="name",
        many=True,
        read_only=True,
    )

    class Meta:
        model = models.Schedule
        fields = [
            *AUDIT_FIELDS,
            "platforms",
            "platform_names",
            "selection_filters",
            "frequency",
            "max_quantity",
            "stop_after_minutes",
            "start_date",
        ]
        read_only_fields = AUDIT_FIELDS

    def validate_platforms(self, value):
        if not value:
            raise serializers.ValidationError("Debes seleccionar al menos una plataforma.")
        unavailable_platforms = [
            f"{platform.name} ({platform.pk})"
            for platform in value
            if not platform.is_harvestable
        ]
        if unavailable_platforms:
            raise serializers.ValidationError(
                "Estas plataformas no están habilitadas para cosecha: "
                + ", ".join(unavailable_platforms)
                + "."
            )
        return value

    def validate_max_quantity(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("La cantidad máxima debe ser mayor a 0.")
        return value

    def validate_stop_after_minutes(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("El tiempo máximo debe ser mayor a 0 minutos.")
        return value

    def validate(self, attrs):
        max_quantity = attrs.get("max_quantity", getattr(self.instance, "max_quantity", None))
        stop_after_minutes = attrs.get(
            "stop_after_minutes",
            getattr(self.instance, "stop_after_minutes", None),
        )
        if max_quantity is None and stop_after_minutes is None:
            raise serializers.ValidationError(
                "Debes definir al menos un límite: cantidad máxima (max_quantity) "
                "o tiempo máximo en minutos (stop_after_minutes)."
            )
        if self.instance is None and attrs.get("start_date") is None:
            raise serializers.ValidationError(
                {"start_date": "Debes indicar la fecha y hora de la primera ejecución."}
            )
        selection = attrs.get("selection_filters", getattr(self.instance, "selection_filters", {}))
        if "selection_filters" not in attrs:
            try:
                resolve_filters(selection)
            except serializers.ValidationError as exc:
                raise serializers.ValidationError({"selection_filters": exc.detail}) from exc
        platforms = attrs.get("platforms", self.instance.platforms.all() if self.instance else [])
        from .services import _is_doaj_platform
        for platform in platforms:
            allowed = DOAJ_FIELDS if _is_doaj_platform(platform) else OPENALEX_FIELDS
            if set(selection) - allowed:
                raise serializers.ValidationError({"selection_filters": f"Filtros incompatibles con {platform.name}; crea programaciones separadas por proveedor."})
        return attrs


class ScheduleEventSerializer(serializers.ModelSerializer):
    harvests = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = models.ScheduleEvent
        fields = [
            *AUDIT_FIELDS,
            "schedule",
            "scheduled_for",
            "state",
            "started_at",
            "finished_at",
            "error_message",
            "harvests",
        ]
        read_only_fields = fields


class HarvestSerializer(serializers.ModelSerializer):
    platform_name = serializers.CharField(source="platform.name", read_only=True)
    schedule_frequency = serializers.CharField(
        source="schedule.frequency",
        read_only=True,
        default=None,
    )
    duration = serializers.SerializerMethodField()

    class Meta:
        model = models.Harvest
        fields = [
            *AUDIT_FIELDS,
            "platform",
            "platform_name",
            "schedule",
            "event",
            "schedule_frequency",
            "max_quantity",
            "stop_after_minutes",
            "selection_filters",
            "resolved_filters",
            "filter_key",
            "source_exhausted",
            "records_skipped",
            "api_cursor",
            "api_marker",
            "state",
            "records_added",
            "records_updated",
            "records_failed",
            "elapsed_seconds",
            "started_at",
            "finished_at",
            "duration",
            "error_message",
        ]
        read_only_fields = fields

    def get_duration(self, obj) -> str | None:
        if obj.elapsed_seconds:
            return duration_string(timedelta(seconds=obj.elapsed_seconds))
        if obj.started_at and obj.finished_at:
            return duration_string(obj.finished_at - obj.started_at)
        return None


class HarvestQueueErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()
