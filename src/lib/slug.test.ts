import { test } from "node:test";
import assert from "node:assert/strict";
import { slugify } from "./slug.ts";

test("kısa ad başlığın tamamından üretilir", () => {
  assert.equal(slugify("1453 - İstanbulun Fethi"), "1453-istanbulun-fethi");
  assert.equal(slugify("Pompei'nin Son Günü — Vezüv'ün Yok Ettiği Şehir"), "pompeinin-son-gunu-vezuvun-yok-ettigi-sehir");
  assert.ok(slugify("Çok ".repeat(40)).length <= 48);
});
