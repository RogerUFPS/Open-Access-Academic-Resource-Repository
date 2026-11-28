import assert from "node:assert/strict";
import test from "node:test";

const { buildJournalChecklist, isChecklistComplete } = await import(
  "../src/shared/utils/publishChecklists.js"
);

const journalRequirements = {
  issn: "1234-5678",
  title: "Revista de prueba",
  editorial: 1,
  publicationDate: "2026-01-01",
  languages: [1],
  countries: [1],
  materialTypes: [1],
  academicPrograms: [1],
  platforms: [{ platform: 1, published: true }],
  licenses: [1],
};

test("journal publication checklist requires an image URL", () => {
  const checklistWithoutImage = buildJournalChecklist(journalRequirements);
  const imageRequirement = checklistWithoutImage.find((item) => item.key === "url_image");

  assert.equal(imageRequirement.done, false);
  assert.equal(isChecklistComplete(checklistWithoutImage), false);

  const checklistWithImage = buildJournalChecklist({
    ...journalRequirements,
    urlImage: "https://example.org/journal.png",
  });
  const completedImageRequirement = checklistWithImage.find((item) => item.key === "url_image");

  assert.equal(completedImageRequirement.done, true);
  assert.equal(isChecklistComplete(checklistWithImage), true);
});

test("journal checklist requires a published platform with the journal URL", () => {
  const platformsItem = (platforms) =>
    buildJournalChecklist({ ...journalRequirements, platforms }).find((item) => item.key === "platforms");

  assert.equal(platformsItem([{ platform: 1, published: false, hasUrl: true }]).done, false);
  assert.equal(platformsItem([{ platform: 1, published: true, hasUrl: false }]).done, false);
  assert.equal(
    platformsItem([
      { platform: 1, published: false, hasUrl: true },
      { platform: 2, published: true, hasUrl: true },
    ]).done,
    true
  );
});

test("journal checklist explains link verification state", () => {
  const hint = (platforms) =>
    buildJournalChecklist({ ...journalRequirements, platforms }).find((item) => item.key === "platforms").hint;

  assert.match(hint([{ platform: 1, published: true, hasUrl: true, serving: false }]), /se verificarán al publicar/);
  assert.match(
    hint([
      { platform: 1, published: true, hasUrl: true, serving: true },
      { platform: 2, published: true, hasUrl: true, serving: false },
    ]),
    /^1 asociación/
  );
  assert.match(hint([{ platform: 1, published: false, hasUrl: true }]), /Ninguna de las plataformas/);
});
