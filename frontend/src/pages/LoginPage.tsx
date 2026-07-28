import { useState, type FormEvent } from "react";
import { Loader2 } from "lucide-react";
import { useAutoFocus } from "@/hooks/useAutoFocus";
import { errMsg, voidPromise } from "@/utils/async";
import { useLocation, useSearch } from "wouter";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "@/stores/auth-store";
import { safeReturnPath } from "@/utils/safe-url";
import type { LoginResponse, ErrorResponse } from "@/api";
import { AuthPageShell } from "@/components/auth/AuthPageShell";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { ACCENT_BTN_CLS, ACCENT_BUTTON_STYLE, INPUT_CLS } from "@/components/ui/darkroom-tokens";

export function LoginPage() {
  const { t, i18n } = useTranslation(["common", "auth"]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [, setLocation] = useLocation();
  const search = useSearch();
  const login = useAuthStore((s) => s.login);
  const registrationEnabled = useAuthStore((s) => s.registrationEnabled);
  const usernameRef = useAutoFocus<HTMLInputElement>();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const body = new URLSearchParams({
        username,
        password,
        grant_type: "password",
      });
      const resp = await fetch("/api/v1/auth/token", {
        method: "POST",
        headers: {
          "Accept-Language": i18n.language || "zh",
        },
        body,
      });

      if (!resp.ok) {
        const data = await resp.json().catch(() => ({})) as Partial<ErrorResponse>;
        const detail = data.detail;
        throw new Error(typeof detail === "string" ? detail : t("auth:login_failed"));
      }

      const data = await resp.json() as LoginResponse;
      login(data.access_token, username);
      // 登录成功后回跳到进入登录页前的原始地址（由 AuthGuard / 401 拦截以 ?from 传入），
      // 经 safeReturnPath 校验为站内安全路径；非法或缺失时回退到项目列表。
      const returnTo = safeReturnPath(new URLSearchParams(search).get("from"));
      setLocation(returnTo ?? "/app/projects");
    } catch (err) {
      setError(errMsg(err, t("auth:login_failed")));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div data-testid="login-page">
      <AuthPageShell canonicalPath="/login" pageTitle={t("auth:login")}>
        <form onSubmit={voidPromise(handleSubmit)} className="space-y-4">
          <div>
            <FieldLabel htmlFor="login-username" required>
              {t("auth:username")}
            </FieldLabel>
            <input
              id="login-username"
              type="text"
              autoComplete="username"
              spellCheck={false}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className={INPUT_CLS}
              ref={usernameRef}
              required
            />
          </div>

          <div>
            <FieldLabel htmlFor="login-password" required>
              {t("auth:password")}
            </FieldLabel>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={INPUT_CLS}
              required
            />
          </div>

          {error && (
            <p role="alert" aria-live="polite" className="text-sm text-warm-bright">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className={`${ACCENT_BTN_CLS} w-full justify-center`}
            style={ACCENT_BUTTON_STYLE}
          >
            {loading && <Loader2 aria-hidden className="h-4 w-4 motion-safe:animate-spin" />}
            {loading ? t("auth:logging_in") : t("auth:login")}
          </button>

          {registrationEnabled ? (
            <button
              type="button"
              onClick={() => setLocation(search ? `/register?${search}` : "/register")}
              className="w-full rounded-md py-1 text-sm text-text-3 transition-colors hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              {t("auth:no_account_register")}
            </button>
          ) : null}
        </form>
      </AuthPageShell>
    </div>
  );
}
