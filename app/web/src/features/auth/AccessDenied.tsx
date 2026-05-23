import { signOut } from '../../lib/session';

/** Shown when a user authenticates with Google but their email is not in the
 *  server's ALLOWED_EMAILS list (backend returns 403). The data is already
 *  protected server-side; this just replaces the empty app shell with a clear
 *  "not authorized" message and a way back to the login screen. */
export function AccessDenied({ email }: { email?: string }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background text-on-surface px-4">
      <div className="w-full max-w-sm space-y-6 text-center">
        <h1 className="text-2xl font-semibold">Access denied</h1>
        <p className="text-sm opacity-80">
          {email ? <><span className="font-medium">{email}</span> is not </> : 'This account is not '}
          authorized to use this app. Ask the family admin to add your email.
        </p>
        <button
          type="button"
          onClick={() => signOut()}
          className="w-full rounded-md border border-on-surface/20 bg-surface px-4 py-2 text-sm font-medium hover:bg-on-surface/5"
        >
          Sign in with a different account
        </button>
      </div>
    </div>
  );
}
