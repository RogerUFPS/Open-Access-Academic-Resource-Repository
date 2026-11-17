from django.urls import path

from .views import AgentSnapshotView


urlpatterns = [
    path("v1/snapshot/", AgentSnapshotView.as_view(), name="agent-public-snapshot"),
]

