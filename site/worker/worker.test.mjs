import assert from 'node:assert/strict';
import test from 'node:test';
import worker, { createWorker } from './index.js';

test('serves static assets without SPA fallback', async () => {
  const calls = [];
  const response = await worker.fetch(new Request('https://example.test/assets/app.js'), {
    ASSETS: {
      fetch(request) {
        calls.push(new URL(request.url).pathname);
        return Promise.resolve(new Response('missing', { status: 404 }));
      },
    },
  });

  assert.equal(response.status, 404);
  assert.deepEqual(calls, ['/assets/app.js']);
});

test('falls back document routes to the app shell', async () => {
  const calls = [];
  const response = await worker.fetch(new Request('https://example.test/roadmap'), {
    ASSETS: {
      fetch(request) {
        const pathname = new URL(request.url).pathname;
        calls.push(pathname);
        return Promise.resolve(pathname === '/index.html' ? new Response('<!doctype html>') : new Response('missing', { status: 404 }));
      },
    },
  });

  assert.equal(response.status, 200);
  assert.match(await response.text(), /doctype html/);
  assert.deepEqual(calls, ['/roadmap', '/index.html']);
});

test('serves the app shell for the root route when the asset binding does not rewrite it', async () => {
  const calls = [];
  const response = await worker.fetch(new Request('https://example.test/'), {
    ASSETS: {
      fetch(request) {
        const pathname = new URL(request.url).pathname;
        calls.push(pathname);
        return Promise.resolve(pathname === '/index.html' ? new Response('<!doctype html>') : new Response('missing', { status: 404 }));
      },
    },
  });

  assert.equal(response.status, 200);
  assert.match(await response.text(), /doctype html/);
  assert.deepEqual(calls, ['/', '/index.html']);
});

test('serves embedded build assets without relying on the runtime asset binding', async () => {
  const embeddedWorker = createWorker({
    '/index.html': { body: '<!doctype html><main>Roadmap</main>', contentType: 'text/html; charset=utf-8' },
    '/assets/app.js': { body: 'console.log("roadmap")', contentType: 'text/javascript; charset=utf-8' },
  });

  const rootResponse = await embeddedWorker.fetch(new Request('https://example.test/'), {});
  const assetResponse = await embeddedWorker.fetch(new Request('https://example.test/assets/app.js'), {});

  assert.equal(rootResponse.status, 200);
  assert.match(await rootResponse.text(), /Roadmap/);
  assert.equal(rootResponse.headers.get('content-type'), 'text/html; charset=utf-8');
  assert.equal(assetResponse.status, 200);
  assert.match(await assetResponse.text(), /roadmap/);
  assert.equal(assetResponse.headers.get('content-type'), 'text/javascript; charset=utf-8');
});
