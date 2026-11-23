from datetime import datetime

from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.journal import models as journal_models
from apps.platforms import services as platform_services


def _next_month(month):
    if month.month == 12:
        return month.replace(year=month.year + 1, month=1)
    return month.replace(month=month.month + 1)


def _month_range(month):
    start = timezone.make_aware(datetime.combine(month, datetime.min.time()))
    next_month = _next_month(month)
    end = timezone.make_aware(datetime.combine(next_month, datetime.min.time()))
    return start, end


class IndicatorsView(APIView):
    @extend_schema(
        summary="Consultar indicadores administrativos",
        description=(
            "Devuelve en una sola respuesta los indicadores del panel: "
            "revistas publicadas, pendientes, publicaciones mensuales, "
            "disponibilidad de enlaces y revistas por área temática."
        ),
        responses=inline_serializer(
            name="IndicatorsResponse",
            fields={
                "published_journals": serializers.IntegerField(),
                "published_journals_this_month": serializers.IntegerField(),
                "pending_journals": serializers.IntegerField(),
                "link_availability": serializers.DictField(),
                "publications_by_month": serializers.ListField(),
                "journals_by_knowledge_area": serializers.ListField(),
            },
        ),
        tags=["Indicadores"],
    )
    def get(self, _request):
        journals = journal_models.Journal.objects.filter(
            deleted_at__isnull=True,
        )
        published = journals.filter(active=True, validated_at__isnull=False)
        today = timezone.localdate()
        current_month = today.replace(day=1)
        month_start, month_end = _month_range(current_month)
        monthly = []
        month = current_month
        for _ in range(12):
            start, end = _month_range(month)
            monthly.append({
                "month": month.strftime("%Y-%m"),
                "count": published.filter(
                    validated_at__gte=start,
                    validated_at__lt=end,
                ).count(),
            })
            month = month.replace(
                year=month.year - 1 if month.month == 1 else month.year,
                month=12 if month.month == 1 else month.month - 1,
            )
        monthly.reverse()

        link_logs = platform_services.current_link_logs()
        total_links = link_logs.count()
        available_links = link_logs.filter(
            last_check__isnull=False,
            is_active=True,
        ).count()
        availability = round(
            available_links * 100 / total_links,
            2,
        ) if total_links else 0

        areas = (
            journal_models.SharedJournalKnowledgeArea.objects
            .filter(
                deleted_at__isnull=True,
                knowledge_area__deleted_at__isnull=True,
                journal__deleted_at__isnull=True,
                journal__active=True,
                journal__validated_at__isnull=False,
            )
            .values(
                "knowledge_area_id",
                "knowledge_area__name",
            )
            .annotate(journals=Count("journal_id", distinct=True))
            .order_by("knowledge_area__name")
        )

        return Response({
            "published_journals": published.count(),
            "published_journals_this_month": published.filter(
                validated_at__gte=month_start,
                validated_at__lt=month_end,
            ).count(),
            "pending_journals": journals.filter(
                Q(active=False) | Q(validated_at__isnull=True),
            ).count(),
            "link_availability": {
                "percentage": availability,
                "available": available_links,
                "total": total_links,
            },
            "publications_by_month": monthly,
            "journals_by_knowledge_area": [
                {
                    "id": area["knowledge_area_id"],
                    "name": area["knowledge_area__name"],
                    "journals": area["journals"],
                }
                for area in areas
            ],
        }, status=status.HTTP_200_OK)
