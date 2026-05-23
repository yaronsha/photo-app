import { NavLink } from 'react-router-dom';
import { signOut } from '../lib/session';
import type { AuthUser } from '../lib/session';

export function MobileBottomNav({ user }: { user?: AuthUser | null }) {
  return (
    <nav className="md:hidden fixed bottom-0 left-0 w-full bg-surface-container-low border-t border-outline-variant flex justify-around items-center py-sm z-50">
      <NavLink
        to="/"
        end
        className={({ isActive }) =>
          `flex flex-col items-center gap-xs ${isActive ? 'text-primary font-bold' : 'text-on-surface-variant'}`
        }
      >
        {({ isActive }) => (
          <>
            <span
              className="material-symbols-outlined"
              style={isActive ? { fontVariationSettings: "'FILL' 1" } : undefined}
            >
              photo_library
            </span>
            <span className="text-[10px] uppercase tracking-tighter">Library</span>
          </>
        )}
      </NavLink>

      <NavLink
        to="/games"
        className={({ isActive }) =>
          `flex flex-col items-center gap-xs ${isActive ? 'text-primary font-bold' : 'text-on-surface-variant'}`
        }
      >
        {({ isActive }) => (
          <>
            <span
              className="material-symbols-outlined"
              style={isActive ? { fontVariationSettings: "'FILL' 1" } : undefined}
            >
              sports_esports
            </span>
            <span className="text-[10px] uppercase tracking-tighter">Games</span>
          </>
        )}
      </NavLink>

      {user && (
        <button
          type="button"
          onClick={() => signOut()}
          className="flex flex-col items-center gap-xs text-on-surface-variant"
        >
          {user.avatarUrl ? (
            <img
              src={user.avatarUrl}
              alt={user.name ?? user.email ?? 'Account'}
              referrerPolicy="no-referrer"
              className="w-6 h-6 rounded-full object-cover"
            />
          ) : (
            <span className="material-symbols-outlined">logout</span>
          )}
          <span className="text-[10px] uppercase tracking-tighter">Sign out</span>
        </button>
      )}
    </nav>
  );
}
