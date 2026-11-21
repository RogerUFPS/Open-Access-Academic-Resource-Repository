import AiModulePanel from "@/features/admin/agent/components/AiModulePanel";

export const metadata = {
  title: "Módulo de IA | Administración",
};

export default async function AiModulePage({ searchParams }) {
  const params = await searchParams;
  const initialTab = params?.tab === "analitica" ? "analitica" : "modelos";
  return <AiModulePanel initialTab={initialTab} />;
}
