const { test } = require("node:test");
const assert = require("node:assert/strict");
const { validateRequest, safeExternal } = require("../electron/security.cjs");
test("bridge refuses absolute URLs and traversal", () => {
  assert.throws(() =>
    validateRequest({ path: "https://attacker.test", method: "GET" }),
  );
  assert.throws(() => validateRequest({ path: "/../profiles", method: "GET" }));
  assert.throws(() => validateRequest({ path: "/profiles", method: "POST" }));
  assert.throws(() =>
    validateRequest({ path: "/resources/%2e%2e/download", method: "GET" }),
  );
});
test("bridge accepts application requests and safe browser links", () => {
  assert.equal(
    validateRequest({ path: "/records/assignment", method: "GET" }).path,
    "/records/assignment",
  );
  assert.equal(
    safeExternal("https://meet.google.com/abc"),
    "https://meet.google.com/abc",
  );
  assert.throws(() => safeExternal("javascript:alert(1)"));
  assert.throws(() => safeExternal("file:///etc/passwd"));
});
