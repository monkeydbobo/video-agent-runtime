import { useEffect, useState, type FormEvent } from "react";
import { Loader2 } from "lucide-react";
import { useLocation, useSearch } from "wouter";
import { useTranslation } from "react-i18next";
import { useAutoFocus } from "@/hooks/useAutoFocus";
import { useAuthStore } from "@/stores/auth-store";
import { errMsg, voidPromise } from "@/utils/async";
import { safeReturnPath } from "@/utils/safe-url";
import type { ErrorResponse, LoginResponse } from "@/api";
import { FieldLabel } from "@/components/ui/FieldLabel";
import {
  ACCENT_BTN_CLS,
  ACCENT_BUTTON_STYLE,
  CARD_STYLE,
  INPUT_CLS,
  ambientGlowStyle,
  posterGridStyle,
} from "@/components/ui/darkroom-tokens";

const POSTER_GRID_STYLE = posterGridStyle({ size: 44, maskShape: "60% 60% at 50% 35%", opacity: 0.05 });
const AMBIENT_GLOW_STYLE = ambientGlowStyle();

export function RegisterPage() {
  const { t, i18n } = useTranslation(["common", "auth"]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [, setLocation] = useLocation();
  const search = useSearch();
  const login = useAuthStore((s) => s.login);
  const usernameRef = useAutoFocus<HTMLInputElement>();

  useEffect(() => {
    const prev = document.title;
    document.title = t("auth:register");
    return () => { document.title = prev; };
  }, [t]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (password !== confirmPassword) {
      setError(t("auth:password_mismatch"));
      return;
    }
    setLoading(true);
    try {
      const resp = await fetch("/api/v1/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept-Language": i18n.language || "zh" },
        body: JSON.stringify({ username, password }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({})) as Partial<ErrorResponse>;
        throw new Error(typeof data.detail === "string" ? data.detail : t("auth:registration_failed"));
      }
      const data = await resp.json() as LoginResponse;
      login(data.access_token, username);
      const returnTo = safeReturnPath(new URLSearchParams(search).get("from"));
      setLocation(returnTo ?? "/app/projects");
    } catch (err) {
      setError(errMsg(err, t("auth:registration_failed")));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div data-testid="register-page" className="relative flex min-h-screen items-center justify-center overflow-hidden bg-bg px-4 text-text">
      <div aria-hidden className="pointer-events-none absolute inset-0" style={AMBIENT_GLOW_STYLE} />
      <div aria-hidden className="pointer-events-none absolute inset-0" style={POSTER_GRID_STYLE} />
      <div className="relative w-full max-w-sm overflow-hidden rounded-2xl border border-hairline p-8 shadow-2xl" style={CARD_STYLE}>
        <div className="mb-6 text-center">
          <div className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-text-4">system · register</div>
          <h1 className="font-editorial mt-1 text-[28px] tracking-tight text-text">{t("auth:register")}</h1>
        </div>
        <form onSubmit={voidPromise(handleSubmit)} className="space-y-4">
          <div>
            <FieldLabel htmlFor="register-username" required>{t("auth:username")}</FieldLabel>
            <input id="register-username" type="text" autoComplete="username" spellCheck={false} value={username} onChange={(e) => setUsername(e.target.value)} className={INPUT_CLS} ref={usernameRef} minLength={3} maxLength={64} required />
          </div>
          <div>
            <FieldLabel htmlFor="register-password" required>{t("auth:password")}</FieldLabel>
            <input id="register-password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} className={INPUT_CLS} minLength={8} maxLength={128} required />
          </div>
          <div>
            <FieldLabel htmlFor="register-confirm-password" required>{t("auth:confirm_password")}</FieldLabel>
            <input id="register-confirm-password" type="password" autoComplete="new-password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} className={INPUT_CLS} minLength={8} maxLength={128} required />
          </div>
          {error && <p role="alert" aria-live="polite" className="text-sm text-warm-bright">{error}</p>}
          <button type="submit" disabled={loading} className={`${ACCENT_BTN_CLS} w-full justify-center`} style={ACCENT_BUTTON_STYLE}>
            {loading && <Loader2 aria-hidden className="h-4 w-4 motion-safe:animate-spin" />}
            {loading ? t("auth:registering") : t("auth:register")}
          </button>
          <button type="button" onClick={() => setLocation(`/login${search}`)} className="w-full text-sm text-text-3 transition-colors hover:text-text">
            {t("auth:already_have_account")}
          </button>
        </form>
      </div>
    </div>
  );
}
