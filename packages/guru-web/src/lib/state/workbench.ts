import {
  createContext,
  createElement,
  useContext,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";

import type { BootPayload } from "../api/client";
import type { WorkbenchSurface } from "./url";

type WorkbenchContextValue = {
  boot: BootPayload;
  surface: WorkbenchSurface;
  setSurface: (surface: WorkbenchSurface) => void;
};

const WorkbenchContext = createContext<WorkbenchContextValue | null>(null);

type WorkbenchProviderProps = PropsWithChildren<{
  boot: BootPayload;
  initialSurface: WorkbenchSurface;
}>;

export function WorkbenchProvider({ boot, initialSurface, children }: WorkbenchProviderProps) {
  const [surface, setSurface] = useState<WorkbenchSurface>(initialSurface);
  const value = useMemo(
    () => ({
      boot,
      surface,
      setSurface,
    }),
    [boot, surface],
  );

  return createElement(WorkbenchContext.Provider, { value }, children);
}

export function useWorkbench() {
  const context = useContext(WorkbenchContext);

  if (!context) {
    throw new Error("useWorkbench must be used within WorkbenchProvider");
  }

  return context;
}
