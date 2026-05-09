import { NavLink } from 'react-router-dom';

export function SideNav() {
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
    </aside>
  );
}
