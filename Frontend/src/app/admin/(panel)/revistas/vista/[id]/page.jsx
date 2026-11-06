"use client";

import { use } from "react";
import JournalDetail from "@/features/admin/journals/components/JournalDetail";

export default function AdminJournalViewPage({ params }) {
  const resolvedParams = params && typeof params.then === "function" ? use(params) : params;
  return <JournalDetail journalId={resolvedParams?.id} />;
}
