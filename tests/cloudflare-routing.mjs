import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const api = await readFile(new URL('../site/admin-api.js', import.meta.url), 'utf8');
const code = (await readFile(new URL('../site/_worker.js', import.meta.url), 'utf8'))
  .replace('"./admin-api.js"', JSON.stringify(`data:text/javascript;base64,${Buffer.from(api).toString('base64')}`));
const { default: worker } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const calls = [];
const env = { ASSETS: { fetch: async request => {
  calls.push(request);
  const path = new URL(request.url).pathname;
  if (path === '/source.json') return new Response(request.method === 'HEAD' ? null : '{"apps":[]}', {
    headers: { 'Content-Type': 'application/octet-stream' },
  });
  if (path === '/admin/') return new Response('<html>Admin</html>');
  return new Response('Not found', { status: 404 });
} } };
const request = (path, method = 'GET') => new Request(`https://altsource.zynthec.com${path}`, { method });

let response = await worker.fetch(request('/'), env);
assert.equal(response.status, 200);
assert.equal(response.headers.get('content-type'), 'application/json; charset=utf-8');
assert.equal(response.headers.get('access-control-allow-origin'), '*');
assert.deepEqual(await response.json(), { apps: [] });
assert.equal(new URL(calls.at(-1).url).pathname, '/source.json');

response = await worker.fetch(request('/', 'HEAD'), env);
assert.equal(await response.text(), '');
response = await worker.fetch(request('/', 'OPTIONS'), env);
assert.equal(response.status, 204);
assert.equal(response.headers.get('access-control-allow-origin'), '*');
response = await worker.fetch(request('/', 'POST'), env);
assert.equal(response.status, 405);
response = await worker.fetch(request('/source.json?test=1'), env);
assert.equal(response.status, 308);
assert.equal(response.headers.get('location'), 'https://altsource.zynthec.com/?test=1');
response = await worker.fetch(request('/admin/'), env);
assert.equal(await response.text(), '<html>Admin</html>');
response = await worker.fetch(request('/missing'), env);
assert.equal(response.status, 404);
console.log('Cloudflare routing: root JSON, HEAD, CORS, redirect and static admin passed.');
