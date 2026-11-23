import Link from "next/link";
import AgentPanel from "@/features/public/agent/AgentPanel";

export const metadata = {
  title: "Asistente de búsqueda | Biblioteca",
  description:
    "Consulta al asistente académico anónimo para obtener estrategias y cadenas de búsqueda en las bases de datos y revistas del directorio.",
};

export default function AssistantPage() {
  return (
    <main className="flex-1">
      <section className="border-b border-[#e2dcd7] bg-[#efedeb]">
        <div className="mx-auto max-w-5xl px-5 py-9 sm:px-8 sm:py-12">
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#7f1218]">
            Biblioteca / Asistente IA
          </p>
          <h1 className="mt-2.5 text-3xl font-bold text-[#1f1a1a] sm:text-4xl">
            Asistente de búsqueda académica
          </h1>
          <p className="mt-2.5 max-w-2xl text-sm leading-6 text-[#5c5252] sm:text-base">
            Describe qué necesitas investigar y te recomendaremos recursos del directorio junto con cadenas de búsqueda
            y su justificación. No requiere inicio de sesión.
          </p>
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-5 py-8 sm:px-8 sm:py-10">
        <AgentPanel />
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-xs text-[#5c5252]">
          <p>
            Tu conversación es anónima y permanece activa únicamente en esta pestaña del navegador.
          </p>
          <Link
            href="/directorio"
            className="font-semibold text-[#a3141c] underline decoration-[#c9a45c] underline-offset-4 hover:text-[#8a1018]"
          >
            Explorar el directorio manualmente →
          </Link>
        </div>
      </section>
    </main>
  );
}
