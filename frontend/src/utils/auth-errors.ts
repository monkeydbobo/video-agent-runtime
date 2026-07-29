// @author wanghaobo

/** FastAPI / Pydantic validation error item (422). */
export interface FastApiErrorItem {
  loc?: (string | number)[];
  msg?: string;
  type?: string;
  ctx?: Record<string, unknown>;
}

export interface AuthFieldErrors {
  username?: string;
  password?: string;
  form?: string;
}

export interface FormattedAuthError {
  /** Single message suitable for a top-level alert. */
  message: string;
  /** Per-field messages for inline display. */
  fields: AuthFieldErrors;
}

type Translate = (key: string, options?: Record<string, unknown>) => string;

function fieldFromLoc(loc: (string | number)[] | undefined): "username" | "password" | null {
  if (!loc?.length) return null;
  const last = loc[loc.length - 1];
  if (last === "username") return "username";
  if (last === "password") return "password";
  return null;
}

function messageForItem(item: FastApiErrorItem, field: "username" | "password" | null, t: Translate): string {
  const type = item.type ?? "";
  const ctx = item.ctx ?? {};

  if (type === "string_too_short") {
    if (field === "username") {
      return t("auth:username_too_short", { min: Number(ctx.min_length) || 3 });
    }
    if (field === "password") {
      return t("auth:password_too_short", { min: Number(ctx.min_length) || 8 });
    }
  }
  if (type === "string_too_long") {
    if (field === "username") {
      return t("auth:username_too_long", { max: Number(ctx.max_length) || 64 });
    }
    if (field === "password") {
      return t("auth:password_too_long", { max: Number(ctx.max_length) || 128 });
    }
  }
  if (type === "string_pattern_mismatch" && field === "username") {
    return t("auth:username_invalid_format");
  }
  if (type === "missing") {
    if (field === "username") return t("auth:username_required");
    if (field === "password") return t("auth:password_required");
  }

  if (typeof item.msg === "string" && item.msg.trim()) {
    return item.msg;
  }
  return t("auth:validation_failed");
}

/**
 * Parse FastAPI `detail` (string or 422 array) into a readable auth error.
 * String details from the backend are already localized via Accept-Language.
 */
export function formatAuthErrorDetail(
  detail: unknown,
  t: Translate,
  fallbackKey: "auth:login_failed" | "auth:registration_failed" | "auth:google_login_failed",
): FormattedAuthError {
  if (typeof detail === "string" && detail.trim()) {
    return { message: detail, fields: { form: detail } };
  }

  if (!Array.isArray(detail) || detail.length === 0) {
    const message = t(fallbackKey);
    return { message, fields: { form: message } };
  }

  const fields: AuthFieldErrors = {};
  const messages: string[] = [];

  for (const raw of detail) {
    if (!raw || typeof raw !== "object") continue;
    const item = raw as FastApiErrorItem;
    const field = fieldFromLoc(item.loc);
    const text = messageForItem(item, field, t);
    if (field === "username" && !fields.username) fields.username = text;
    else if (field === "password" && !fields.password) fields.password = text;
    else if (!field && !fields.form) fields.form = text;
    if (!messages.includes(text)) messages.push(text);
  }

  if (messages.length === 0) {
    const message = t(fallbackKey);
    return { message, fields: { form: message } };
  }

  return { message: messages.join("；"), fields };
}
