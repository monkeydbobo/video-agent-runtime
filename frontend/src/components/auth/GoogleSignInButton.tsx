// @author wanghaobo

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ErrorResponse, LoginResponse } from "@/api";
import { useAuthStore } from "@/stores/auth-store";
import { formatAuthErrorDetail } from "@/utils/auth-errors";
import { errMsg } from "@/utils/async";

const GIS_SCRIPT_SRC = "https://accounts.google.com/gsi/client";
const GIS_SCRIPT_ID = "google-gsi-client";

let gisScriptPromise: Promise<void> | null = null;

function loadGisScript(): Promise<void> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("no-window"));
  }
  if (window.google?.accounts?.id) {
    return Promise.resolve();
  }
  if (gisScriptPromise) return gisScriptPromise;

  gisScriptPromise = new Promise((resolve, reject) => {
    const existing = document.getElementById(GIS_SCRIPT_ID) as HTMLScriptElement | null;
    if (existing) {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error("gis-load-failed")), { once: true });
      return;
    }
    const script = document.createElement("script");
    script.id = GIS_SCRIPT_ID;
    script.src = GIS_SCRIPT_SRC;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => {
      gisScriptPromise = null;
      reject(new Error("gis-load-failed"));
    };
    document.head.appendChild(script);
  });
  return gisScriptPromise;
}

interface GoogleSignInButtonProps {
  disabled?: boolean;
  onSuccess: (accessToken: string, username: string) => void;
  onError: (message: string) => void;
}

export function GoogleSignInButton({ disabled = false, onSuccess, onError }: GoogleSignInButtonProps) {
  const { t, i18n } = useTranslation("auth");
  const googleEnabled = useAuthStore((s) => s.googleEnabled);
  const googleClientId = useAuthStore((s) => s.googleClientId);
  const buttonHostRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);
  const onSuccessRef = useRef(onSuccess);
  const onErrorRef = useRef(onError);
  onSuccessRef.current = onSuccess;
  onErrorRef.current = onError;

  useEffect(() => {
    if (!googleEnabled || !googleClientId) return;
    const host = buttonHostRef.current;
    if (!host) return;

    let cancelled = false;

    const exchangeCredential = async (credential: string) => {
      setBusy(true);
      try {
        const resp = await fetch("/api/v1/auth/google", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept-Language": i18n.language || "zh",
          },
          body: JSON.stringify({ id_token: credential }),
        });
        if (!resp.ok) {
          const data = (await resp.json().catch(() => ({}))) as Partial<ErrorResponse>;
          const formatted = formatAuthErrorDetail(data.detail, t, "auth:google_login_failed");
          throw new Error(formatted.message);
        }
        const data = (await resp.json()) as LoginResponse;
        let username = "google";
        try {
          const verifyResp = await fetch("/api/v1/auth/verify", {
            headers: { Authorization: `Bearer ${data.access_token}` },
          });
          if (verifyResp.ok) {
            const payload: unknown = await verifyResp.json();
            if (
              typeof payload === "object" &&
              payload !== null &&
              typeof (payload as { username?: unknown }).username === "string" &&
              (payload as { username: string }).username.length > 0
            ) {
              username = (payload as { username: string }).username;
            }
          }
        } catch {
          // Fall back to placeholder; badge can hydrate later via auth-store.
        }
        onSuccessRef.current(data.access_token, username);
      } catch (err) {
        onErrorRef.current(errMsg(err, t("google_login_failed")));
      } finally {
        setBusy(false);
      }
    };

    void loadGisScript()
      .then(() => {
        if (cancelled || !window.google?.accounts?.id || !buttonHostRef.current) return;
        host.replaceChildren();
        window.google.accounts.id.initialize({
          client_id: googleClientId,
          callback: (response) => {
            if (!response.credential) {
              onErrorRef.current(t("google_login_failed"));
              return;
            }
            void exchangeCredential(response.credential);
          },
          ux_mode: "popup",
          context: "signin",
          use_fedcm_for_prompt: false,
        });
        window.google.accounts.id.renderButton(host, {
          type: "standard",
          theme: "outline",
          size: "large",
          text: "continue_with",
          shape: "rectangular",
          width: host.offsetWidth || 320,
          locale: i18n.language || "zh",
        });
      })
      .catch(() => {
        if (!cancelled) onErrorRef.current(t("google_unavailable"));
      });

    return () => {
      cancelled = true;
      host.replaceChildren();
    };
  }, [googleEnabled, googleClientId, i18n.language, t]);

  if (!googleEnabled || !googleClientId) {
    return null;
  }

  return (
    <div className="space-y-3" data-testid="google-sign-in">
      <div className="flex items-center gap-3 text-xs text-text-3" aria-hidden>
        <div className="h-px flex-1 bg-border" />
        <span>{t("or_continue_with")}</span>
        <div className="h-px flex-1 bg-border" />
      </div>
      <div
        ref={buttonHostRef}
        className={`flex min-h-10 w-full justify-center ${disabled || busy ? "pointer-events-none opacity-60" : ""}`}
        aria-busy={busy}
      />
    </div>
  );
}
