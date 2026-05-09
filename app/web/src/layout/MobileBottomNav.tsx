import { NavLink } from 'react-router-dom';

export function MobileBottomNav() {
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
    </nav>
  );
}
