// @author wanghaobo

/** FastAPI validation / HTTPException detail item. */
export interface AuthErrorDetailItem {
  loc?: Array<string | number>;
  msg?: string;
  type?: string;
  ctx?: { min_length?: number; max_length?: number };
}

export type AuthErrorDetail = string | AuthErrorDetailItem[] | undefined;

type Translate = (key: string, options?: Record<string, unknown>) => string;

function fieldFromLoc(loc: Array<string | number> | undefined): string | null {
  if (!loc || loc.length === 0) return null;
  // Typical FastAPI loc: ["body", "username"] or ["body", "password"]
  for (let i = loc.length - 1; i >= 0; i--) {
    const part = loc[i];
    if (typeof part === "string" && part !== "body" && part !== "query" && part !== "path") {
      return part;
    }
  }
  return null;
}

function messageForItem(item: AuthErrorDetailItem, t: Translate): string {
  const field = fieldFromLoc(item.loc);
  const fieldLabel =
    field === "username"
      ? t("auth:username")
      : field === "password"
        ? t("auth:password")
        : field === "confirm_password"
          ? t("auth:confirm_password")
          : field === "id_token"
            ? t("auth:continue_with_google")
            : field ?? "";

  switch (item.type) {
    case "string_too_short": {
      const min = item.ctx?.min_length;
      if (field === "username") return t("auth:validation_username_too_short", { min: min ?? 3 });
      if (field === "password") return t("auth:validation_password_too_short", { min: min ?? 8 });
      return t("auth:validation_too_short", { field: fieldLabel, min: min ?? 1 });
    }
    case "string_too_long": {
      const max = item.ctx?.max_length;
      if (field === "username") return t("auth:validation_username_too_long", { max: max ?? 64 });
      if (field === "password") return t("auth:validation_password_too_long", { max: max ?? 128 });
      return t("auth:validation_too_long", { field: fieldLabel, max: max ?? 1 });
    }
    case "string_pattern_mismatch":
      if (field === "username") return t("auth:validation_username_pattern");
      return t("auth:validation_pattern", { field: fieldLabel });
    case "missing":
      return t("auth:validation_required", { field: fieldLabel || t("auth:username") });
    default:
      if (typeof item.msg === "string" && item.msg.trim()) {
        return fieldLabel ? `${fieldLabel}: ${item.msg}` : item.msg;
      }
      return t("auth:registration_failed");
  }
}

/**
 * Turn FastAPI `detail` (string or validation array) into a user-facing message.
 */
export function formatAuthErrorDetail(
  detail: AuthErrorDetail,
  t: Translate,
  fallbackKey = "auth:registration_failed",
): string {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const messages = detail.map((item) => messageForItem(item, t)).filter(Boolean);
    if (messages.length > 0) {
      // Deduplicate while preserving order
      return [...new Set(messages)].join("；");
    }
  }
  return t(fallbackKey);
}

/** Map validation items to per-field messages for inline form errors. */
export function fieldErrorsFromDetail(
  detail: AuthErrorDetail,
  t: Translate,
): Partial<Record<"username" | "password" | "confirm_password" | "form", string>> {
  if (typeof detail === "string" && detail.trim()) {
    return { form: detail };
  }
  if (!Array.isArray(detail)) {
    return {};
  }
  const out: Partial<Record<"username" | "password" | "confirm_password" | "form", string>> = {};
  for (const item of detail) {
    const field = fieldFromLoc(item.loc);
    const msg = messageForItem(item, t);
    if (field === "username" || field === "password" || field === "confirm_password") {
      if (!out[field]) out[field] = msg;
    } else if (!out.form) {
      out.form = msg;
    }
  }
  return out;
}
