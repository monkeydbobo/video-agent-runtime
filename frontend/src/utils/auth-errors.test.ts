// @author wanghaobo

import { describe, expect, it } from "vitest";
import { formatAuthErrorDetail } from "@/utils/auth-errors";

const t = (key: string, options?: Record<string, unknown>) => {
  if (key === "auth:username_too_short") return `用户名至少 ${options?.min ?? 3} 位`;
  if (key === "auth:password_too_short") return `密码至少 ${options?.min ?? 8} 位`;
  if (key === "auth:username_invalid_format") return "用户名格式无效";
  if (key === "auth:registration_failed") return "注册失败";
  if (key === "auth:validation_failed") return "校验失败";
  return key;
};

describe("formatAuthErrorDetail", () => {
  it("returns string detail as-is", () => {
    const result = formatAuthErrorDetail("该用户名已被占用", t, "auth:registration_failed");
    expect(result.message).toBe("该用户名已被占用");
    expect(result.fields.form).toBe("该用户名已被占用");
  });

  it("maps 422 array items to field messages", () => {
    const result = formatAuthErrorDetail(
      [
        {
          type: "string_pattern_mismatch",
          loc: ["body", "username"],
          msg: "String should match pattern",
        },
        {
          type: "string_too_short",
          loc: ["body", "password"],
          msg: "String should have at least 8 characters",
          ctx: { min_length: 8 },
        },
      ],
      t,
      "auth:registration_failed",
    );
    expect(result.fields.username).toBe("用户名格式无效");
    expect(result.fields.password).toBe("密码至少 8 位");
    expect(result.message).toContain("用户名格式无效");
    expect(result.message).toContain("密码至少 8 位");
  });

  it("falls back when detail is missing", () => {
    const result = formatAuthErrorDetail(undefined, t, "auth:registration_failed");
    expect(result.message).toBe("注册失败");
  });
});
