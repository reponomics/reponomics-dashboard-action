#!/usr/bin/env node
import http from 'node:http';
import { delimiter, extname, join, resolve } from 'node:path';
import { existsSync } from 'node:fs';
import { mkdir, readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';

const ROOT = resolve(new URL('..', import.meta.url).pathname);
const DEFAULT_DASHBOARD_DIR = join(ROOT, 'dist/demo/docs');
const DEFAULT_OUTPUT_DIR = join(ROOT, 'docs/promotional/dashboard-guide/assets');
const DEFAULT_KEY = 'reponomics-demo-public-key-2026-keep-this-visible-do-not-reuse';

const ASSETS = [
  { name: 'full-page.png', fullPage: true },
  { name: 'top-dashboard.png', selector: '#dashboard-app > .hero' },
  { name: 'next-moves.png', selector: '.story-board' },
  { name: 'relationship-visuals.png', selector: '#opportunity-card' },
  { name: 'code-event-graph.png', selector: '#event-graph-card', optional: true },
  { name: 'readiness-queue.png', selector: '#readiness-card' },
  { name: 'repo-selection.png', selector: '#repo-strip-card' },
  { name: 'tables.png', selector: '#repo-section' },
];

function usage() {
  return `Usage: node scripts/capture_dashboard_guide_assets.mjs [options]

Captures the dashboard guide screenshot assets from a rendered dashboard.

Options:
  --url <url>                 Capture an already served dashboard URL.
  --dashboard-dir <path>      Serve this dashboard directory when --url is omitted.
                              Defaults to dist/demo/docs.
  --out-dir <path>            Screenshot output directory.
                              Defaults to docs/promotional/dashboard-guide/assets.
  --key <value>               Demo unlock key. Defaults to the public demo key.
  --chrome-executable <path>  Browser executable for Playwright Chromium.
                              Also read from CHROME_EXECUTABLE.
  --host <host>               Local static server host. Defaults to 127.0.0.1.
  --port <port>               Local static server port. Defaults to an ephemeral port.
`;
}

function argValue(args, name) {
  const idx = args.indexOf(name);
  if (idx === -1) return null;
  const value = args[idx + 1];
  if (!value || value.startsWith('--')) {
    throw new Error(`${name} requires a value.`);
  }
  return value;
}

function contentType(path) {
  return {
    '.css': 'text/css; charset=utf-8',
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.svg': 'image/svg+xml',
    '.woff2': 'font/woff2',
  }[extname(path)] || 'application/octet-stream';
}

async function startServer(root, host, port) {
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url || '/', `http://${host}`);
      const pathname = decodeURIComponent(url.pathname);
      const relative = pathname === '/' ? 'index.html' : pathname.replace(/^\/+/, '');
      const file = resolve(root, relative);
      if (!file.startsWith(resolve(root))) {
        res.writeHead(403);
        res.end('Forbidden');
        return;
      }
      const body = await readFile(file);
      res.writeHead(200, { 'content-type': contentType(file) });
      res.end(body);
    } catch (_error) {
      res.writeHead(404);
      res.end('Not found');
    }
  });

  await new Promise((resolveListen) => server.listen(Number(port || 0), host, resolveListen));
  const address = server.address();
  const actualPort = typeof address === 'object' && address ? address.port : port;
  return {
    server,
    url: `http://${host}:${actualPort}/`,
  };
}

function defaultChromeExecutable() {
  if (process.env.CHROME_EXECUTABLE) return process.env.CHROME_EXECUTABLE;
  if (process.platform === 'darwin') {
    return '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  }
  return null;
}

async function loadPlaywright() {
  const require = createRequire(import.meta.url);
  try {
    return require('playwright');
  } catch (error) {
    for (const pathEntry of (process.env.PATH || '').split(delimiter)) {
      const normalizedPathEntry = pathEntry.replaceAll('\\', '/');
      if (!normalizedPathEntry.endsWith('/node_modules/.bin')) continue;
      const candidate = resolve(pathEntry, '..', 'playwright', 'package.json');
      if (!existsSync(candidate)) continue;
      return createRequire(candidate)('playwright');
    }
    throw new Error(
      'Missing Playwright. Run with npx, install it in your Node environment, or expose it with NODE_PATH. Original error: ' +
        error.message,
    );
  }
}

async function unlockDashboard(page, key) {
  const input = page.locator('#dashboard-key');
  const button = page.locator('#demo-unlock-button');
  if (await button.count()) {
    await button.click();
  } else if (await input.count()) {
    await input.fill(key);
    await page.locator('#unlock-button, button[type="submit"]').first().click();
  }
  await page.waitForSelector('#dashboard-app:not(.dashboard-hidden)', { timeout: 15000 });
  await page.waitForSelector('.lead-story-slide h3, #insights-list .insight-item', { timeout: 15000 });
  await page.waitForTimeout(1800);
}

async function captureAsset(page, asset, outDir) {
  const path = join(outDir, asset.name);
  if (asset.fullPage) {
    await page.screenshot({ path, fullPage: true });
    return 'captured';
  }
  const locator = page.locator(asset.selector).first();
  try {
    await locator.waitFor({ state: 'visible', timeout: 15000 });
  } catch (error) {
    if (asset.optional && existsSync(path)) {
      console.log(`Skipped ${asset.name}; selector ${asset.selector} is hidden in this render.`);
      return 'skipped';
    }
    throw error;
  }
  await locator.scrollIntoViewIfNeeded();
  await page.waitForTimeout(250);
  await locator.screenshot({ path });
  return 'captured';
}

async function main() {
  const args = process.argv.slice(2);
  if (args.includes('--help') || args.includes('-h')) {
    console.log(usage());
    return;
  }

  const host = argValue(args, '--host') || '127.0.0.1';
  const port = argValue(args, '--port') || '0';
  const dashboardDir = resolve(argValue(args, '--dashboard-dir') || DEFAULT_DASHBOARD_DIR);
  const outDir = resolve(argValue(args, '--out-dir') || DEFAULT_OUTPUT_DIR);
  const key = argValue(args, '--key') || DEFAULT_KEY;
  const chromeExecutable = argValue(args, '--chrome-executable') || defaultChromeExecutable();
  let url = argValue(args, '--url');
  let server = null;

  await mkdir(outDir, { recursive: true });

  if (!url) {
    const started = await startServer(dashboardDir, host, port);
    server = started.server;
    url = started.url;
  }

  const { chromium } = await loadPlaywright();
  const launchOptions = chromeExecutable ? { executablePath: chromeExecutable } : {};
  const browser = await chromium.launch({ headless: true, ...launchOptions });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    await page.goto(url, { waitUntil: 'networkidle' });
    await unlockDashboard(page, key);
    for (const asset of ASSETS) {
      const result = await captureAsset(page, asset, outDir);
      if (result === 'captured') console.log(`Captured ${asset.name}`);
    }
  } finally {
    await browser.close();
    if (server) {
      await new Promise((resolveClose) => server.close(resolveClose));
    }
  }
}

main().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
