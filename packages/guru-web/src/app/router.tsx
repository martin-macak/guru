import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./layout/AppShell";
import { useWorkbench } from "../lib/state/workbench";
import {
  surfaceFromPathname,
  surfaceToPath,
  type WorkbenchSurface,
  workbenchSurfaces,
} from "../lib/state/url";

type SurfaceRouteProps = {
  surface: WorkbenchSurface;
};

function SurfaceRoute({ surface }: SurfaceRouteProps) {
  const { setSurface } = useWorkbench();

  useEffect(() => {
    setSurface(surface);
  }, [setSurface, surface]);

  return <AppShell />;
}

export function AppRouter() {
  const defaultSurface = surfaceFromPathname(window.location.pathname);

  return (
    <Routes>
      <Route element={<Navigate replace to={surfaceToPath(defaultSurface)} />} path="/" />
      {workbenchSurfaces.map((surface) => (
        <Route element={<SurfaceRoute surface={surface} />} key={surface} path={surfaceToPath(surface)} />
      ))}
      <Route element={<Navigate replace to={surfaceToPath(defaultSurface)} />} path="*" />
    </Routes>
  );
}
