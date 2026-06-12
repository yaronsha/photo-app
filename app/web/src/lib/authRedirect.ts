// Supabase OAuth redirect error handling.
//
// On a failed sign-in Supabase bounces back to our redirectTo (the app
// origin) with the failure in the URL — `?error=...&error_code=...&
// error_description=...` for the PKCE flow, or the same keys in the `#`
// fragment for the implicit flow. The `error_description` is verbose and
// leaks backend detail (e.g. "Database error saving new user"), and it
// lingers in the address bar.
//
// We scrub those keys from the URL on load and expose a generic,
// detail-free status for the UI. We never surface `error_description`.

export type AuthRedirectError = 'none' | 'denied' | 'failed';

const ERROR_KEYS = ['error', 'error_code', 'error_description'] as const;

let captured = false;
let status: AuthRedirectError = 'none';

/** Read the redirect-error status captured at load. */
export function getAuthRedirectError(): AuthRedirectError {
  return status;
}

/** Strip Supabase OAuth error keys from the URL (query + hash) and record a
 *  generic status. Idempotent — safe under React StrictMode double-invoke.
 *  Preserves the path and any unrelated params; only touches error keys, and
 *  only when an `error` is actually present (never disturbs a success hash
 *  carrying `access_token`). */
export function captureAndScrubAuthRedirect(): void {
  if (captured) return;
  captured = true;
  if (typeof window === 'undefined') return;

  const search = new URLSearchParams(window.location.search);
  // hash is like "#error=...&error_description=..."; drop the leading '#'.
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ''));

  const rawError = search.get('error') ?? hash.get('error');
  if (!rawError) return;

  status = rawError === 'access_denied' ? 'denied' : 'failed';

  for (const key of ERROR_KEYS) {
    search.delete(key);
    hash.delete(key);
  }

  const newSearch = search.toString();
  const newHash = hash.toString();
  const url =
    window.location.pathname +
    (newSearch ? `?${newSearch}` : '') +
    (newHash ? `#${newHash}` : '');
  window.history.replaceState(window.history.state, '', url);
}
