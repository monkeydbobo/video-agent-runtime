// @author wanghaobo

import { create } from "zustand";
import { getToken, setToken as saveToken, clearToken } from "@/utils/auth";
import { clearMediaTokenCache } from "@/lib/mediaUrl";
import { useAssetsStore } from "@/stores/assets-store";
import { useConfigStatusStore } from "@/stores/config-status-store";
import { useEndpointCatalogStore } from "@/stores/endpoint-catalog-store";

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

function applyAuthStatus(payload: {
  enabled: boolean;
  registration_enabled: boolean;
  google_enabled?: boolean;
  google_client_id?: string | null;
}): void {
  const googleEnabled = payload.google_enabled === true && typeof payload.google_client_id === "string" && payload.google_client_id.length > 0;
  useAuthStore.setState({
    registrationEnabled: payload.registration_enabled,
    googleEnabled,
    googleClientId: googleEnabled ? payload.google_client_id ?? null : null,
  });
  if (!payload.enabled) {
    useAuthStore.setState({ isAuthenticated: true });
  }
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
      // Still fetch status so Google button / registration flags are available if user logs out.
      fetch("/api/v1/auth/status")
        .then(async (res) => {
          if (!res.ok) return;
          const payload: unknown = await res.json();
          if (
            typeof payload === "object" &&
            payload !== null &&
            typeof (payload as { enabled?: unknown }).enabled === "boolean" &&
            typeof (payload as { registration_enabled?: unknown }).registration_enabled === "boolean"
          ) {
            applyAuthStatus(payload as {
              enabled: boolean;
              registration_enabled: boolean;
              google_enabled?: boolean;
              google_client_id?: string | null;
            });
          }
        })
        .catch(() => {
          /* ignore */
        });
      return;
    }
    // 无 token 时先问后端是否启用了鉴权。`AUTH_ENABLED=false` 时后端全链路
    // bypass，前端也应该跳过登录页直接进主界面。超时 / 网络异常 / 响应 shape
    // 异常时 fail-closed 退回到登录页，避免误把损坏响应当成"无需鉴权"放行。
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    fetch("/api/v1/auth/status", { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(`status ${res.status}`);
        const payload: unknown = await res.json();
        if (
          typeof payload !== "object" ||
          payload === null ||
          typeof (payload as { enabled?: unknown }).enabled !== "boolean" ||
          typeof (payload as { registration_enabled?: unknown }).registration_enabled !== "boolean"
        ) {
          throw new Error("invalid /auth/status payload");
        }
        applyAuthStatus(payload as {
          enabled: boolean;
          registration_enabled: boolean;
          google_enabled?: boolean;
          google_client_id?: string | null;
        });
      })
      .catch((err) => {
        console.warn("[auth] /auth/status fetch failed; defaulting to login", err);
      })
      .finally(() => {
        clearTimeout(timeoutId);
        set({ isLoading: false });
      });
  },

  login: (token, username) => {
    clearMediaTokenCache();
    useAssetsStore.getState().reset();
    useConfigStatusStore.getState().reset();
    useEndpointCatalogStore.getState().reset();
    saveToken(token);
    set({ token, username, isAuthenticated: true, isLoading: false });
  },

  logout: () => {
    clearToken();
    clearMediaTokenCache();
    useAssetsStore.getState().reset();
    useConfigStatusStore.getState().reset();
    useEndpointCatalogStore.getState().reset();
    set({ token: null, username: null, isAuthenticated: false });
  },

  setLoading: (isLoading) => set({ isLoading }),
}));
