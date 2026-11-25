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
