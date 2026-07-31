// @author wanghaobo

import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "@/stores/auth-store";
import { formatAuthErrorDetail } from "@/utils/auth-errors";
import { errMsg } from "@/utils/async";
import { loadGisScript } from "@/utils/gis-loader";
import type { ErrorResponse, LoginResponse } from "@/api";

const GIS_LOCALES: Record<string, string> = {
  zh: "zh_CN",
  en: "en",
  vi: "vi",
};

function gisLocale(language: string): string {
  return GIS_LOCALES[language.split("-", 1)[0]] ?? "en";
}

interface GoogleSignInButtonProps {
  disabled?: boolean;
  onSuccess: (token: string, username: string) => void;
  onError: (message: string) => void;
}

export function GoogleSignInButton({ disabled = false, onSuccess, onError }: GoogleSignInButtonProps) {
  const { t, i18n } = useTranslation("auth");
  const googleEnabled = useAuthStore((s) => s.googleEnabled);
  const googleClientId = useAuthStore((s) => s.googleClientId);
  const buttonHostRef = useRef<HTMLDivElement>(null);
  const onSuccessRef = useRef(onSuccess);
  const onErrorRef = useRef(onError);

  useEffect(() => {
    onSuccessRef.current = onSuccess;
    onErrorRef.current = onError;
  }, [onSuccess, onError]);

  useEffect(() => {
    if (!googleEnabled || !googleClientId) {
      return;
    }

    let cancelled = false;
    const locale = gisLocale(i18n.language);

    const exchangeCredential = async (credential: string) => {
      try {
        const resp = await fetch("/api/v1/auth/google", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Accept-Language": i18n.language || "en",
          },
          body: JSON.stringify({ id_token: credential }),
        });
        if (!resp.ok) {
          const data = (await resp.json().catch(() => ({}))) as Partial<ErrorResponse>;
          throw new Error(formatAuthErrorDetail(data.detail, t, "auth:google_login_failed"));
        }
        const data = (await resp.json()) as LoginResponse;
        // Username is not returned by /auth/google; resolve via verify for badge consistency.
        let username = "google";
        try {
          const verifyResp = await fetch("/api/v1/auth/verify", {
            headers: { Authorization: `Bearer ${data.access_token}` },
          });
          if (verifyResp.ok) {
            const verifyPayload: unknown = await verifyResp.json();
            if (
              typeof verifyPayload === "object" &&
              verifyPayload !== null &&
              typeof (verifyPayload as { username?: unknown }).username === "string"
            ) {
              username = (verifyPayload as { username: string }).username;
            }
          }
        } catch {
          // Non-fatal: store can hydrate username later.
        }
        onSuccessRef.current(data.access_token, username);
      } catch (err) {
        onErrorRef.current(errMsg(err, t("google_login_failed")));
      }
    };

    void loadGisScript(locale)
      .then(() => {
        if (cancelled || !buttonHostRef.current || !window.google?.accounts?.id) return;
        buttonHostRef.current.innerHTML = "";
        window.google.accounts.id.initialize({
          client_id: googleClientId,
          callback: (response) => {
            if (!response.credential) {
              onErrorRef.current(t("google_login_failed"));
              return;
            }
            void exchangeCredential(response.credential);
          },
          auto_select: false,
          cancel_on_tap_outside: true,
        });
        window.google.accounts.id.renderButton(buttonHostRef.current, {
          type: "standard",
          theme: "outline",
          size: "large",
          text: "continue_with",
          shape: "rectangular",
          width: "100%",
          locale,
        });
      })
      .catch(() => {
        /* GIS unavailable — leave host empty */
      });

    return () => {
      cancelled = true;
    };
  }, [googleEnabled, googleClientId, i18n.language, t]);

  if (!googleEnabled || !googleClientId) {
    return null;
  }

  return (
    <div className="space-y-3" data-testid="google-sign-in">
      <div className="flex items-center gap-3 text-xs text-text-3" aria-hidden>
        <div className="h-px flex-1 bg-hairline" />
        <span>{t("or_continue_with")}</span>
        <div className="h-px flex-1 bg-hairline" />
      </div>
      <div
        ref={buttonHostRef}
        className={`flex min-h-10 w-full justify-center ${disabled ? "pointer-events-none opacity-60" : ""}`}
        aria-label={t("continue_with_google")}
      />
    </div>
  );
}
