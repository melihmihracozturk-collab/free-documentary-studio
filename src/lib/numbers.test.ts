import { test } from "node:test";
import assert from "node:assert/strict";
import { extractNumbers, unsupportedNumbers } from "./numbers.ts";

const set = (...xs: number[]) => new Set(xs);

test("Türkçe yazıyla sayılar", () => {
  assert.deepEqual(extractNumbers("Milattan sonra yetmiş dokuz yılında"), set(79));
  assert.deepEqual(extractNumbers("bin yedi yüz altmış dört yılında İsis Tapınağı"), set(1764));
  assert.deepEqual(extractNumbers("en az iki yüz elli derece"), set(250));
  assert.deepEqual(extractNumbers("saatte bir buçuk milyon ton"), set(1_500_000));
  assert.deepEqual(extractNumbers("yetmiş dokuzda başladı, altmış ikideki deprem"), set(79, 62));
  assert.deepEqual(extractNumbers("yirmi dört yirmi beş Ekim"), set(24, 25));
  assert.deepEqual(extractNumbers("takvimler bin yedi yüz altmış dördü gösterdiğinde"), set(1764));
  assert.deepEqual(extractNumbers("Bir şehir vardı; binalar yıkıldı, onlar kaçtı."), set());
});

test("rakamlar", () => {
  assert.deepEqual(extractNumbers("MS 62'de deprem; 1.500 kişi; 250 °C; 1,5 milyon ton; 4-6 metre"), set(62, 1500, 250, 1_500_000, 4, 6));
});

test("kaynaksız sayılar", () => {
  const claims = "C3 (5 Şubat 62) MS 62 depremi ciddi hasar verdi. C9 En az 250 °C sıcaklık.";
  assert.deepEqual(unsupportedNumbers("Milattan sonra altmış iki yılının beş Şubat tarihinde", claims), []);
  assert.deepEqual(unsupportedNumbers("Milattan sonra altmış yılının beş Şubat tarihinde", claims), [60]);
});
