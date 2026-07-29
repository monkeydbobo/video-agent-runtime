// @author wanghaobo

import { describe, expect, it } from "vitest";
import { fieldErrorsFromDetail, formatAuthErrorDetail } from "@/utils/auth-errors";

const messages: Record<string, string> = {
  "auth:username": "Username",
  "auth:password": "Password",
  "auth:confirm_password": "Confirm password",
  "auth:continue_with_google": "Continue with Google",
  "auth:registration_failed": "Registration failed",
  "auth:login_failed": "Login failed",
  "auth:validation_username_too_short": "Username must be at least {{min}} characters",
  "auth:validation_password_too_short": "Password must be at least {{min}} characters",
  "auth:validation_username_pattern": "Username pattern invalid",
  "auth:validation_required": "{{field}} is required",
  "auth:validation_too_short": "{{field}} must be at least {{min}} characters",
  "auth:validation_too_long": "{{field}} must be at most {{max}} characters",
  "auth:validation_pattern": "{{field}} format is invalid",
  "auth:validation_username_too_long": "Username must be at most {{max}} characters",
  "auth:validation_password_too_long": "Password must be at most {{max}} characters",
};

function t(key: string, options?: Record<string, unknown>): string {
  let template = messages[key] ?? key;
  if (options) {
    for (const [k, v] of Object.entries(options)) {
      template = template.replace(`{{${k}}}`, String(v));
    }
  }
  return template;
}

describe("formatAuthErrorDetail", () => {
  it("returns string detail as-is", () => {
    expect(formatAuthErrorDetail("该用户名已被占用", t)).toBe("该用户名已被占用");
  });

  it("maps username pattern and password too-short validation items", () => {
    const detail = [
      { loc: ["body", "username"], type: "string_pattern_mismatch", msg: "String should match pattern" },
      { loc: ["body", "password"], type: "string_too_short", msg: "String should have at least 8", ctx: { min_length: 8 } },
    ];
    const message = formatAuthErrorDetail(detail, t);
    expect(message).toContain("Username pattern invalid");
    expect(message).toContain("Password must be at least 8 characters");
  });

  it("falls back when detail is empty", () => {
    expect(formatAuthErrorDetail(undefined, t, "auth:login_failed")).toBe("Login failed");
  });
});

describe("fieldErrorsFromDetail", () => {
  it("assigns messages to username and password fields", () => {
    const errors = fieldErrorsFromDetail(
      [
        { loc: ["body", "username"], type: "string_too_short", ctx: { min_length: 3 } },
        { loc: ["body", "password"], type: "string_too_short", ctx: { min_length: 8 } },
      ],
      t,
    );
    expect(errors.username).toBe("Username must be at least 3 characters");
    expect(errors.password).toBe("Password must be at least 8 characters");
  });

  it("puts plain string detail on form", () => {
    expect(fieldErrorsFromDetail("Registration is currently unavailable", t)).toEqual({
      form: "Registration is currently unavailable",
    });
  });
});
