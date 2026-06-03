const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1400, height: 860 });
  try {
    await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 15000 });
  } catch {
    await page.goto('http://localhost:3001', { waitUntil: 'networkidle', timeout: 15000 });
  }
  await page.waitForTimeout(2500);
  await page.screenshot({ path: 'screenshot-main.png' });
  console.log('done');
  await browser.close();
})();
