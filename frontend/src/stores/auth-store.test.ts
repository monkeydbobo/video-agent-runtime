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
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ valid: true, username: "bob" }),
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
});
