"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import { MessageSquare, Sparkles } from "lucide-react";
import AgentPanel from "@/features/public/agent/AgentPanel";

export default function PublicChatWidget() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  // En la página dedicada del asistente no se duplica el widget flotante.
  if (pathname === "/asistente" || pathname?.startsWith("/asistente/")) {
    return null;
  }

  return (
    <div className="fixed right-4 bottom-4 z-40 sm:right-6 sm:bottom-6">
      {open ? (
        <div
          role="dialog"
          aria-label="Asistente de búsqueda académica"
          className="fixed inset-0 z-50 flex flex-col bg-white sm:static sm:h-[600px] sm:max-h-[calc(100dvh-5rem)] sm:w-[420px] sm:rounded-xl sm:border sm:border-[#e7dfd9] sm:shadow-[0_24px_60px_rgba(31,26,26,0.22)]"
        >
          <AgentPanel compact onClose={() => setOpen(false)} expandHref="/asistente" />
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-haspopup="dialog"
          className="inline-flex items-center gap-2.5 rounded-full bg-[#7f1218] px-4 py-3 text-sm font-semibold text-white shadow-[0_12px_30px_rgba(127,18,24,0.35)] transition hover:bg-[#a3141c] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7f1218]"
        >
          <Sparkles className="h-4 w-4 text-[#f5d79b]" aria-hidden="true" />
          <span>Asistente IA</span>
          <MessageSquare className="h-4 w-4 opacity-85" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
