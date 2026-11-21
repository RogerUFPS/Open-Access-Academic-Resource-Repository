import ConversationDetail from "@/features/admin/agent/components/ConversationDetail";

export const metadata = {
  title: "Detalle del chat | Administración",
};

export default async function ChatDetailPage({ params }) {
  const { id } = await params;
  return <ConversationDetail conversationId={id} />;
}
