import { NavLink } from "react-router-dom";

import { workbenchSurfaces, surfaceToPath, surfaceLabels } from "../../lib/state/url";
import { cn } from "../../lib/utils";

export function MenuBar({ projectName }: { projectName: string }) {
  return (
    <nav
      className="flex h-8 items-center gap-4 border-b border-neutral-200 bg-white px-4 text-sm"
      aria-label="Primary"
    >
      <span className="font-semibold text-neutral-700" data-testid="project-name">
        {projectName}
      </span>
      <ul className="flex items-center gap-3">
        {workbenchSurfaces.map((s) => (
          <li key={s}>
            <NavLink
              to={surfaceToPath[s]}
              className={({ isActive }) =>
                cn(
                  "rounded px-2 py-1 text-neutral-600 hover:bg-neutral-100",
                  isActive && "bg-neutral-900 text-white hover:bg-neutral-900",
                )
              }
            >
              {surfaceLabels[s]}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
