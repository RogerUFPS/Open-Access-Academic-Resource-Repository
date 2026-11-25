import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import test from "node:test";

process.env.NEXT_PUBLIC_API_URL ||= "http://localhost";

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith("@/")) {
      return nextResolve(new URL(`../src/${specifier.slice(2)}.js`, import.meta.url).href, context);
    }
    return nextResolve(specifier, context);
  },
});

const { catalogAdminService, CATALOG_RESOURCES } = await import(
  "../src/features/admin/catalogs/catalogAdminService.js"
);
const { catalogResourcePermissions, viewableCatalogResources } = await import(
  "../src/features/admin/catalogs/catalogPermissions.js"
);

test("catalog listing requests use documented endpoints and pagination parameters", async (context) => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  context.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async (url, options) => {
    requests.push({ url: new URL(url), options });
    return new Response(JSON.stringify({
      current_page: 2,
      total_pages: 3,
      page_size: 10,
      total_items: 21,
      next: "next",
      previous: "previous",
      results: [],
    }), { status: 200, headers: { "content-type": "application/json" } });
  };

  for (const resource of ["institutions", "languages", "countries"]) {
    const response = await catalogAdminService.list(resource, {
      search: "  test ",
      page: 2,
      pageSize: 10,
    });
    assert.equal(response.current_page, 2);
  }
  await catalogAdminService.list("countries", { archived: true });

  assert.deepEqual(
    requests.slice(0, 3).map(({ url }) => url.pathname),
    Object.values(CATALOG_RESOURCES).map(({ endpoint }) => endpoint)
  );
  assert.equal(requests[0].url.searchParams.get("search"), "test");
  assert.equal(requests[0].url.searchParams.get("ordering"), "name");
  assert.equal(requests[0].url.searchParams.get("page"), "2");
  assert.equal(requests[0].url.searchParams.get("page_size"), "10");
  assert.equal(requests[3].url.pathname, "/api/catalog/countries/archived/");
});

test("catalog mutations use the documented detail, create, update, archive, and restore contracts", async (context) => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  context.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async (url, options) => {
    requests.push({ url: new URL(url), options });
    return options.method === "DELETE"
      ? new Response(null, { status: 204 })
      : new Response(JSON.stringify({ id: 8 }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
  };

  await catalogAdminService.get("languages", 8);
  await catalogAdminService.create("institutions", { name: "Universidad" });
  await catalogAdminService.update("countries", 8, {
    name: "Colombia",
    abbreviation: "co",
    emoji_flag: "🇨🇴",
  });
  await catalogAdminService.archive("languages", 8, "Actualización del catálogo");
  await catalogAdminService.restore("countries", 8);

  assert.deepEqual(requests.map(({ options }) => options.method), ["GET", "POST", "PATCH", "DELETE", "POST"]);
  assert.equal(requests[0].url.pathname, "/api/catalog/languages/8/");
  assert.equal(requests[1].url.pathname, "/api/catalog/institutions/");
  assert.equal(requests[2].url.pathname, "/api/catalog/countries/8/");
  assert.equal(requests[3].url.pathname, "/api/catalog/languages/8/");
  assert.deepEqual(JSON.parse(requests[3].options.body), {
    delete_explanation: "Actualización del catálogo",
  });
  assert.equal(requests[4].url.pathname, "/api/catalog/countries/8/restore/");
});

test("catalog permissions expose only allowed resources and actions", () => {
  const viewer = {
    effective_permissions: {
      catalog: {
        institutions: { view: true, create: true, update: false, delete: true, restore: false },
        languages: { view: false, create: true, update: true, delete: true, restore: true },
        countries: { view: true, create: false, update: false, delete: false, restore: true },
      },
    },
  };

  assert.deepEqual(viewableCatalogResources(viewer), ["institutions", "countries"]);
  assert.deepEqual(catalogResourcePermissions(viewer, "institutions"), {
    view: true,
    create: true,
    update: false,
    delete: true,
    restore: false,
  });
  assert.deepEqual(catalogResourcePermissions({ is_superadmin: true }, "languages"), {
    view: true,
    create: true,
    update: true,
    delete: true,
    restore: true,
  });
});

test("catalog requests preserve specific 400, 401, and 403 API errors", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => { globalThis.fetch = originalFetch; });

  for (const status of [400, 401, 403]) {
    const message = `Error específico ${status}`;
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: message }), {
      status,
      headers: { "content-type": "application/json" },
    });

    await assert.rejects(
      catalogAdminService.list("institutions"),
      (error) => error.status === status && error.message === message
    );
  }
});
