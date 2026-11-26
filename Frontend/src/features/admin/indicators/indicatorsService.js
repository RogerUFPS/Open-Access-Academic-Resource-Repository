import { apiClient } from "@/shared/services/apiClient";

export function getIndicators(signal) {
  return apiClient.get("/api/indicators/", {}, { signal, cache: "no-store" });
}

export function sortPublicationMonths(months = []) {
  return [...months].sort((first, second) => first.month.localeCompare(second.month));
}

export function formatPublicationMonth(month) {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  if (!match) return month;

  const [, year, monthNumber] = match;
  const date = new Date(Date.UTC(Number(year), Number(monthNumber) - 1, 1));
  return new Intl.DateTimeFormat("es-CO", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}
