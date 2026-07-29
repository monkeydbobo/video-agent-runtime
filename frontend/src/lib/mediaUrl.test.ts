import { describe, expect, it, vi, beforeEach } from "vitest";
import {
  appendMediaToken,
  buildMediaUrl,
  clearMediaTokenCache,
  getGlobalAssetUrlSync,
  getProjectFileUrlSync,
  isPrivateMediaUrl,
  parseGlobalAssetPath,
  resolveAssetImageUrl,
} from "@/lib/mediaUrl";

describe("mediaUrl", () => {
  beforeEach(() => {
    clearMediaTokenCache();
  });

  it("detects private media URLs", () => {
    expect(isPrivateMediaUrl("/api/v1/files/demo/a.png")).toBe(true);
    expect(isPrivateMediaUrl("/api/v1/global-assets/character/a.png")).toBe(true);
    expect(isPrivateMediaUrl("https://cdn.example/a.png")).toBe(false);
  });

  it("appends media_token without breaking existing query", () => {
    expect(appendMediaToken("/api/v1/files/demo/a.png?v=1", "tok")).toBe(
      "/api/v1/files/demo/a.png?v=1&media_token=tok",
    );
    expect(appendMediaToken("/api/v1/files/demo/a.png", "tok")).toBe(
      "/api/v1/files/demo/a.png?media_token=tok",
    );
  });

  it("builds project file URLs with cache bust", () => {
    expect(getProjectFileUrlSync("my project", "source/a.txt")).toBe(
      "/api/v1/files/my%20project/source/a.txt",
    );
    expect(getProjectFileUrlSync("demo", "a.png", 3)).toBe(
      "/api/v1/files/demo/a.png?v=3",
    );
  });

  it("parses legacy and user-scoped global asset paths", () => {
    expect(parseGlobalAssetPath("_global_assets/character/abc.png")).toEqual({
      type: "character",
      filename: "abc.png",
    });
    expect(parseGlobalAssetPath("users/u1/assets/scene/x.webp")).toEqual({
      type: "scene",
      filename: "x.webp",
      assetPath: "users/u1/assets/scene/x.webp",
    });
  });

  it("builds global asset URLs", () => {
    const legacy = getGlobalAssetUrlSync("_global_assets/character/abc.png", "123");
    expect(legacy).toContain("/global-assets/character/abc.png");
    expect(legacy).toContain("fp=123");

    const scoped = getGlobalAssetUrlSync("users/u1/assets/prop/p.png", null, "scoped-tok");
    expect(scoped).toContain("/global-assets/prop/p.png");
    expect(scoped).toContain("media_token=scoped-tok");
  });

  it("prefers image_url + media_token from asset payload", () => {
    const url = resolveAssetImageUrl({
      image_path: "users/u1/assets/character/a.png",
      image_url: "/api/v1/global-assets/character/a.png",
      media_token: "asset-tok",
      updated_at: null,
    });
    expect(url).toContain("/api/v1/global-assets/character/a.png");
    expect(url).toContain("media_token=asset-tok");
  });

  it("buildMediaUrl combines cache bust and token", () => {
    expect(
      buildMediaUrl("/api/v1/files/demo/a.png", { cacheBust: 9, mediaToken: "t" }),
    ).toBe("/api/v1/files/demo/a.png?v=9&media_token=t");
  });
});

describe("ensureProjectMediaToken", () => {
  beforeEach(() => {
    clearMediaTokenCache();
    vi.restoreAllMocks();
  });

  it("skips network when auth disabled", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/auth/status")) {
        return new Response(JSON.stringify({ enabled: false, registration_enabled: false }));
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    const { ensureProjectMediaToken } = await import("@/lib/mediaUrl");
    await expect(ensureProjectMediaToken("demo")).resolves.toBeNull();
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes("/media-token"))).toBe(false);
  });
});
