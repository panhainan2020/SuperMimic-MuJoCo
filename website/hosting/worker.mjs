/* No dependencies. build_host.py injects text assets and reviewed media metadata. */
const STATIC_ASSETS = /*__STATIC_ASSETS__*/ {};
const MEDIA_OBJECTS = /*__MEDIA_OBJECTS__*/ {};
const MEDIA_KEYS = new Set(Object.keys(MEDIA_OBJECTS));
const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;

function response(body, status = 200, headers = {}) {
  return new Response(body, {status, headers: {
    "X-Content-Type-Options": "nosniff", "Referrer-Policy": "strict-origin-when-cross-origin",
    ...headers,
  }});
}
function json(value, status = 200) {
  return response(JSON.stringify(value), status, {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"});
}
function keyFor(path, prefix) {
  if (!path.startsWith(prefix)) return null;
  try {
    const key = decodeURIComponent(path.slice(prefix.length));
    return MEDIA_KEYS.has(key) ? key : null;
  } catch { return null; }
}
function objectEtag(object) {
  return object.httpEtag || '"' + object.etag + '"';
}
function matchesEtag(header, etag) {
  return header && header.split(",").some(item => item.trim() === "*" || item.trim().replace(/^W\//, "") === etag);
}
export function parseRange(header, size) {
  const match = /^bytes=(\d*)-(\d*)$/.exec(header || "");
  if (!match || (!match[1] && !match[2]) || !size) return null;
  const a = match[1] ? Number(match[1]) : null;
  const b = match[2] ? Number(match[2]) : null;
  if ((a !== null && !Number.isSafeInteger(a)) || (b !== null && !Number.isSafeInteger(b))) return null;
  let start, end;
  if (a === null) {
    if (b <= 0) return null;
    start = Math.max(0, size - b); end = size - 1;
  } else {
    start = a; end = b === null ? size - 1 : Math.min(b, size - 1);
    if (start >= size || end < start) return null;
  }
  return {start, end, offset: start, length: end - start + 1};
}
async function authorized(request, token) {
  if (typeof token !== "string" || !token) return false;
  const supplied = request.headers.get("Authorization") || "";
  if (!supplied.startsWith("Bearer ")) return false;
  const encode = value => new TextEncoder().encode(value);
  const [actual, expected] = await Promise.all([
    crypto.subtle.digest("SHA-256", encode(supplied.slice(7))),
    crypto.subtle.digest("SHA-256", encode(token)),
  ]);
  const a = new Uint8Array(actual), b = new Uint8Array(expected);
  let difference = 0;
  for (let index = 0; index < a.length; index++) difference |= a[index] ^ b[index];
  return difference === 0;
}
async function upload(request, env, key) {
  if (env.MEDIA_UPLOAD_ENABLED !== "true" || !env.MEDIA_UPLOAD_TOKEN) return response("Not found", 404);
  if (!await authorized(request, env.MEDIA_UPLOAD_TOKEN)) {
    return response("Unauthorized", 401, {"WWW-Authenticate": 'Bearer realm="media-upload"', "Cache-Control": "no-store"});
  }
  if (request.method !== "PUT") return response("Method not allowed", 405, {Allow: "PUT"});
  if (!key) return response("Not found", 404);
  if (!env.BUCKET) return response("Media storage unavailable", 503);
  const value = request.headers.get("Content-Length");
  if (value === null) return response("Content-Length required", 411);
  if (!/^[0-9]+$/.test(value)) return response("Invalid Content-Length", 400);
  const length = Number(value);
  if (!Number.isSafeInteger(length) || length > MAX_UPLOAD_BYTES) return response("Upload exceeds 25 MiB", 413);
  if (length <= 0 || !request.body) return response("Empty media", 400);
  const expected = MEDIA_OBJECTS[key];
  if (length !== expected.size) return response("Media size differs from manifest", 400);
  if ((request.headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase() !== "video/mp4") return response("Expected video/mp4", 415);
  // Allocate only after the declared size matches the bounded manifest entry.
  // Verify all bytes before writing so a failed upload cannot replace an object.
  const data = new Uint8Array(length);
  const reader = request.body.getReader();
  let count = 0;
  try {
    for (;;) {
      const {done, value: chunk} = await reader.read();
      if (done) break;
      if (count + chunk.byteLength > length) {
        await reader.cancel();
        return response("Upload body length mismatch", 400);
      }
      data.set(chunk, count);
      count += chunk.byteLength;
    }
    if (count !== length) return response("Upload body length mismatch", 400);
    const digest = await crypto.subtle.digest("SHA-256", data);
    const sha256 = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
    if (sha256 !== expected.sha256) return response("Media SHA-256 differs from manifest", 400);
    const object = await env.BUCKET.put(key, data, {
      httpMetadata: {contentType: "video/mp4", cacheControl: "public, max-age=3600"},
      customMetadata: {sha256},
    });
    return json({key, size: object.size, sha256, etag: object.etag, httpEtag: objectEtag(object)}, 201);
  } catch {
    return response("Upload failed or body length mismatch", 400, {"Cache-Control": "no-store"});
  } finally {
    reader.releaseLock();
  }
}
async function media(request, env, key) {
  if (!key) return response("Not found", 404);
  if (!env.BUCKET) return response("Media storage unavailable", 503);
  const object = await env.BUCKET.head(key);
  if (!object) return response("Not found", 404);
  const etag = objectEtag(object);
  const headers = {
    "Content-Type": "video/mp4", "Accept-Ranges": "bytes", ETag: etag,
    "Cache-Control": "public, max-age=3600", "Content-Length": String(object.size),
  };
  if (object.uploaded) headers["Last-Modified"] = new Date(object.uploaded).toUTCString();
  if (/^[0-9a-f]{64}$/.test(object.customMetadata?.sha256 || "")) headers["X-Content-SHA256"] = object.customMetadata.sha256;
  if (matchesEtag(request.headers.get("If-None-Match"), etag)) return response(null, 304, {ETag: etag, "Cache-Control": headers["Cache-Control"]});
  let rangeHeader = request.headers.get("Range"), range = null;
  const ifRange = request.headers.get("If-Range");
  if (ifRange && ifRange !== etag) rangeHeader = null;
  if (rangeHeader !== null) {
    range = parseRange(rangeHeader, object.size);
    if (!range) return response(null, 416, {"Content-Range": `bytes */${object.size}`, "Accept-Ranges": "bytes", ETag: etag});
    headers["Content-Range"] = `bytes ${range.start}-${range.end}/${object.size}`;
    headers["Content-Length"] = String(range.length);
  }
  const status = range ? 206 : 200;
  if (request.method === "HEAD") return response(null, status, headers);
  const stored = await env.BUCKET.get(key, range ? {range: {offset: range.offset, length: range.length}} : undefined);
  if (!stored) return response("Not found", 404);
  return response(stored.body, status, headers);
}

export async function handle(request, env = {}, assets = STATIC_ASSETS) {
  const pathname = new URL(request.url).pathname;
  if (pathname.startsWith("/admin/media/")) return upload(request, env, keyFor(pathname, "/admin/media/"));
  if (request.method !== "GET" && request.method !== "HEAD") return response("Method not allowed", 405, {Allow: "GET, HEAD"});
  if (pathname.startsWith("/media/")) return media(request, env, keyFor(pathname, "/media/"));
  const path = pathname === "/" ? "/index.html" : pathname;
  if (!Object.prototype.hasOwnProperty.call(assets, path)) return response("Not found", 404);
  const item = assets[path];
  const headers = {"Content-Type": item.type, ETag: item.etag, "Cache-Control": "public, max-age=300", "Content-Length": String(item.bytes)};
  if (matchesEtag(request.headers.get("If-None-Match"), item.etag)) return response(null, 304, {ETag: item.etag, "Cache-Control": headers["Cache-Control"]});
  return response(request.method === "HEAD" ? null : item.body, 200, headers);
}

export default {fetch(request, env) { return handle(request, env); }};
