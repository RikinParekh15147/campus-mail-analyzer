const path = require("node:path");

function backendCommand({ root, resourcesPath, platform, packaged, override }) {
  if (packaged) {
    return {
      executable: path.join(
        resourcesPath,
        "backend",
        platform === "win32" ? "campusmail-backend.exe" : "campusmail-backend",
      ),
      prefixArgs: [],
    };
  }
  return {
    executable:
      override ||
      path.join(
        root,
        platform === "win32"
          ? ".venv-win/Scripts/python.exe"
          : ".venv/bin/python",
      ),
    prefixArgs: ["-m", "campusmail"],
  };
}

async function waitForBackend(child, url, options = {}) {
  const probe = options.probe || fetch;
  const pause = options.pause || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  const attempts = options.attempts ?? 150;
  const intervalMs = options.intervalMs ?? 200;
  let spawnError = null;
  const onError = (error) => {
    spawnError = error;
  };
  child.on("error", onError);
  try {
    for (let attempt = 0; attempt < attempts; attempt++) {
      if (spawnError) throw Error(`Backend spawn failed: ${spawnError.message}`);
      if (child.exitCode !== null || child.signalCode !== null)
        throw Error(`Backend exited before health check (${child.exitCode ?? child.signalCode})`);
      try {
        const response = await probe(url, { signal: AbortSignal.timeout(1000) });
        if (spawnError) throw Error(`Backend spawn failed: ${spawnError.message}`);
        if (response.ok) {
          const health = await response.json();
          if (health.status === "ok" && health.version === "0.1.0") return;
        }
      } catch (error) {
        if (spawnError) throw Error(`Backend spawn failed: ${spawnError.message}`);
      }
      await pause(intervalMs);
    }
    throw Error(`Backend health check timed out after ${attempts * intervalMs} ms`);
  } finally {
    child.removeListener("error", onError);
  }
}

async function stopBackend(child, timeoutMs = 5000) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return "already_stopped";
  return new Promise((resolve) => {
    let finished = false;
    let timer;
    const finish = (status) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      child.removeListener("exit", onExit);
      resolve(status);
    };
    const onExit = () => finish("stopped");
    child.once("exit", onExit);
    timer = setTimeout(() => {
      try { child.kill("SIGKILL"); } catch {}
      finish("forced");
    }, timeoutMs);
    try {
      if (!child.kill()) finish("already_stopped");
    } catch {
      finish("already_stopped");
    }
  });
}

module.exports = { backendCommand, waitForBackend, stopBackend };
