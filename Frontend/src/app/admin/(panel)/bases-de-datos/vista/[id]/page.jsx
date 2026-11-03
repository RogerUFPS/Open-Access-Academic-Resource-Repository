"use client";

import { use } from "react";
import DatabaseDetail from "@/features/admin/databases/components/DatabaseDetail";

export default function AdminDatabaseViewPage({ params }) {
  const resolvedParams = params && typeof params.then === "function" ? use(params) : params;
  return <DatabaseDetail platformId={resolvedParams?.id} />;
}
