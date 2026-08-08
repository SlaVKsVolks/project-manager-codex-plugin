const STATIC_ASSETS = null;

function documentRequest(url) {
  return !url.pathname.startsWith('/assets/') && !/\.[^/]+$/.test(url.pathname);
}

function rootRequest(request) {
  const url = new URL(request.url);
  url.pathname = '/index.html';
  url.search = '';
  return new Request(url, request);
}

function embeddedAssetResponse(staticAssets, pathname, method) {
  const asset = staticAssets?.[pathname];
  if (!asset) {
    return null;
  }
  return new Response(method === 'HEAD' ? null : asset.body, {
    headers: {
      'cache-control': asset.cacheControl ?? 'no-cache',
      'content-type': asset.contentType,
    },
  });
}

export function createWorker(staticAssets = STATIC_ASSETS) {
  return {
    async fetch(request, env) {
      const url = new URL(request.url);

      if (staticAssets) {
        const exact = embeddedAssetResponse(staticAssets, url.pathname, request.method);
        if (exact) {
          return exact;
        }
        if (documentRequest(url)) {
          return embeddedAssetResponse(staticAssets, '/index.html', request.method)
            ?? new Response('App shell unavailable.', { status: 500 });
        }
        return new Response('Not found.', { status: 404 });
      }

      if (!env?.ASSETS?.fetch) {
        return new Response('Static asset binding unavailable.', { status: 500 });
      }

      const response = await env.ASSETS.fetch(request);

      if (response.status !== 404 || !documentRequest(url)) {
        return response;
      }

      return env.ASSETS.fetch(rootRequest(request));
    },
  };
}

const worker = createWorker();
export default worker;
