import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';

const manifest = JSON.parse(await readFile(new URL('../../results/098000/media_manifest.json', import.meta.url)));
const mediaObjects = Object.fromEntries(manifest.videos.map(video => [video.key, {size:video.size_bytes,sha256:video.sha256}]));
const mediaKey = manifest.videos[0].key;
const uploadSha256 = createHash('sha256').update('abcd').digest('hex');
// Tiny upload fixture; route names still come from the actual release manifest.
mediaObjects[mediaKey] = {size:4,sha256:uploadSha256};
const template = await readFile(new URL('./worker.mjs', import.meta.url), 'utf8');
const marker = '/*__MEDIA_OBJECTS__*/ {}';
assert.equal(template.split(marker).length, 2);
const source = template.replace(marker, JSON.stringify(mediaObjects));
const {default:worker, handle, parseRange} = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

const encoder = new TextEncoder();
const token = 'test-only-not-a-deployed-secret';
const bytes = encoder.encode('0123456789');
class MockR2 {
  constructor() { this.items = new Map([[mediaKey, bytes]]); this.metadata = new Map(); this.putCount = 0; }
  object(key) {
    const data = this.items.get(key);
    return data ? {key, size:data.byteLength, etag:'mock-etag', httpEtag:'"mock-etag"', uploaded:new Date('2026-10-23T00:00:00Z'), customMetadata:this.metadata.get(key)} : null;
  }
  async head(key) { return this.object(key); }
  async get(key, options) {
    const item = this.object(key); if (!item) return null;
    let data = this.items.get(key);
    if (options?.range) data = data.slice(options.range.offset, options.range.offset + options.range.length);
    return {...item, body:new Response(data).body};
  }
  async put(key, body, options) {
    const data = new Uint8Array(await new Response(body).arrayBuffer());
    this.items.set(key,data); this.metadata.set(key,options.customMetadata); this.putCount++;
    return this.object(key);
  }
}
const req = (path, options) => new Request('https://example.invalid'+path, options);
function uploadRequest({authorization='Bearer '+token,length='4',body='abcd',type='video/mp4',method='PUT',key=mediaKey}={}) {
  const headers = {'Authorization':authorization,'Content-Type':type};
  if (length !== null) headers['Content-Length']=length;
  return req('/admin/media/'+key,{method,headers,body});
}

