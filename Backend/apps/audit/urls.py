from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("logs", views.AuditLogViewSet, basename="audit-log")

# El primer segmento es el recurso de permiso: audit.archived-logs y
# audit.archived-superadmin-events.
urlpatterns = [
    path("archived-logs/", views.ArchivedAuditLogView.as_view(), name="audit-archived-logs"),
    path(
        "archived-superadmin-events/",
        views.ArchivedSuperadminEventView.as_view(),
        name="audit-archived-superadmin-events",
    ),
    # Recurso de permiso: audit.archive-anomalies (view / resolve).
    path(
        "archive-anomalies/",
        views.ArchiveAnomalyListView.as_view(),
        name="audit-archive-anomalies",
    ),
    path(
        "archive-anomalies/resolve/",
        views.ResolveArchiveAnomalyView.as_view(),
        name="audit-archive-anomalies-resolve",
    ),
    path(
        "archive-anomalies/<str:source>/<str:snapshot_id>/records/",
        views.ArchiveAnomalyRecordsView.as_view(),
        name="audit-archive-anomaly-records",
    ),
    *router.urls,
]
