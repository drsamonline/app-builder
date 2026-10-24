#!/usr/bin/env node
/**
 * shot.js — screenshot a deployed demo, and put it in the README.
 *
 * A landing page and a README both READ better with the app in them, and neither
 * had one. This captures the LIVE demo (so the picture can never show an older
 * build than the one you can download) and inserts it into the README between
 * markers, so a re-run replaces the image instead of stacking another one.
 *
 *   node tools/shot.js --url <demo-url> --out docs/shot.png --readme README.md
 *
 * It never fails the pipeline for a missing screenshot: a broken picture must not
 * block a release. It says so and exits 0.
 */
'use strict';
const fs = require('fs');
const path = require('path');

function arg(name, dflt) {
  const i = process.argv.indexOf('--' + name);
  return i > -1 && process.argv[i + 1] ? process.argv[i + 1] : dflt;
}

(async () => {
  const url = arg('url', '');
  const out = arg('out', 'docs/shot.png');
  const readme = arg('readme', 'README.md');
  const wait = parseInt(arg('wait', '3500'), 10);
  if (!url) { console.log('no --url: nothing to screenshot'); process.exit(0); }

  let puppeteer;
  try {
    puppeteer = require('puppeteer');
  } catch (e) {
    console.log('puppeteer is not installed - skipping the screenshot (not a failure)');
    process.exit(0);
  }

  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage']
  });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1200, height: 900, deviceScaleFactor: 1 });
    await page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
    await new Promise((r) => setTimeout(r, wait));
    fs.mkdirSync(path.dirname(out), { recursive: true });
    await page.screenshot({ path: out });
    console.log('wrote ' + out + ' from ' + url);
  } catch (e) {
    console.log('could not screenshot ' + url + ': ' + e.message + ' (not a failure)');
    process.exit(0);
  } finally {
    await browser.close();
  }

  // and into the README, between markers so a re-run replaces rather than appends
  try {
    let md = fs.existsSync(readme) ? fs.readFileSync(readme, 'utf8') : '';
    const rel = path.relative(path.dirname(readme) || '.', out).split(path.sep).join('/');
    const block = '<!-- shot:start -->\n\n![Screenshot](' + rel + ')\n\n<!-- shot:end -->';
    if (md.includes('<!-- shot:start -->')) {
      md = md.replace(/<!-- shot:start -->[\s\S]*?<!-- shot:end -->/, block);
    } else {
      const lines = md.split('\n');
      let at = lines.findIndex((l) => l.startsWith('# '));
      at = at === -1 ? 0 : at + 1;
      md = lines.slice(0, at).join('\n') + '\n\n' + block + '\n' + lines.slice(at).join('\n');
    }
    fs.writeFileSync(readme, md);
    console.log('screenshot inserted into ' + readme);
  } catch (e) {
    console.log('could not update the README: ' + e.message);
  }
})();