test('range parser: closed, open, suffix, capped, invalid and multiple', () => {
  assert.deepEqual(parseRange('bytes=2-4',10),{start:2,end:4,offset:2,length:3});
  assert.equal(parseRange('bytes=2-',10).length,8);
  assert.equal(parseRange('bytes=-3',10).start,7);
  assert.equal(parseRange('bytes=-30',10).start,0);
  assert.equal(parseRange('bytes=2-999',10).end,9);
  for (const value of ['bytes=10-','bytes=3-2','bytes=-0','bytes=-','bytes=0-1,3-4','bytes=abc','items=0-1','bytes=9007199254740993-']) assert.equal(parseRange(value,10),null,value);
  assert.equal(parseRange('bytes=0-',0),null);
});
test('full GET, HEAD and cache validation', async () => {
  const env={BUCKET:new MockR2()};
  let res=await worker.fetch(req('/media/'+mediaKey),env,{waitUntil(){}});
  assert.equal(res.status,200); assert.equal(await res.text(),'0123456789');
  assert.equal(res.headers.get('content-type'),'video/mp4'); assert.equal(res.headers.get('content-length'),'10');
  res=await handle(req('/media/'+mediaKey,{method:'HEAD'}),env);
  assert.equal(res.status,200); assert.equal(await res.text(),''); assert.equal(res.headers.get('content-length'),'10');
  res=await handle(req('/media/'+mediaKey,{headers:{'If-None-Match':'W/"mock-etag"'}}),env);
  assert.equal(res.status,304); assert.equal(await res.text(),'');
});
test('GET/HEAD range 206, 416 and If-Range', async () => {
  const env={BUCKET:new MockR2()};
  for (const [range,expected,contentRange] of [['bytes=2-4','234','bytes 2-4/10'],['bytes=8-','89','bytes 8-9/10'],['bytes=-2','89','bytes 8-9/10']]) {
    const res=await handle(req('/media/'+mediaKey,{headers:{Range:range}}),env);
    assert.equal(res.status,206); assert.equal(await res.text(),expected); assert.equal(res.headers.get('content-range'),contentRange); assert.equal(res.headers.get('content-length'),String(expected.length));
  }
  let res=await handle(req('/media/'+mediaKey,{method:'HEAD',headers:{Range:'bytes=2-4'}}),env);
  assert.equal(res.status,206); assert.equal(await res.text(),''); assert.equal(res.headers.get('content-length'),'3');
  for (const range of ['bytes=10-','bytes=0-1,3-4','bytes=-0']) {
    res=await handle(req('/media/'+mediaKey,{headers:{Range:range}}),env);
    assert.equal(res.status,416); assert.equal(res.headers.get('content-range'),'bytes */10');
  }
  res=await handle(req('/media/'+mediaKey,{headers:{Range:'bytes=0-1','If-Range':'"old"'}}),env);
  assert.equal(res.status,200); assert.equal(await res.text(),'0123456789');
});
test('strict route whitelist and read methods', async () => {
  const env={BUCKET:new MockR2()};
  for (const path of ['/media/other.mp4','/media/lafan/dance.mp4','/.openai/hosting.json','/admin/media/no.mp4']) assert.equal((await handle(req(path),env)).status,404);
  assert.equal((await handle(req('/media/'+mediaKey,{method:'POST'}),env)).status,405);
  assert.equal((await handle(req('/media/100style/ood_low.mp4'),env)).status,404);
});
test('every manifest video is routable; upload size is checked per key', async () => {
  const bucket = new MockR2();
  const env = {BUCKET:bucket,MEDIA_UPLOAD_TOKEN:token,MEDIA_UPLOAD_ENABLED:'true'};
  for (const video of manifest.videos) {
    bucket.items.set(video.key, bytes);
    assert.equal((await handle(req('/media/'+video.key,{method:'HEAD'}),env)).status,200,video.key);
    const invalidLength = mediaObjects[video.key].size + 1;
    const res = await handle(uploadRequest({key:video.key,length:String(invalidLength)}),env);
    assert.equal(res.status,400,video.key);
  }
  assert.equal(bucket.putCount,0);
});
test('upload disabled without token; unauthorized writes rejected', async () => {
  const bucket=new MockR2();
  assert.equal((await handle(uploadRequest(),{BUCKET:bucket})).status,404);
  assert.equal((await handle(uploadRequest({authorization:'Bearer wrong'}),{BUCKET:bucket,MEDIA_UPLOAD_TOKEN:token,MEDIA_UPLOAD_ENABLED:'true'})).status,401);
  assert.equal(bucket.putCount,0);
});
test('explicit upload enable flag required even with a residual valid token', async () => {
  const bucket=new MockR2();
  for (const flag of [undefined, 'false', false, true, '1', 'TRUE', '']) {
    const env={BUCKET:bucket,MEDIA_UPLOAD_TOKEN:token,MEDIA_UPLOAD_ENABLED:flag};
    assert.equal((await handle(uploadRequest(),env)).status,404,String(flag));
  }
  assert.equal((await handle(uploadRequest(),{BUCKET:bucket,MEDIA_UPLOAD_ENABLED:'true'})).status,404);
  assert.equal(bucket.putCount,0);
});
test('bounded upload verifies manifest size and SHA-256 before storage', async () => {
  const bucket=new MockR2(),env={BUCKET:bucket,MEDIA_UPLOAD_TOKEN:token,MEDIA_UPLOAD_ENABLED:'true'};
  let res=await handle(uploadRequest(),env);
  assert.equal(res.status,201); assert.deepEqual(await res.json(),{key:mediaKey,size:4,sha256:uploadSha256,etag:'mock-etag',httpEtag:'"mock-etag"'}); assert.equal(bucket.putCount,1);
  for (const [options,status] of [[{length:null},411],[{length:'not-a-number'},400],[{length:'0'},400],[{length:String(25*1024*1024+1)},413],[{type:'text/plain'},415],[{key:'unknown.mp4'},404],[{method:'POST'},405],[{length:'3',body:'abcd'},400],[{length:'6',body:'abcd'},400],[{body:'abc'},400],[{body:'abcde'},400],[{body:'abce'},400]]) {
    res=await handle(uploadRequest(options),env); assert.equal(res.status,status,JSON.stringify(options));
  }
  assert.equal(bucket.putCount,1); assert.equal((await bucket.head(mediaKey)).size,4);
  for (const method of ['GET','HEAD']) {
    const verified = await handle(req('/media/'+mediaKey,{method,headers:{Range:'bytes=0-1'}}),env);
    assert.equal(verified.status,206);
    assert.equal(verified.headers.get('X-Content-SHA256'),uploadSha256);
    assert.equal(await verified.text(),method === 'HEAD' ? '' : 'ab');
  }
});
test('static assets only, HEAD, ETag, and no secret values in responses', async () => {
  const assets={'/index.html':{body:'<h1>SuperMimic</h1>',bytes:19,type:'text/html; charset=utf-8',etag:'"static"'}};
  let res=await handle(req('/'),{MEDIA_UPLOAD_TOKEN:token},assets);
  assert.equal(res.status,200); assert.equal(await res.text(),'<h1>SuperMimic</h1>');
  res=await handle(req('/index.html',{method:'HEAD'}),{},assets); assert.equal(res.status,200); assert.equal(await res.text(),'');
  res=await handle(req('/',{headers:{'If-None-Match':'"static"'}}),{},assets); assert.equal(res.status,304);
  res=await handle(req('/secret'),{MEDIA_UPLOAD_TOKEN:token},assets); assert.equal(res.status,404); assert.ok(!(await res.text()).includes(token));
});
