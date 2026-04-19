import { getBoot } from "./client";

const bootPayload = {
  project: { name: "guru", root: "/tmp/guru" },
  web: {
    enabled: true,
    available: true,
    url: "http://127.0.0.1:41773",
    reason: null,
    autoOpen: false,
  },
  graph: { enabled: true },
};

describe("getBoot", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  test("uses a configured API base URL when provided", async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: true,
      json: async () => bootPayload,
    }));
    vi.stubGlobal("fetch", fetchSpy);
    vi.stubEnv("VITE_GURU_API_BASE_URL", "http://127.0.0.1:9000");

    await expect(getBoot()).resolves.toEqual(bootPayload);

    expect(fetchSpy).toHaveBeenCalledWith("http://127.0.0.1:9000/web/boot");
  });

  test("falls back to the current origin path when no API base is configured", async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: true,
      json: async () => bootPayload,
    }));
    vi.stubGlobal("fetch", fetchSpy);

    await expect(getBoot()).resolves.toEqual(bootPayload);

    expect(fetchSpy).toHaveBeenCalledWith("/web/boot");
  });
});
