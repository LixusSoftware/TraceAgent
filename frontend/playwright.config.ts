import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "@playwright/test";

const frontendDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(frontendDir, "..");

export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  use: {
    baseURL: "http://127.0.0.1:4173",
    headless: true
  },
  webServer: [
    {
      command: "python scripts/e2e_backend.py",
      url: "http://127.0.0.1:8010/health",
      cwd: repoRoot,
      reuseExistingServer: !process.env.CI,
      timeout: 45_000
    },
    {
      command: "npm run build && npm run preview -- --host 127.0.0.1 --port 4173",
      url: "http://127.0.0.1:4173",
      cwd: frontendDir,
      reuseExistingServer: !process.env.CI,
      timeout: 45_000,
      env: {
        ...process.env,
        VITE_API_BASE_URL: "http://127.0.0.1:8010"
      }
    }
  ]
});
