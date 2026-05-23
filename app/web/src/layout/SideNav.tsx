import { NavLink } from 'react-router-dom';
import { signOut } from '../lib/session';
import type { AuthUser } from '../lib/session';

export function SideNav({ user }: { user?: AuthUser | null }) {
  return (
    <aside className="hidden md:flex flex-col h-full p-md gap-lg fixed left-0 top-0 w-[280px] bg-surface-container-low z-50">
      <div className="flex items-center gap-sm px-sm">
        <div className="w-10 h-10 rounded-full bg-primary flex items-center justify-center text-on-primary">
          <span className="material-symbols-outlined">photo_library</span>
        </div>
        <div>
          <h1 className="text-headline-sm font-bold text-primary">Gallery Pro</h1>
          <p className="text-label-md text-on-surface-variant">Family Archive</p>
        </div>
      </div>

      <nav className="flex flex-col gap-xs mt-xl">
        <NavLink
          to="/"
          end
          className={({ isActive }) =>
            `flex items-center gap-md px-md py-sm font-bold rounded-full transition-all duration-200 text-label-md ${
              isActive
                ? 'text-primary bg-secondary-container translate-x-1'
                : 'text-on-surface-variant hover:bg-surface-container-high'
            }`
          }
        >
          <span className="material-symbols-outlined">photo_library</span>
          <span>Library</span>
        </NavLink>

        <NavLink
          to="/games"
          className={({ isActive }) =>
            `flex items-center gap-md px-md py-sm font-bold rounded-full transition-all duration-200 text-label-md ${
              isActive
                ? 'text-primary bg-secondary-container translate-x-1'
                : 'text-on-surface-variant hover:bg-surface-container-high'
            }`
          }
        >
          <span className="material-symbols-outlined">sports_esports</span>
          <span>Games</span>
        </NavLink>
      </nav>

      {user && (
        <div className="mt-auto flex flex-col gap-sm">
          <div className="flex items-center gap-sm px-sm py-xs">
            <AccountAvatar user={user} />
            <div className="min-w-0">
              {user.name && (
                <p className="text-label-md font-bold text-on-surface truncate">{user.name}</p>
              )}
              <p className="text-label-md text-on-surface-variant truncate">{user.email}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => signOut()}
            className="flex items-center gap-md px-md py-sm font-bold rounded-full transition-all duration-200 text-label-md text-on-surface-variant hover:bg-surface-container-high"
          >
            <span className="material-symbols-outlined">logout</span>
            <span>Sign out</span>
          </button>
        </div>
      )}
    </aside>
  );
}

function AccountAvatar({ user }: { user: AuthUser }) {
  if (user.avatarUrl) {
    return (
      <img
        src={user.avatarUrl}
        alt={user.name ?? user.email ?? 'Account'}
        referrerPolicy="no-referrer"
        className="w-9 h-9 rounded-full object-cover shrink-0"
      />
    );
  }
  return (
    <div className="w-9 h-9 rounded-full bg-secondary-container flex items-center justify-center shrink-0 text-on-secondary-container">
      <span className="material-symbols-outlined">account_circle</span>
    </div>
  );
}
