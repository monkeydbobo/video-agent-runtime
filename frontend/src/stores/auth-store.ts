// @author wanghaobo

import { create } from "zustand";
import { getToken, setToken as saveToken, clearToken } from "@/utils/auth";

interface AuthState {
  token: string | null;
  username: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  registrationEnabled: boolean;
  googleEnabled: boolean;
  googleClientId: string | null;
  initialize: () => void;
  login: (token: string, username: string) => void;
  logout: () => void;
  setLoading: (loading: boolean) => void;
}

function isVerifyPayload(payload: unknown): payload is { valid: boolean; username: string } {
  return (
    typeof payload === "object" &&
    payload !== null &&
    (payload as { valid?: unknown }).valid === true &&
    typeof (payload as { username?: unknown }).username === "string" &&
    (payload as { username: string }).username.length > 0
  );
}

function parseAuthStatus(payload: unknown): {
  enabled: boolean;
  registrationEnabled: boolean;
  googleEnabled: boolean;
  googleClientId: string | null;
} | null {
  if (typeof payload !== "object" || payload === null) return null;
  const obj = payload as {
    enabled?: unknown;
    registration_enabled?: unknown;
    google_enabled?: unknown;
    google_client_id?: unknown;
  };
  if (typeof obj.enabled !== "boolean" || typeof obj.registration_enabled !== "boolean") {
    return null;
  }
  const googleEnabled = obj.google_enabled === true;
  const googleClientId =
    typeof obj.google_client_id === "string" && obj.google_client_id.trim()
      ? obj.google_client_id.trim()
      : null;
  return {
    enabled: obj.enabled,
    registrationEnabled: obj.registration_enabled,
    googleEnabled: googleEnabled && Boolean(googleClientId),
    googleClientId: googleEnabled ? googleClientId : null,
  };
}

/** Resolve signed-in username from /auth/verify after a page reload. */
function hydrateUsernameFromToken(token: string): void {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5000);
  fetch("/api/v1/auth/verify", {
    headers: { Authorization: `Bearer ${token}` },
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) throw new Error(`status ${res.status}`);
      const payload: unknown = await res.json();
      if (!isVerifyPayload(payload)) {
        throw new Error("invalid /auth/verify payload");
      }
      useAuthStore.setState({ username: payload.username });
    })
    .catch((err) => {
      console.warn("[auth] /auth/verify fetch failed; username badge unavailable", err);
    })
    .finally(() => {
      clearTimeout(timeoutId);
    });
}

/** Load public auth flags (registration / Google) from /auth/status. */
function hydrateAuthStatus(options?: { setAuthenticatedWhenDisabled?: boolean }): void {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5000);
  fetch("/api/v1/auth/status", { signal: controller.signal })
    .then(async (res) => {
      if (!res.ok) throw new Error(`status ${res.status}`);
      const parsed = parseAuthStatus(await res.json());
      if (!parsed) throw new Error("invalid /auth/status payload");
      useAuthStore.setState({
        registrationEnabled: parsed.registrationEnabled,
        googleEnabled: parsed.googleEnabled,
        googleClientId: parsed.googleClientId,
        ...(options?.setAuthenticatedWhenDisabled && !parsed.enabled
          ? { isAuthenticated: true }
          : {}),
      });
    })
    .catch((err) => {
      console.warn("[auth] /auth/status fetch failed; defaulting to login", err);
    })
    .finally(() => {
      clearTimeout(timeoutId);
      useAuthStore.setState({ isLoading: false });
    });
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  username: null,
  isAuthenticated: false,
  isLoading: true,
  registrationEnabled: false,
  googleEnabled: false,
  googleClientId: null,

  initialize: () => {
    const token = getToken();
    if (token) {
      set({ token, isAuthenticated: true, isLoading: false });
      // localStorage only keeps the token; refill username for the lobby badge.
      hydrateUsernameFromToken(token);
      // Load Google/registration flags without flipping isLoading (already settled).
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);
      fetch("/api/v1/auth/status", { signal: controller.signal })
        .then(async (res) => {
          if (!res.ok) throw new Error(`status ${res.status}`);
          const parsed = parseAuthStatus(await res.json());
          if (!parsed) throw new Error("invalid /auth/status payload");
          useAuthStore.setState({
            registrationEnabled: parsed.registrationEnabled,
            googleEnabled: parsed.googleEnabled,
            googleClientId: parsed.googleClientId,
          });
        })
        .catch((err) => {
          console.warn("[auth] /auth/status fetch failed while authenticated", err);
        })
        .finally(() => {
          clearTimeout(timeoutId);
        });
      return;
    }
    // 无 token 时先问后端是否启用了鉴权。`AUTH_ENABLED=false` 时后端全链路
    // bypass，前端也应该跳过登录页直接进主界面。超时 / 网络异常 / 响应 shape
    // 异常时 fail-closed 退回到登录页，避免误把损坏响应当成"无需鉴权"放行。
    hydrateAuthStatus({ setAuthenticatedWhenDisabled: true });
  },

  login: (token, username) => {
    saveToken(token);
    set({ token, username, isAuthenticated: true, isLoading: false });
  },

  logout: () => {
    clearToken();
    set({ token: null, username: null, isAuthenticated: false });
  },

  setLoading: (isLoading) => set({ isLoading }),
}));
