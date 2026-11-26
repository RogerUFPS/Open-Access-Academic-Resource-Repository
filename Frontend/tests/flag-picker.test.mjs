import assert from "node:assert/strict";
import test from "node:test";

const {
  FLAG_COUNTRIES,
  countryFlagEmoji,
  filterFlagCountries,
  suggestCountryAbbreviation,
} = await import("../src/features/admin/catalogs/flagCountries.js");

test("flag list contains unique ISO alpha-2 countries and generated regional-indicator emoji", () => {
  const codes = FLAG_COUNTRIES.map(({ code }) => code);

  assert.equal(codes.length, 249);
  assert.equal(new Set(codes).size, codes.length);
  assert.ok(codes.every((code) => /^[A-Z]{2}$/.test(code)));
  assert.equal(countryFlagEmoji("CO"), "🇨🇴");
  assert.equal(countryFlagEmoji("DE"), "🇩🇪");
  assert.equal(countryFlagEmoji("co"), "");
});

test("flag search matches Spanish names without accents and ISO codes", () => {
  assert.ok(filterFlagCountries("alemania").some(({ code }) => code === "DE"));
  assert.ok(filterFlagCountries("MÉXICO").some(({ code }) => code === "MX"));
  assert.ok(filterFlagCountries("co").some(({ code }) => code === "CO"));
});

test("country selection suggests an abbreviation without replacing an existing value", () => {
  assert.equal(suggestCountryAbbreviation("", "CO"), "CO");
  assert.equal(suggestCountryAbbreviation("  ", "DE"), "DE");
  assert.equal(suggestCountryAbbreviation("custom", "DE"), "custom");
});
