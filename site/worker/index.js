function documentRequest(url) {
  return !url.pathname.startsWith('/assets/') && !/\.[^/]+$/.test(url.pathname);
}

function rootRequest(request) {
  const url = new URL(request.url);
  url.pathname = '/index.html';
  url.search = '';
  return new Request(url, request);
}

const worker = {
  async fetch(request, env) {
    if (!env?.ASSETS?.fetch) {
      return new Response('Static asset binding unavailable.', { status: 500 });
    }

    const response = await env.ASSETS.fetch(request);
    const url = new URL(request.url);

    if (response.status !== 404 || !documentRequest(url)) {
      return response;
    }

    return env.ASSETS.fetch(rootRequest(request));
  },
};

export default worker;
