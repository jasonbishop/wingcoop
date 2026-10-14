// Headless screenshots of the viewer, for checking changes without a desktop browser.
//
// Needs Playwright with Chromium. On this project that is the container image:
//
//   podman run --rm --network host -v <dir with node_modules/playwright>:/pw -v "$PWD":/viewer:ro \
//     -v <output dir>:/shots -w /pw mcr.microsoft.com/playwright:v1.63.0-noble \
//     node /viewer/tools/shot.mjs /shots/out.png "http://localhost:5273/?log=docs/samples/coop-3p-greedy-every-decision.jsonl.gz&at=120"
//
// Arguments: <out.png> <url> [--size=1600x900] [--wait=ms] [--eval=<js run in the page before the shot>]
//            [--then=<out2.png>:<js>] (repeatable: run js, wait, take another shot)
// The page's console errors are printed. WebGL runs in software, so frames are slow; the
// script waits for the table to report ready (window.viewer.game.ready) and then --wait ms.

import { createRequire } from 'node:module';
const { chromium } = createRequire(process.cwd() + '/')('playwright');

const [out, url, ...rest] = process.argv.slice(2);
const opt = name => rest.find(a => a.startsWith(`--${name}=`))?.slice(name.length + 3);
const [w, h] = (opt('size') || '1600x900').split('x').map(Number);
const wait = Number(opt('wait') || 1500);

const browser = await chromium.launch({
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-webgl'],
});
const page = await browser.newPage({ viewport: { width: w, height: h }, colorScheme: opt('scheme') || 'light' });
page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') console.log(`[${m.type()}]`, m.text()); });
page.on('pageerror', e => console.log('[pageerror]', e.message));
await page.goto(url, { waitUntil: 'load' });
if (/[?&]log=/.test(url)) {
  await page.waitForFunction(() => window.viewer?.game, null, { timeout: 60000 });
  await page.evaluate(() => window.viewer.game.ready);
}
if (opt('eval')) console.log('eval ->', JSON.stringify(await page.evaluate(opt('eval'))));
await page.waitForTimeout(wait);
await page.screenshot({ path: out });
console.log('wrote', out);
for (const step of rest.filter(a => a.startsWith('--then='))) {
  const spec = step.slice(7), i = spec.indexOf(':');
  const res = await page.evaluate(spec.slice(i + 1));
  if (res !== undefined) console.log('then ->', JSON.stringify(res));
  await page.waitForTimeout(wait);
  const file = spec.slice(0, i).includes('/') ? spec.slice(0, i) : out.replace(/[^/]*$/, spec.slice(0, i));
  await page.screenshot({ path: file });
  console.log('wrote', file);
}
await browser.close();
