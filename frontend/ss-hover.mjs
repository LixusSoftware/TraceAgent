import { chromium } from 'playwright';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });

await page.goto('http://localhost:5173/');
await page.waitForTimeout(2000);
await page.locator('button:has-text("Dashboard")').click();
await page.waitForTimeout(1500);

// Hover over the AreaChart
await page.locator('.recharts-wrapper').first().hover();
await page.waitForTimeout(500);
await page.screenshot({ path: 'ss-hover-chart.png' });

// Hover over the BarChart
await page.locator('.recharts-wrapper').nth(2).hover();
await page.waitForTimeout(500);
await page.screenshot({ path: 'ss-hover-bar.png' });

await browser.close();
