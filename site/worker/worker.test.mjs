import assert from 'node:assert/strict';
import test from 'node:test';
import worker from './index.js';

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
        return Promise.resolve(pathname === '/' ? new Response('<!doctype html>') : new Response('missing', { status: 404 }));
      },
    },
  });

  assert.equal(response.status, 200);
  assert.match(await response.text(), /doctype html/);
  assert.deepEqual(calls, ['/roadmap', '/']);
});
