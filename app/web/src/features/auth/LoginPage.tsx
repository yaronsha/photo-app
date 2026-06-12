import { useState } from 'react';
import { supabase } from '../../lib/supabase';
import { getAuthRedirectError } from '../../lib/authRedirect';

// Generic, detail-free messages. We deliberately do NOT surface Supabase's
// `error_description` (it leaks backend detail); the specifics were scrubbed
// from the URL on load.
const REDIRECT_MESSAGES = {
  denied: 'Sign-in was cancelled.',
  failed: 'Sign-in failed. Please try again.',
} as const;

export function LoginPage() {
  const redirect = getAuthRedirectError();
  const [error, setError] = useState<string | null>(
    redirect === 'none' ? null : REDIRECT_MESSAGES[redirect],
  );
  const [loading, setLoading] = useState(false);

  const signInWithGoogle = async () => {
    if (!supabase) {
      setError('Auth is not configured.');
      return;
    }
    setLoading(true);
    setError(null);
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: window.location.origin,
        // Force Google's account chooser instead of silently reusing the
        // last-used Google session — lets a different account sign in.
        queryParams: { prompt: 'select_account' },
      },
    });
    if (error) {
      setError(error.message);
      setLoading(false);
    }
    // On success, Supabase navigates away to Google.
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background text-on-surface px-4">
      <div className="w-full max-w-sm space-y-6">
        <h1 className="text-2xl font-semibold text-center">Family Photos</h1>
        <p className="text-center text-sm opacity-80">
          Sign in with your Google account to continue.
        </p>
        <button
          type="button"
          onClick={signInWithGoogle}
          disabled={loading}
          className="w-full rounded-md border border-on-surface/20 bg-surface px-4 py-2 text-sm font-medium hover:bg-on-surface/5 disabled:opacity-50"
        >
          {loading ? 'Redirecting…' : 'Sign in with Google'}
        </button>
        {error && (
          <p role="alert" className="text-sm text-red-500 text-center">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
