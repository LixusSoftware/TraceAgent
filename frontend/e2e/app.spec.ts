import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

const frontendDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(frontendDir, "..", "..");

test.beforeAll(() => {
  execFileSync("python", ["scripts/seed_e2e_runs.py"], {
    cwd: repoRoot,
    env: {
      ...process.env,
      VISOR_PROXY_URL: "http://127.0.0.1:8010"
    },
    stdio: "inherit"
  });
});

test("loads a run, opens compare mode and handles no-divergence compare", async ({ page }) => {
  await page.goto("/");

  await page.locator(".run-rail").getByText("Patch app.py and run tests", { exact: true }).click();
  await expect(page.getByRole("heading", { name: "Patch app.py and run tests" })).toBeVisible();
  await expect(page.getByText("Commands").first()).toBeVisible();
  await expect(page.getByText("Files").first()).toBeVisible();

  await page.getByRole("button", { name: "Comparar" }).first().click();

  await expect(page.getByText("Compare workspace")).toBeVisible();
  await page.getByLabel("Right run").selectOption({ label: "coding-agent-demo / Patch app.py and run tests (wrong file)" });
  await expect(page.getByText("First divergence")).toBeVisible();
  await expect(page.getByText("Root cause")).toBeVisible();

  await page.getByRole("button", { name: /Command diverged:/ }).click();
  await expect(page.getByText("Left evidence")).toBeVisible();
  await expect(page.getByText("Right evidence")).toBeVisible();
  await expect(page.locator(".inspector").getByText("command.succeeded").first()).toBeVisible();
  await expect(page.locator(".inspector").getByText("command.failed").first()).toBeVisible();

  await page.getByLabel("Right run").selectOption({ label: "coding-agent-demo / Patch app.py and run tests (clone)" });
  await expect(page.getByTestId("compare-divergence")).toContainText("No observable divergence between the selected runs.");
  await expect(page.getByTestId("compare-root-cause")).toContainText("no_observable_root_cause");
});
