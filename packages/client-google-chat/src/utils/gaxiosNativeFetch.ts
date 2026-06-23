import { Gaxios } from 'gaxios';
import { Logger } from './logger.js';

const logger = Logger.getLogger('gaxiosNativeFetch');

/**
 * Force gaxios — the HTTP transport beneath `google-auth-library` and
 * `googleapis` — to use Node's native `fetch` (undici) instead of the bundled
 * `node-fetch`.
 *
 * Why this is needed:
 *   gaxios picks its fetch implementation once, at module load, with roughly:
 *     const fetch = hasFetch() ? window.fetch : nodeFetch;
 *   `hasFetch()` only looks for a *browser* `window.fetch`, so under Node it
 *   ALWAYS falls back to node-fetch — even on Node 18+ where `globalThis.fetch`
 *   exists. node-fetch 2.x's response-stream handling broke in a Node *patch*
 *   release: every response rejects with `ERR_STREAM_PREMATURE_CLOSE`
 *   ("Invalid response body … : Premature close"). That took down all Google
 *   Chat traffic — token fetch, message send, attachment upload/download —
 *   while native fetch/undici works fine.
 *
 *   Exact boundary we observed (both running the identical image/deps,
 *   gaxios 6.7.1 + node-fetch 2.7.0, only the Node patch differs):
 *     - Node v24.16.0  -> node-fetch works, no patch needed
 *     - Node v24.17.0  -> node-fetch fails on every call, this patch required
 *   This is a Node *regression*, tracked at nodejs/node#63989: the v24.17.0 fix
 *   for "response queue poisoning in http.Agent" (CVE-2026-48931) altered
 *   keep-alive socket-reuse timing and broke premature-close handling on reused
 *   pooled connections. node-fetch makes requests over a keep-alive agent, so it
 *   trips on it; native fetch/undici does not. The same regression hit the 22.x
 *   line, so pinning the base image backward (<=24.16) is a stopgap that also
 *   strands us below the security fix.
 *   References:
 *     - Node regression: https://github.com/nodejs/node/issues/63989
 *     - Node fix:        https://github.com/nodejs/node/pull/64004 (not yet
 *       released as of this commit; a later 24.x / 22.x patch will carry it)
 *     - Same boundary, independent report: backstage/backstage#34651
 *
 * How the patch works:
 *   gaxios resolves `opts.fetchImplementation || fetch` per request, where
 *   `opts` is the merge of instance defaults and per-call options. Injecting
 *   `fetchImplementation` into every `request()` at the prototype level covers
 *   every transporter google-auth-library / googleapis create — the cached auth
 *   client's transporter and any per-request `DefaultTransporter` — without
 *   reaching into each instance. Call this once, before the first request.
 *
 * When/how to remove this patch — safe once EITHER is true:
 *   1. The Node base image carries the nodejs/node#64004 fix (a 24.x patch
 *      > 24.17, or the corresponding 22.x patch). Verify with `node --version`
 *      against the release notes for PR #64004; once on a fixed runtime,
 *      node-fetch works again and this patch is a no-op.
 *   2. gaxios is upgraded to v7+, which drops node-fetch for the native Fetch
 *      API. From packages/client-google-chat run `npm ls gaxios node-fetch`; if
 *      gaxios >= 7 and node-fetch no longer appears under the gaxios /
 *      google-auth-library subtree, the bundled-node-fetch path is gone.
 *   In either case delete this module and its call in app.ts. Until then keep
 *   it: it is harmless on an unaffected runtime (it only sets a fetch impl
 *   gaxios would otherwise have to pick itself).
 */
let patched = false;

export function patchGaxiosToUseNativeFetch(): void {
  if (patched) return;
  if (typeof globalThis.fetch !== 'function') {
    // Node < 18 (no global fetch): leave gaxios on node-fetch.
    return;
  }

  type RequestFn = (opts?: Record<string, unknown>) => unknown;
  const proto = Gaxios.prototype as unknown as { request?: RequestFn; defaults?: Record<string, unknown> };
  const original = proto.request;
  if (typeof original !== 'function') return;

  proto.request = function (this: { defaults?: Record<string, unknown> }, opts: Record<string, unknown> = {}) {
    // Respect an explicit override on either the call or the instance defaults.
    if (opts.fetchImplementation == null && this.defaults?.fetchImplementation == null) {
      opts = { ...opts, fetchImplementation: globalThis.fetch };
    }
    return original.call(this, opts);
  };

  patched = true;
  logger.info('Patched gaxios to use native fetch (undici) instead of node-fetch');
}
