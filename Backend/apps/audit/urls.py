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
    *router.urls,
]
