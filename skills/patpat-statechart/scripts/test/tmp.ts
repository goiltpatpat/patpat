import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const made: string[] = [];

// node:test runs each file in its own process, so this runs once per file, after passes and failures.
process.on("exit", () => {
  for (const dir of made) {
    try {
      fs.chmodSync(dir, 0o700);
      fs.rmSync(dir, { recursive: true, force: true });
    } catch {}
  }
});

export const tempDir = (prefix: string) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  made.push(dir);
  return dir;
};
