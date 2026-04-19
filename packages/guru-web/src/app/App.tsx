import { RouterProvider } from "react-router-dom";
import { useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { useBootQuery } from "../lib/api/hooks";
import { useWorkbench } from "../lib/state/workbench";
import { router } from "./router";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
});

export function AppBootstrap() {
  const boot = useBootQuery();
  const setBoot = useWorkbench((s) => s.setBoot);

  useEffect(() => {
    if (boot.data) {
      setBoot(boot.data);
    }
  }, [boot.data, setBoot]);

  if (boot.isPending) {
    return <p className="p-6 text-sm text-neutral-600">Loading Guru…</p>;
  }

  if (boot.isError || !boot.data) {
    return <p className="p-6 text-sm text-neutral-600">Server unavailable</p>;
  }

  return <RouterProvider router={router} />;
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppBootstrap />
    </QueryClientProvider>
  );
}
