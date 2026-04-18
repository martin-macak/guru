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

export async function getBoot(): Promise<BootPayload> {
  const response = await fetch("/web/boot");

  if (!response.ok) {
    throw new Error(`boot failed: ${response.status}`);
  }

  return (await response.json()) as BootPayload;
}
