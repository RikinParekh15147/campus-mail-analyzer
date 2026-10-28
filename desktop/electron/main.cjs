const { app, BrowserWindow, ipcMain, dialog, shell } = require("electron");
const { spawn } = require("node:child_process");
const { randomBytes } = require("node:crypto");
const fs = require("node:fs/promises");
const path = require("node:path");
const net = require("node:net");
const { validateRequest, safeExternal } = require("./security.cjs");
const { backendCommand, waitForBackend, stopBackend } = require("./backend_lifecycle.cjs");
let window,
  backend,
  base,
  token = null,
  backendError = "";
const bootstrap = randomBytes(32).toString("hex");
const root = path.resolve(__dirname, "../..");
async function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
  });
}
async function request(route, method = "GET", body, admin = false) {
  const response = await fetch(base + route, {
    method,
    headers: {
      ...(admin
        ? { "X-Bootstrap-Key": bootstrap }
        : token
          ? { Authorization: "Bearer " + token }
          : {}),
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const value = await response.json();
  if (!response.ok)
    throw Error(
      typeof value.detail === "string"
        ? value.detail
        : JSON.stringify(value.detail || value),
    );
  return value;
}
function guard(event) {
  if (
    !window ||
    event.sender !== window.webContents ||
    event.senderFrame !== window.webContents.mainFrame
  )
    throw Error("Untrusted desktop frame");
}
function handle(name, fn) {
  ipcMain.handle(name, async (event, ...args) => {
    guard(event);
    return fn(...args);
  });
}
async function startBackend() {
  const port = await freePort();
  base = "http://127.0.0.1:" + port;
  const command = backendCommand({
    root,
    resourcesPath: process.resourcesPath,
    platform: process.platform,
    packaged: app.isPackaged,
    override: process.env.CAMPUS_PYTHON,
  });
  const args = [
    ...command.prefixArgs,
    "serve",
    "--port",
    String(port),
    "--data-dir",
    process.env.CAMPUS_DATA_DIR || path.join(app.getPath("userData"), "data"),
  ];
  backend = spawn(command.executable, args, {
    cwd: root,
    env: { ...process.env, CAMPUS_BOOTSTRAP_KEY: bootstrap },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  backend.stderr.on("data", (chunk) => {
    backendError = (backendError + chunk.toString()).slice(-4000);
  });
  backend.on("error", (error) => {
    backendError = error.message;
  });
  try {
    await waitForBackend(backend, base + "/health");
  } catch (error) {
    if (backend && backend.exitCode === null && backend.signalCode === null) {
      try { backend.kill(); } catch {}
    }
    throw Error(
      "Python backend could not start. Run the setup instructions. " +
        error.message + " " + backendError,
    );
  }
}
app.whenReady().then(async () => {
  try {
    await startBackend();
    window = new BrowserWindow({
      width: 1440,
      height: 960,
      minWidth: 1000,
      minHeight: 700,
      backgroundColor: "#f6f7f9",
      title: "Campus Mail",
      webPreferences: {
        preload: path.join(__dirname, "preload.cjs"),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
      },
    });
    window.webContents.setWindowOpenHandler(({ url }) => {
      try {
        shell.openExternal(safeExternal(url));
      } catch {}
      return { action: "deny" };
    });
    window.webContents.on("will-navigate", (event, url) => {
      if (!url.startsWith("file://")) event.preventDefault();
    });
    window.webContents.session.setPermissionRequestHandler(
      (wc, permission, callback) => callback(false),
    );
    handle("api:request", (payload) => {
      const r = validateRequest(payload);
      return request(r.path, r.method, r.body);
    });
    handle("profiles:list", () => request("/profiles", "GET", null, true));
    handle("profiles:create", async (name) => {
      const user = await request("/profiles", "POST", { name }, true);
      token = user.token;
      const { token: secret, ...profile } = user;
      return profile;
    });
    handle("profiles:select", async (id) => {
      if (!/^[a-f0-9]{32}$/.test(id)) throw Error("Invalid profile");
      const value = await request(
        "/profiles/" + id + "/session",
        "POST",
        null,
        true,
      );
      token = value.token;
      return { id };
    });
    handle("files:json", async (kind) => {
      if (!["timetable", "holidays"].includes(kind))
        throw Error("Unsupported import");
      const choice = await dialog.showOpenDialog(window, {
        properties: ["openFile"],
        filters: [{ name: "JSON", extensions: ["json"] }],
      });
      if (choice.canceled) return null;
      const body = await fs.readFile(choice.filePaths[0], "utf8");
      if (body.length > 2_000_000) throw Error("JSON exceeds import limit");
      return JSON.parse(body);
    });
    handle("files:upload", async (parentId) => {
      const choice = await dialog.showOpenDialog(window, {
        properties: ["openFile"],
      });
      if (choice.canceled) return null;
      const file = choice.filePaths[0],
        stat = await fs.stat(file);
      if (stat.size > 20 * 1024 * 1024) throw Error("File exceeds 20 MB");
      const form = new FormData();
      form.append(
        "file",
        new Blob([await fs.readFile(file)]),
        path.basename(file),
      );
      const response = await fetch(
        base +
          "/attachments" +
          (parentId ? "?parent_id=" + encodeURIComponent(parentId) : ""),
        {
          method: "POST",
          headers: { Authorization: "Bearer " + token },
          body: form,
        },
      );
      const result = await response.json();
      if (!response.ok) throw Error(result.detail || "Upload failed");
      return result;
    });
    handle("google:connect", async (service) => {
      if (!["gmail", "calendar"].includes(service))
        throw Error("Unsupported service");
      const choice = await dialog.showOpenDialog(window, {
        title: "Choose your Google Desktop OAuth client JSON",
        properties: ["openFile"],
        filters: [{ name: "OAuth client", extensions: ["json"] }],
      });
      if (choice.canceled) return null;
      const raw = await fs.readFile(choice.filePaths[0], "utf8");
      if (raw.length > 100000) throw Error("OAuth configuration too large");
      return request(
        "/connections/" + service + "/connect",
        "POST",
        JSON.parse(raw),
      );
    });
    handle("files:download", async (id) => {
      if (!/^[a-f0-9]{32}$/.test(id)) throw Error("Invalid resource");
      const item = await request("/records/" + id + "/detail");
      const choice = await dialog.showSaveDialog(window, {
        defaultPath: path.basename(item.filename || "resource"),
      });
      if (choice.canceled) return null;
      const response = await fetch(base + "/resources/" + id + "/download", {
        headers: { Authorization: "Bearer " + token },
      });
      if (!response.ok) throw Error("Original attachment is unavailable");
      await fs.writeFile(
        choice.filePath,
        Buffer.from(await response.arrayBuffer()),
      );
      return { saved: true };
    });
    handle("summary:configure", async () => {
      const choice = await dialog.showOpenDialog(window, {
        title: "Choose summary provider JSON (endpoint, model, api_key)",
        properties: ["openFile"],
        filters: [{ name: "Provider configuration", extensions: ["json"] }],
      });
      if (choice.canceled) return null;
      const raw = await fs.readFile(choice.filePaths[0], "utf8");
      if (raw.length > 100000) throw Error("Provider configuration too large");
      return request("/summary/provider", "POST", JSON.parse(raw));
    });
    handle("links:open", (url) => shell.openExternal(safeExternal(url)));
    await window.loadFile(path.join(__dirname, "../dist/index.html"));
  } catch (error) {
    dialog.showErrorBox("Campus Mail startup", error.message);
    app.quit();
  }
});
app.on("window-all-closed", () => app.quit());
let stoppingBackend = false;
app.on("before-quit", (event) => {
  if (!backend || stoppingBackend) return;
  event.preventDefault();
  stoppingBackend = true;
  stopBackend(backend).finally(() => {
    backend = null;
    app.quit();
  });
});
