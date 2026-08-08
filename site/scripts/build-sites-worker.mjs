import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import { extname, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const siteRoot = fileURLToPath(new URL('..', import.meta.url));
const distRoot = resolve(siteRoot, 'dist');
const serverRoot = resolve(distRoot, 'server');
const workerSource = resolve(siteRoot, 'worker', 'index.js');
const workerOutput = resolve(serverRoot, 'index.js');

await mkdir(serverRoot, { recursive: true });

const contentTypes = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
};

async function collectStaticFiles(directory) {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.name === 'server' || entry.name === '.openai') {
      continue;
    }
    const absolute = resolve(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...await collectStaticFiles(absolute));
    } else if (entry.isFile()) {
      files.push(absolute);
    }
  }
  return files;
}

const staticAssets = {};
for (const absolute of (await collectStaticFiles(distRoot)).sort()) {
  const relativePath = relative(distRoot, absolute).split(sep).join('/');
  staticAssets[`/${relativePath}`] = {
    body: await readFile(absolute, 'utf8'),
    contentType: contentTypes[extname(relativePath)] ?? 'application/octet-stream',
    cacheControl: relativePath.startsWith('assets/') ? 'public, max-age=31536000, immutable' : 'no-cache',
  };
}

const workerTemplate = await readFile(workerSource, 'utf8');
const sentinel = 'const STATIC_ASSETS = null;';
if (!workerTemplate.includes(sentinel)) {
  throw new Error('Sites worker template is missing its static asset sentinel.');
}
const bundledWorker = workerTemplate.replace(
  sentinel,
  `const STATIC_ASSETS = ${JSON.stringify(staticAssets)};`,
);
await writeFile(workerOutput, bundledWorker, 'utf8');

console.log(`Sites worker emitted: ${workerOutput}`);
