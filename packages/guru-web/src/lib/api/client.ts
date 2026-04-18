export type BootPayload = {
  project: {
    name: string;
    root: string;
  };
  web: {
    enabled: boolean;
    available: boolean;
    url: string | null;
    reason: string | null;
    autoOpen: boolean;
  };
  graph: {
    enabled: boolean;
  };
};

function resolveBootUrl(): string {
  const apiBaseUrl = import.meta.env.VITE_GURU_API_BASE_URL?.trim();

  if (!apiBaseUrl) {
    return "/web/boot";
  }

  return new URL("/web/boot", `${apiBaseUrl.replace(/\/+$/, "")}/`).toString();
}

export async function getBoot(): Promise<BootPayload> {
  const response = await fetch(resolveBootUrl());

  if (!response.ok) {
    throw new Error(`boot failed: ${response.status}`);
  }

  return (await response.json()) as BootPayload;
}
