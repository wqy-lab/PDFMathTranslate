import { spawn } from "node:child_process";

/**
 * Run a command and capture stdout/stderr. Returns { code, stdout, stderr }.
 * Runs on the DSH host (full user access), so network/memory/filesystem are
 * unrestricted — this is how the plugin bypasses any agent-sandbox limits.
 */
export function runCommand(cmd, args, { cwd, env = {} } = {}) {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, {
      cwd,
      env: { ...process.env, ...env },
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));
    child.on("error", (err) => resolve({ code: -1, stdout, stderr: String(err) }));
    child.on("close", (code) => resolve({ code, stdout, stderr }));
  });
}

/** POST JSON to the OpenViking server. Returns { status, json }. */
export async function httpPostJson(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const text = await res.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch {
    json = { error: { message: text } };
  }
  return { status: res.status, json };
}

/** Strip ANSI escape sequences (rich progress bars) from a string. */
export function stripAnsi(s) {
  // eslint-disable-next-line no-control-regex
  return String(s || "").replace(/\u001b\[[0-9;]*[A-Za-z]/g, "");
}
