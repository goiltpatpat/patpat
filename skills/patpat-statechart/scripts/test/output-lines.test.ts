import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { plainText } from "../backends/plain-text.ts";
import { readMessages } from "../frontends/messages.ts";
import { fileLines, outputLines } from "../run.ts";

const here = path.dirname(fileURLToPath(import.meta.url));
const saved = fs.readFileSync(path.join(here, "corpus", "MediaPlayer", "verdict-1.out"), "utf8");
const lf = saved.replace(/\r\n/g, "\n");
const crlf = lf.replace(/\n/g, "\r\n");
const plain = (lines: Iterable<string>) => [...plainText(readMessages(lines))].join("");

// Java on Windows prints CRLF. Cut the output at every byte so a CR lands at each chunk edge.
test("TLC output with CRLF reads like LF, however the bytes arrive", () => {
  const want = plain(outputLines([Buffer.from(lf)]));
  assert.doesNotMatch(want, /@!@!@/);
  const bytes = Buffer.from(crlf);
  for (const size of [1, 2, 3, 7, 64, bytes.length]) {
    const parts: Buffer[] = [];
    for (let i = 0; i < bytes.length; i += size) parts.push(bytes.subarray(i, i + size));
    assert.equal(plain(outputLines(parts)), want, `chunks of ${size} bytes`);
  }
});

test("a CRLF file reads like LF", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "statechart-lines-"));
  try {
    const [a, b] = ["lf.out", "crlf.out"].map((f) => path.join(dir, f));
    fs.writeFileSync(a, lf);
    fs.writeFileSync(b, crlf);
    assert.deepEqual([...fileLines(b)], [...fileLines(a)]);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
