// @author wanghaobo

import { useState, type FormEvent } from "react";
import { Loader2 } from "lucide-react";
import { useLocation, useSearch } from "wouter";
import { useTranslation } from "react-i18next";
import { useAutoFocus } from "@/hooks/useAutoFocus";
import { useAuthStore } from "@/stores/auth-store";
import { errMsg, voidPromise } from "@/utils/async";
import { safeReturnPath } from "@/utils/safe-url";
import { fieldErrorsFromDetail, formatAuthErrorDetail } from "@/utils/auth-errors";
import type { ErrorResponse, LoginResponse } from "@/api";
import { AuthPageShell } from "@/components/auth/AuthPageShell";
import { GoogleSignInButton } from "@/components/auth/GoogleSignInButton";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { ACCENT_BTN_CLS, ACCENT_BUTTON_STYLE, INPUT_CLS } from "@/components/ui/darkroom-tokens";

export function RegisterPage() {
  const { t, i18n } = useTranslation(["common", "auth"]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<"username" | "password" | "confirm_password", string>>>({});
  const [loading, setLoading] = useState(false);
  const [, setLocation] = useLocation();
  const search = useSearch();
  const login = useAuthStore((s) => s.login);
  const usernameRef = useAutoFocus<HTMLInputElement>();

  const goAfterAuth = (token: string, name: string) => {
    login(token, name);
    const returnTo = safeReturnPath(new URLSearchParams(search).get("from"));
    setLocation(returnTo ?? "/app/projects");
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setFieldErrors({});
    if (password !== confirmPassword) {
      setFieldErrors({ confirm_password: t("auth:password_mismatch") });
      setError(t("auth:password_mismatch"));
      return;
    }
    setLoading(true);
    try {
      const resp = await fetch("/api/v1/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept-Language": i18n.language || "en" },
        body: JSON.stringify({ username, password }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({})) as Partial<ErrorResponse>;
        const mapped = fieldErrorsFromDetail(data.detail, t);
        setFieldErrors({
          username: mapped.username,
          password: mapped.password,
          confirm_password: mapped.confirm_password,
        });
        throw new Error(formatAuthErrorDetail(data.detail, t, "auth:registration_failed"));
      }
      const data = await resp.json() as LoginResponse;
      goAfterAuth(data.access_token, username);
    } catch (err) {
      setError(errMsg(err, t("auth:registration_failed")));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div data-testid="register-page">
      <AuthPageShell canonicalPath="/register" pageTitle={t("auth:register")}>
        <form onSubmit={voidPromise(handleSubmit)} className="space-y-4">
          <div>
            <FieldLabel htmlFor="register-username" required>{t("auth:username")}</FieldLabel>
            <input
              id="register-username"
              type="text"
              autoComplete="username"
              spellCheck={false}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className={INPUT_CLS}
              ref={usernameRef}
              minLength={3}
              maxLength={64}
              required
              aria-invalid={Boolean(fieldErrors.username)}
              aria-describedby={fieldErrors.username ? "register-username-error" : undefined}
            />
            {fieldErrors.username ? (
              <p id="register-username-error" className="mt-1 text-sm text-warm-bright">{fieldErrors.username}</p>
            ) : null}
          </div>
          <div>
            <FieldLabel htmlFor="register-password" required>{t("auth:password")}</FieldLabel>
            <input
              id="register-password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={INPUT_CLS}
              minLength={8}
              maxLength={128}
              required
              aria-invalid={Boolean(fieldErrors.password)}
              aria-describedby={fieldErrors.password ? "register-password-error" : undefined}
            />
            {fieldErrors.password ? (
              <p id="register-password-error" className="mt-1 text-sm text-warm-bright">{fieldErrors.password}</p>
            ) : null}
          </div>
          <div>
            <FieldLabel htmlFor="register-confirm-password" required>{t("auth:confirm_password")}</FieldLabel>
            <input
              id="register-confirm-password"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className={INPUT_CLS}
              minLength={8}
              maxLength={128}
              required
              aria-invalid={Boolean(fieldErrors.confirm_password)}
              aria-describedby={fieldErrors.confirm_password ? "register-confirm-password-error" : undefined}
            />
            {fieldErrors.confirm_password ? (
              <p id="register-confirm-password-error" className="mt-1 text-sm text-warm-bright">{fieldErrors.confirm_password}</p>
            ) : null}
          </div>
          {error && <p role="alert" aria-live="polite" className="text-sm text-warm-bright">{error}</p>}
          <button type="submit" disabled={loading} className={`${ACCENT_BTN_CLS} w-full justify-center`} style={ACCENT_BUTTON_STYLE}>
            {loading && <Loader2 aria-hidden className="h-4 w-4 motion-safe:animate-spin" />}
            {loading ? t("auth:registering") : t("auth:register")}
          </button>
          <GoogleSignInButton
            disabled={loading}
            onSuccess={goAfterAuth}
            onError={(message) => setError(message)}
          />
          <button
            type="button"
            onClick={() => setLocation(search ? `/login?${search}` : "/login")}
            className="w-full rounded-md py-1 text-sm text-text-3 transition-colors hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            {t("auth:already_have_account")}
          </button>
        </form>
      </AuthPageShell>
    </div>
  );
}
