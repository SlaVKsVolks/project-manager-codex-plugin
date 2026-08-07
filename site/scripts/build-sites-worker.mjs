import { copyFile, mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const siteRoot = fileURLToPath(new URL('..', import.meta.url));
const distRoot = resolve(siteRoot, 'dist');
const serverRoot = resolve(distRoot, 'server');
const workerSource = resolve(siteRoot, 'worker', 'index.js');
const workerOutput = resolve(serverRoot, 'index.js');

await mkdir(serverRoot, { recursive: true });
await copyFile(workerSource, workerOutput);

console.log(`Sites worker emitted: ${workerOutput}`);
