import { test } from "node:test";
import assert from "node:assert/strict";
import { allowed, classify } from "./licenses.ts";

test("lisans sınıfları (licenses.py ile aynı örnekler)", () => {
  assert.equal(classify("Public domain"), "pd");
  assert.equal(classify("CC0", "https://creativecommons.org/publicdomain/zero/1.0/"), "cc0");
  assert.equal(classify("CC BY 2.0"), "by");
  assert.equal(classify("CC BY-SA 4.0"), "by-sa");
  assert.equal(classify("CC BY-NC 2.0"), "nc");
  assert.equal(classify("CC BY-NC-ND 4.0"), "nd");
  assert.equal(classify(""), "unknown");
  assert.equal(classify("All rights reserved"), "unknown");
});

test("politika", () => {
  assert.ok(allowed("pd") && allowed("by") && allowed("own"));
  assert.ok(allowed("by-sa") && !allowed("by-sa", false, false));
  assert.ok(!allowed("nc") && allowed("nc", true));
  assert.ok(!allowed("nd", true) && !allowed("unknown", true));
  assert.ok(allowed("nd", false, true, true) && allowed("unknown", false, true, true));   // taslak modu
});
