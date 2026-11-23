import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import test from "node:test";

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith("@/")) {
      return nextResolve(new URL(`../src/${specifier.slice(2)}.js`, import.meta.url).href, context);
    }
    return nextResolve(specifier, context);
  },
});

const { buildSchedule, buildSelectionFilters, createHarvestingApi, getHarvestProvider } = await import("../src/features/admin/harvesting/harvesting.js");

test("selection filters send catalog IDs as JSON numbers and drop empty keys", () => {
  assert.deepEqual(buildSelectionFilters({ country: "7" }, ["country"]), { country: 7 });
  assert.deepEqual(
    buildSelectionFilters({ publisher: "25", language: 3, title: "  ", subject: " medicine " }, ["publisher", "language", "title", "subject"]),
    { publisher: 25, language: 3, subject: "medicine" },
  );
  assert.deepEqual(buildSelectionFilters({ country: "" }, ["country"]), {});
});

test("selection filters ignore fields from another provider and reject invalid values", () => {
  assert.deepEqual(buildSelectionFilters({ country: 7, publisher: 25 }, ["publisher"]), { publisher: 25 });
  assert.throws(() => buildSelectionFilters({ country: "abc" }, ["country"]));
  assert.throws(() => buildSelectionFilters({ title: "x".repeat(121) }, ["title"]));
});

test("provider detection mirrors the backend DOAJ rule", () => {
  assert.equal(getHarvestProvider({ name: "DOAJ" }), "doaj");
  assert.equal(getHarvestProvider({ name: "Directorio", base_api_url: "https://doaj.org/oai/" }), "doaj");
  assert.equal(getHarvestProvider({ name: "OpenAlex", base_api_url: "https://api.openalex.org" }), "openalex");
});

test("schedule payload includes selection_filters", () => {
  const now = new Date("2026-11-21T12:00:00Z");
  const payload = buildSchedule({ platformId: "12", limit: "500", minutes: "10", mode: "scheduled", startDate: "2026-11-22T09:00", frequency: "once", selectionFilters: { country: 7 } }, now);
  assert.deepEqual(payload.selection_filters, { country: 7 });
  assert.deepEqual(buildSchedule({ platformId: "12", limit: "1", minutes: "", mode: "scheduled", startDate: "2026-11-22T09:00", frequency: "once" }, now).selection_filters, {});
});

function apiResponding(status, data) {
  return createHarvestingApi(async () => ({ status, data }));
}

test("400 field errors keep the previous format for lists of messages", async () => {
  const api = apiResponding(400, { max_quantity: ["Debe ser mayor que cero.", "Valor inválido."] });
  await assert.rejects(api.createSchedule({}), { message: "Límite de revistas: Debe ser mayor que cero. Valor inválido." });
});

test("400 nested selection_filters errors are readable", async () => {
  const api = apiResponding(400, { selection_filters: { publisher: ["El ID no existe o está archivado en el catálogo."] } });
  await assert.rejects(api.updateScheduleFilters(10, { publisher: 999 }), {
    message: "Filtros: Editorial: El ID no existe o está archivado en el catálogo.",
  });
});
