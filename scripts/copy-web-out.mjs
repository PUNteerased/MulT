/**
 * Copy Next.js static export to repo-root /out for Vercel
 * (Root Directory = ./  +  Output Directory = out).
 */
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "dashboard", "web", "out");
const dest = join(root, "out");

if (!existsSync(src)) {
  console.error(`[copy-web-out] Missing build output: ${src}`);
  process.exit(1);
}

rmSync(dest, { recursive: true, force: true });
mkdirSync(dest, { recursive: true });
cpSync(src, dest, { recursive: true });
console.log(`[copy-web-out] Copied ${src} -> ${dest}`);
