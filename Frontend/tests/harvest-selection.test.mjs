import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import test from "node:test";

// Resolve the same source alias as Next.js without adding a test framework.
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith("@/")) {
      return nextResolve(new URL(`../src/${specifier.slice(2)}.js`, import.meta.url).href, context);
    }
    return nextResolve(specifier, context);
  },
});
const {
  buildSchedule, buildSelectionFilters, canRunDueSchedules, formatSelectionFilters, harvestProvider,
  hasRetiredSelectionFilters, runDueErrorMessage, runDueFeedback, selectionValuesFrom,
} = await import("../src/features/admin/harvesting/harvesting.js");

const options = {
  openalex: { country_code: "ISO 3166-1 alpha-2" },
  doaj: { title: "contains", publisher: "contains", subject: "contains", language: "exact" },
};

test("provider comes from platform configuration, not its id", () => {
  assert.equal(harvestProvider({ id: 1, name: "OpenAlex", base_api_url: "" }), "openalex");
  assert.equal(harvestProvider({ id: 2, name: "Fuente A", base_api_url: "https://api.openalex.org" }), "openalex");
  assert.equal(harvestProvider({ id: 3, name: "DOAJ", base_api_url: null }), "doaj");
  assert.equal(harvestProvider({ id: 4, name: "Fuente B", base_api_url: "https://doaj.org/oai/" }), "doaj");
  assert.equal(harvestProvider({ id: 5, name: "Scielo", base_api_url: "https://scielo.org" }), null);
});

test("selection only keeps active fields of the provider", () => {
  const values = { country_code: "co", title: "  salud ", publisher: "", subject: "medicine", language: "es" };
  assert.deepEqual(buildSelectionFilters("openalex", values, options), { country_code: "CO" });
  assert.deepEqual(buildSelectionFilters("doaj", values, options), { title: "salud", subject: "medicine", language: "es" });
  assert.deepEqual(buildSelectionFilters("openalex", { country_code: "" }, options), {});
  assert.deepEqual(buildSelectionFilters(null, values, options), {});
});

test("selection rejects invalid country codes and long texts", () => {
  assert.throws(() => buildSelectionFilters("openalex", { country_code: "COL" }, options), /dos letras/);
  assert.throws(() => buildSelectionFilters("doaj", { title: "x".repeat(121) }, options), /120/);
});

test("schedule payload carries selection_filters", () => {
  const now = new Date("2026-11-21T12:00:00Z");
  const payload = buildSchedule({
    platformId: "12", limit: "500", minutes: "10", mode: "scheduled", startDate: "2026-11-22T09:00",
    frequency: "once", selectionFilters: { country_code: "CO" },
  }, now);
  assert.deepEqual(payload.selection_filters, { country_code: "CO" });
  assert.deepEqual(buildSchedule({ platformId: "12", limit: "5", minutes: "", mode: "scheduled", startDate: "2026-11-22T09:00", frequency: "once" }, now).selection_filters, {});
});

test("selection display and retired filters", () => {
  assert.equal(formatSelectionFilters({}), "Recorrido global");
  assert.equal(formatSelectionFilters({ country_code: "CO" }, new Map([["CO", "Colombia"]])), "País: Colombia");
  assert.match(formatSelectionFilters({ is_oa: true }), /filtro retirado/);
  assert.equal(hasRetiredSelectionFilters({ country_code: "CO", is_in_doaj: true }), true);
  assert.deepEqual(selectionValuesFrom({ country_code: "co", is_oa: true }).country_code, "CO");
});

test("run-due permission and responses", () => {
  assert.equal(canRunDueSchedules({ effective_permissions: { harvesting: { schedules: { run_due: true } } } }), true);
  assert.equal(canRunDueSchedules({ effective_permissions: { harvesting: { schedules: { view: true } } } }), false);
  assert.equal(canRunDueSchedules({ is_superadmin: true }), true);
  assert.match(runDueFeedback({ status: 202 }).message, /no significa que hayan terminado/);
  assert.match(runDueFeedback({ status: 200 }).message, /no hubiera nuevas/);
  assert.match(runDueErrorMessage({ status: 425, message: "Demasiado pronto.", retryAfter: 30 }), /30 segundos/);
});
