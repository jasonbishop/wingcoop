// Plays whole games through the animation code in a headless browser, as fast as it will
// go, and reports page errors and every event whose animation ended somewhere other than
// where the state says (the table is corrected either way; this finds the corrections).
//
//   podman run … node /viewer/tools/playthrough.mjs http://localhost:5273 <log path> [<log path> …]
//
// See tools/shot.mjs for the container command. Log paths are as the viewer lists them.

import { createRequire } from 'node:module';
const { chromium } = createRequire(process.cwd() + '/')('playwright');

const [base, ...logs] = process.argv.slice(2);
const browser = await chromium.launch({
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-webgl'],
});
let bad = 0;
for (const log of logs) {
  const page = await browser.newPage({ viewport: { width: 900, height: 600 } });
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push(e.stack || e.message));
  await page.goto(`${base}/?quality=low&log=${encodeURIComponent(log)}`, { waitUntil: 'load' });
  await page.waitForFunction(() => window.viewer?.game, null, { timeout: 60000 });
  const result = await page.evaluate(async () => {
    const { player } = window.viewer;
    player.checks = [];
    player.follow = 'turn';
    const t0 = performance.now();
    while (player.index < player.last) {
      const p = player.step();
      await player.skip();
      await p;
    }
    // Known gap in the log format (FORMAT-REQUESTS.md, R1): bonus cards leave the bonus deck
    // with no event, so in a per-turn log the pile only catches up when one is kept.
    const known = c => c.event === 'bonus_kept' && Object.keys(JSON.parse(c.before)).every(k => k === 'bonusDeck' || k === 'bonusDiscard' || JSON.parse(c.before)[k] === undefined || JSON.stringify(JSON.parse(c.before)[k]) === JSON.stringify(JSON.parse(c.after)[k]));
    const checks = player.checks.filter(c => !known(c));
    const kinds = {};
    for (const c of checks) kinds[c.event] = (kinds[c.event] || 0) + 1;
    return { steps: player.last, ms: Math.round(performance.now() - t0), corrections: kinds, first: checks.slice(0, 3) };
  });
  const corrected = Object.keys(result.corrections).length;
  if (errors.length || corrected) bad++;
  console.log(`${errors.length || corrected ? 'FAIL' : 'ok  '} ${log}: ${result.steps} steps in ${result.ms} ms`);
  if (corrected) console.log('   corrections by event:', JSON.stringify(result.corrections));
  for (const c of result.first) {
    const a = JSON.parse(c.before), b = JSON.parse(c.after);
    const diff = Object.keys(a).filter(k => JSON.stringify(a[k]) !== JSON.stringify(b[k]));
    console.log(`   position ${c.index} ${c.event}: differs in ${diff.join(', ')}`);
    for (const k of diff.slice(0, 2)) console.log(`     ${k}: ${JSON.stringify(a[k]).slice(0, 300)}\n     -> ${JSON.stringify(b[k]).slice(0, 300)}`);
  }
  for (const e of [...new Set(errors)].slice(0, 5)) console.log('   error:', e.slice(0, 600));
  await page.close();
}
await browser.close();
process.exit(bad ? 1 : 0);
