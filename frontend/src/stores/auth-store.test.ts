import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "@/stores/auth-store";

describe("auth-store initialize", () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.setState({
      token: null,
      username: null,
      isAuthenticated: false,
      isLoading: true,
      registrationEnabled: false,
      googleEnabled: false,
      googleClientId: null,
    });
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("hydrates username from /auth/verify when a token is present", async () => {
    localStorage.setItem("arcreel_auth_token", "tok-abc");
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes("/auth/verify")) {
        return { ok: true, json: async () => ({ valid: true, username: "bob" }) };
      }
      if (url.includes("/auth/status")) {
        return {
          ok: true,
          json: async () => ({
            enabled: true,
            registration_enabled: true,
            google_enabled: true,
            google_client_id: "cid.apps.googleusercontent.com",
          }),
        };
      }
      return { ok: false, status: 404 };
    });
    vi.stubGlobal("fetch", fetchMock);

    useAuthStore.getState().initialize();

    expect(useAuthStore.getState()).toMatchObject({
      token: "tok-abc",
      isAuthenticated: true,
      isLoading: false,
      username: null,
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/auth/verify",
      expect.objectContaining({
        headers: { Authorization: "Bearer tok-abc" },
      }),
    );

    await vi.waitFor(() => {
      expect(useAuthStore.getState().username).toBe("bob");
      expect(useAuthStore.getState().googleEnabled).toBe(true);
      expect(useAuthStore.getState().googleClientId).toBe("cid.apps.googleusercontent.com");
    });
  });

  it("keeps auth when /auth/verify fails", async () => {
    localStorage.setItem("arcreel_auth_token", "tok-bad");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
      }),
    );

    useAuthStore.getState().initialize();

    await vi.waitFor(() => {
      expect(useAuthStore.getState()).toMatchObject({
        token: "tok-bad",
        isAuthenticated: true,
        isLoading: false,
        username: null,
      });
    });
  });

  it("stores google flags from /auth/status when unauthenticated", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          enabled: true,
          registration_enabled: false,
          google_enabled: false,
          google_client_id: null,
        }),
      }),
    );

    useAuthStore.getState().initialize();

    await vi.waitFor(() => {
      expect(useAuthStore.getState()).toMatchObject({
        isLoading: false,
        isAuthenticated: false,
        registrationEnabled: false,
        googleEnabled: false,
        googleClientId: null,
      });
    });
  });
});
