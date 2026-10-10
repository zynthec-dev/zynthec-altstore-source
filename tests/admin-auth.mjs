import assert from 'node:assert/strict';
import { readFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';

const code = await readFile(new URL('../site/admin-api.js', import.meta.url), 'utf8');
const { adminAPI } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const folder = await mkdtemp(join(tmpdir(), 'source-admin-auth-'));
const database = join(folder, 'admin.sqlite');
// Use real SQLite to exercise D1 SQL without adding runtime/test dependencies.
const python = `import json,sqlite3,sys
db=sqlite3.connect(sys.argv[1]); db.row_factory=sqlite3.Row
queries=json.load(sys.stdin); result=[]
with db:
 for q in queries:
  before=db.total_changes; cursor=db.execute(q['sql'],q.get('params',[]))
  rows=[dict(r) for r in cursor.fetchall()] if cursor.description else []
  result.append({'results':rows,'meta':{'changes':db.total_changes-before}})
print(json.dumps(result))`;
const execute = statements => JSON.parse(execFileSync('python3', ['-c', python, database], {
  input: JSON.stringify(statements.map(s=>({sql:s.sql,params:s.params}))), encoding: 'utf8',
}));
class Statement {
  constructor(sql) { this.sql=sql; this.params=[]; }
  bind(...params) { this.params=params; return this; }
  async first() { return execute([this])[0].results[0] || null; }
  async run() { return execute([this])[0]; }
}
const db = { prepare: sql => new Statement(sql), batch: async statements => execute(statements) };
const env = { ADMIN_DB: db, ADMIN_ENCRYPTION_KEY: 'ab'.repeat(32) };
const origin = 'https://zloader.zynthec.com';
const request = (route, body, sessionCookie, headers={}) => new Request(`${origin}/admin/api/${route}`, {
  method:body===undefined?'GET':'POST',
  headers:{'Content-Type':'application/json','X-Admin-Request':'1', Origin:origin,
    ...(sessionCookie?{Cookie:sessionCookie}:{}), ...headers},
  ...(body===undefined?{}:{body:JSON.stringify(body)}),
});
const call = (route, body, cookie, headers) => adminAPI(request(route,body,cookie,headers),env);
const password = 'test-only-password-123';
const token = 'test-only-not-a-real-token';
const originalFetch=globalThis.fetch;
let owner='zynthec-dev'; let upstreamCalls=0;
globalThis.fetch=async (url, options) => {
  upstreamCalls++;
  assert.equal(options.headers.Authorization, `Bearer ${token}`);
  if(url.endsWith('/user')) return Response.json({login:owner});
  if(url.endsWith('/zynthec-altstore-source')) return Response.json({permissions:{push:true}});
  return Response.json({content:'test-content'});
};
try {
  const schema = await readFile(new URL('../migrations/0001_admin.sql', import.meta.url),'utf8');
  execute(schema.split(';').filter(s=>s.trim()).map(sql=>({sql,params:[]})));
  assert.equal((await adminAPI(request('status'),{})).status,503);
  assert.deepEqual(await (await call('status')).json(),{initialized:false,authenticated:false,connected:false});
  assert.equal((await call('github/contents/catalog/content.json')).status,401);
  assert.equal((await call('setup',{password,token},null,{Origin:'https://evil.example'})).status,403);
  owner='someone-else';
  assert.equal((await call('setup',{password,token})).status,403);
  owner='zynthec-dev';
  let response=await call('setup',{password,token});
  assert.equal(response.status,200);
  const cookie=response.headers.get('set-cookie').split(';')[0];
  assert.match(response.headers.get('set-cookie'),/Secure; HttpOnly; SameSite=Strict/);
  assert.doesNotMatch(await response.text(),/test-only|github_token|password_hash/);
  const config=await db.prepare('SELECT * FROM admin_config').first();
  assert.notEqual(config.github_token,token);
  assert.notEqual(config.password_hash,password);
  assert.equal((await call('setup',{password,token})).status,409);
  assert.equal((await call('login',{password:'wrong-password'})).status,401);
  response=await call('login',{password});
  assert.equal(response.status,200);
  const secondCookie=response.headers.get('set-cookie').split(';')[0];
  assert.equal((await (await call('status',undefined,cookie)).json()).authenticated,true);
  assert.equal((await call('github/contents/catalog/content.json',undefined,cookie)).status,200);
  const callsBefore=upstreamCalls;
  assert.equal((await call('github/contents/.github/workflows/deploy.yml',{},cookie)).status,403);
  assert.equal(upstreamCalls,callsBefore);
  assert.equal((await call('password',{currentPassword:'wrong',password:'new-test-password-123'},cookie)).status,401);
  response=await call('password',{currentPassword:password,password:'new-test-password-123'},cookie);
  assert.equal(response.status,200);
  const newCookie=response.headers.get('set-cookie').split(';')[0];
  assert.equal((await (await call('status',undefined,cookie)).json()).authenticated,false);
  assert.equal((await (await call('status',undefined,secondCookie)).json()).authenticated,false);
  assert.equal((await (await call('status',undefined,newCookie)).json()).authenticated,true);
  await db.prepare('DELETE FROM admin_attempts').run();
  assert.equal((await call('login',{password})).status,401);
  assert.equal((await call('login',{password:'new-test-password-123'})).status,200);
  assert.equal((await call('logout',{},newCookie)).status,200);
  assert.equal((await (await call('status',undefined,newCookie)).json()).authenticated,false);
  await db.prepare('DELETE FROM admin_attempts').run();
  for(let i=0;i<8;i++) assert.equal((await call('login',{password:'incorrect'})).status,401);
  assert.equal((await call('login',{password:'incorrect'})).status,429);
  // Provisioned temporary password: authentication works before token setup;
  // only that authenticated user can establish the one-time GitHub connection.
  await db.prepare('DELETE FROM admin_attempts').run();
  await db.prepare("UPDATE admin_config SET github_token='' WHERE id=1").run();
  assert.equal((await call('connection',{token})).status,401);
  response=await call('login',{password:'new-test-password-123'});
  const pendingCookie=response.headers.get('set-cookie').split(';')[0];
  assert.equal((await (await call('status',undefined,pendingCookie)).json()).connected,false);
  assert.equal((await call('github/contents/catalog/content.json',undefined,pendingCookie)).status,409);
  assert.equal((await call('connection',{token},pendingCookie)).status,200);
  assert.equal((await (await call('status',undefined,pendingCookie)).json()).connected,true);
  assert.equal((await call('connection',{token},pendingCookie)).status,409);
  console.log('PASS: password setup, owner verification, encryption, login, cookies, proxy restriction, CSRF, password change, session revocation, logout and throttling.');
} finally {
  globalThis.fetch=originalFetch;
  await rm(folder,{recursive:true,force:true});
}
