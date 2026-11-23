from django.urls import path

from .views import AgentSnapshotView
from . import chat_views as chat


urlpatterns = [
    path("v1/snapshot/", AgentSnapshotView.as_view(), name="agent-public-snapshot"),
    path("chat/conversations/", chat.CreateConversationView.as_view(), name="agent-chat-create"),
    path("chat/conversations/<uuid:conversation_id>/messages/", chat.PublicMessagesView.as_view(), name="agent-chat-messages"),
    path("chat/conversations/<uuid:conversation_id>/messages/<uuid:turn_id>/", chat.PublicMessageView.as_view(), name="agent-chat-message"),
    path("models/", chat.ModelStatusView.as_view(), name="agent-model-status"),
    path("models/switch/", chat.SwitchModelView.as_view(), name="agent-model-switch"),
    path("models/cancel/", chat.CancelSwitchView.as_view(), name="agent-model-cancel"),
    path("conversations/", chat.AdminConversationsView.as_view(), name="agent-conversations"),
    path("conversations/<uuid:conversation_id>/", chat.AdminConversationView.as_view(), name="agent-conversation"),
    path("analytics/topics/", chat.TopicRankingView.as_view(), name="agent-topic-ranking"),
    path("analytics/queries/", chat.FrequentQueriesView.as_view(), name="agent-frequent-queries"),
]

