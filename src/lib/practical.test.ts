import { test } from "node:test";
import assert from "node:assert/strict";
import { isPractical, needsCheck, practicalRefs } from "./practical.ts";

test("pratik bilgi metinden tanınır", () => {
  assert.ok(isPractical("Pompei bileti 18 Euro'dur."));
  assert.ok(isPractical("Venedik'te mayoyla dolaşmak yasaktır."));
  assert.ok(!isPractical("Kolezyum MS 80'de açıldı."));
});

test("iddia listesinden kimlikler ve sahne işareti", () => {
  const claims = "C1 [weak] (Temmuz 2025) Pompei bileti 18 Euro'dur.\nC2 [verified] Kolezyum MS 80'de açıldı.";
  const refs = practicalRefs(claims);
  assert.deepEqual([...refs], ["C1"]);
  assert.ok(needsCheck({ claim_refs: ["C2", "C1"] }, refs));
  assert.ok(!needsCheck({ claim_refs: ["C2"] }, refs));
  assert.ok(needsCheck({ needs_check: true, claim_refs: [] }, refs));
});
