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

if (!process.env.NEXT_PUBLIC_API_URL) {
  process.env.NEXT_PUBLIC_API_URL = "http://localhost";
}

const { formatPublicationMonth, getIndicators, sortPublicationMonths } = await import("../src/features/admin/indicators/indicatorsService.js");

test("indicators request uses the shared API client endpoint and includes the abort signal", async () => {
  const originalFetch = globalThis.fetch;
  const controller = new AbortController();
  let requestUrl;
  let requestOptions;
  const responseData = {
    published_journals: 0,
    published_journals_this_month: 0,
    pending_journals: 0,
    link_availability: { percentage: 0, available: 0, total: 0 },
    publications_by_month: [],
    journals_by_knowledge_area: [],
  };
  globalThis.fetch = async (url, options) => {
    requestUrl = url;
    requestOptions = options;
    return new Response(JSON.stringify(responseData), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };

  try {
    assert.deepEqual(await getIndicators(controller.signal), responseData);
    assert.match(requestUrl, /\/api\/indicators\/$/);
    assert.equal(requestOptions.method, "GET");
    assert.equal(requestOptions.credentials, "include");
    assert.equal(requestOptions.signal, controller.signal);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("indicator request errors preserve 401 and 403 status for the page", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => { globalThis.fetch = originalFetch; });

  for (const status of [401, 403]) {
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: "No autorizado." }), {
      status,
      headers: { "content-type": "application/json" },
    });
    await assert.rejects(getIndicators(), { status, message: "No autorizado." });
  }
});

test("monthly publications are sorted chronologically without mutating the response", () => {
  const responseMonths = [
    { month: "2026-03", count: 0 },
    { month: "2025-12", count: 2 },
    { month: "2026-01", count: 0 },
  ];

  assert.deepEqual(
    sortPublicationMonths(responseMonths).map(({ month }) => month),
    ["2025-12", "2026-01", "2026-03"],
  );
  assert.deepEqual(responseMonths.map(({ month }) => month), ["2026-03", "2025-12", "2026-01"]);
  assert.deepEqual(sortPublicationMonths([]), []);
});

test("monthly labels are readable while keeping invalid original values unchanged", () => {
  assert.match(formatPublicationMonth("2026-11"), /2026/);
  assert.equal(formatPublicationMonth("not-a-month"), "not-a-month");
});
