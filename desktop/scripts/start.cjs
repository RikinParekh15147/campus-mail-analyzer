const { spawn } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");
const root = path.resolve(__dirname, "../..");
const env = {
  ...process.env,
  CAMPUS_DATA_DIR: process.env.CAMPUS_DATA_DIR || path.join(root, "runtime"),
};
const libs = path.join(
  root,
  "runtime/linux-deps/root/usr/lib/x86_64-linux-gnu",
);
if (process.platform === "linux" && fs.existsSync(libs))
  env.LD_LIBRARY_PATH =
    libs + (env.LD_LIBRARY_PATH ? ":" + env.LD_LIBRARY_PATH : "");
const child = spawn(require("electron"), [path.join(root, "desktop")], {
  stdio: "inherit",
  env,
});
child.on("error", (error) => {
  console.error(error.message);
  process.exitCode = 1;
});
child.on("exit", (code) => {
  process.exitCode = code || 0;
});
for (const signal of ["SIGINT", "SIGTERM"])
  process.on(signal, () => child.kill(signal));
