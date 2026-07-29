// @author wanghaobo

import { afterEach, describe, expect, it, vi } from "vitest";

async function freshLoader() {
  vi.resetModules();
  const mod = await import("@/utils/gis-loader");
  return mod.loadGisScript;
}

describe("loadGisScript", () => {
  afterEach(() => {
    document.getElementById("google-gsi-client")?.remove();
    delete window.google;
    vi.useRealTimers();
  });

  it("resolves when an existing script finished loading before listeners attach", async () => {
    const loadGisScript = await freshLoader();
    const existing = document.createElement("script");
    existing.id = "google-gsi-client";
    document.head.appendChild(existing);

    const pending = loadGisScript();
    // No further "load" event will ever fire for the already-loaded tag.
    window.google = { accounts: { id: {} as never } };

    await expect(pending).resolves.toBeUndefined();
  });

  it("rejects on load error and clears the cached promise so a retry can happen", async () => {
    const loadGisScript = await freshLoader();

    const first = loadGisScript();
    const injected = document.getElementById("google-gsi-client");
    expect(injected).not.toBeNull();
    injected?.dispatchEvent(new Event("error"));
    await expect(first).rejects.toThrow("gis load failed");

    const retry = loadGisScript();
    expect(retry).not.toBe(first);
    window.google = { accounts: { id: {} as never } };
    await expect(retry).resolves.toBeUndefined();
  });

  it("rejects when the script never becomes usable", async () => {
    vi.useFakeTimers();
    const loadGisScript = await freshLoader();
    const existing = document.createElement("script");
    existing.id = "google-gsi-client";
    document.head.appendChild(existing);

    const pending = loadGisScript();
    const assertion = expect(pending).rejects.toThrow("gis load failed");
    await vi.advanceTimersByTimeAsync(10_100);
    await assertion;
  });

  it("resolves immediately when the global is already available", async () => {
    const loadGisScript = await freshLoader();
    window.google = { accounts: { id: {} as never } };
    await expect(loadGisScript()).resolves.toBeUndefined();
    expect(document.getElementById("google-gsi-client")).toBeNull();
  });

  it("reuses the pending promise for concurrent callers", async () => {
    const loadGisScript = await freshLoader();
    const first = loadGisScript();
    const second = loadGisScript();
    expect(second).toBe(first);
    window.google = { accounts: { id: {} as never } };
    await expect(first).resolves.toBeUndefined();
  });
});
