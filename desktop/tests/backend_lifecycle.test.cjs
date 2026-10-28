const { test } = require("node:test");
const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const path = require("node:path");
const { backendCommand, waitForBackend, stopBackend } = require("../electron/backend_lifecycle.cjs");

test("backend command selects platform environment and packaged binary", () => {
  const root = path.resolve("/project");
  const mac = backendCommand({ root, platform: "darwin", packaged: false });
  const win = backendCommand({ root, platform: "win32", packaged: false });
  const packageWin = backendCommand({ resourcesPath: root, platform: "win32", packaged: true });
  assert.equal(mac.executable, path.join(root, ".venv/bin/python"));
  assert.equal(win.executable, path.join(root, ".venv-win/Scripts/python.exe"));
  assert.equal(packageWin.executable, path.join(root, "backend/campusmail-backend.exe"));
  assert.deepEqual(win.prefixArgs, ["-m", "campusmail"]);
  assert.deepEqual(packageWin.prefixArgs, []);
});

test("health wait exits immediately on spawn failure and process exit", async () => {
  const child = new EventEmitter();
  child.exitCode = null;
  child.signalCode = null;
  let probes = 0;
  await assert.rejects(
    waitForBackend(child, "http://127.0.0.1/health", {
      attempts: 150,
      probe: async () => { probes++; child.emit("error", Error("ENOENT")); throw Error("offline"); },
      pause: async () => {},
    }),
    /Backend spawn failed: ENOENT/,
  );
  assert.equal(probes, 1);
  assert.equal(child.listenerCount("error"), 0);
  child.exitCode = 7;
  await assert.rejects(
    waitForBackend(child, "http://127.0.0.1/health", { probe: async () => { throw Error("should not probe"); } }),
    /Backend exited before health check \(7\)/,
  );
});

test("health wait succeeds after transient refusal and times out clearly", async () => {
  const child = new EventEmitter();
  child.exitCode = null;
  child.signalCode = null;
  let probes = 0;
  await waitForBackend(child, "http://127.0.0.1/health", {
    attempts: 3, pause: async () => {},
    probe: async () => ({ ok: ++probes === 2,
      json: async () => ({ status: "ok", version: "0.1.0" }) }),
  });
  assert.equal(probes, 2);
  await assert.rejects(
    waitForBackend(child, "http://127.0.0.1/health", {
      attempts: 2, intervalMs: 1, pause: async () => {},
      probe: async () => ({ ok: false }),
    }),
    /timed out after 2 ms/,
  );
});

test("shutdown waits for child exit and can force a stalled child", async () => {
  const child = new EventEmitter();
  child.exitCode = null;
  child.signalCode = null;
  child.kill = (signal) => {
    assert.equal(signal, undefined);
    queueMicrotask(() => child.emit("exit", 0));
    return true;
  };
  assert.equal(await stopBackend(child, 100), "stopped");
  assert.equal(child.listenerCount("exit"), 0);

  const stalled = new EventEmitter();
  stalled.exitCode = null;
  stalled.signalCode = null;
  const signals = [];
  stalled.kill = (signal) => { signals.push(signal || "SIGTERM"); return true; };
  assert.equal(await stopBackend(stalled, 1), "forced");
  assert.deepEqual(signals, ["SIGTERM", "SIGKILL"]);
});
