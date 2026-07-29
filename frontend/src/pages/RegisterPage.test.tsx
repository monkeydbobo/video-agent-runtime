import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { RegisterPage } from "@/pages/RegisterPage";
import { useAuthStore } from "@/stores/auth-store";

// wouter useSearch() 返回 ? 之后的内容（不含 ?）。注册→登录互跳必须自行补上 ?，
// 否则 /register?from=... 点「已有账号」会拼成 /loginfrom=...，落入 SPA 404。
function renderRegisterAt(path: string) {
  const memory = memoryLocation({ path, record: true });
  const view = render(
    <Router hook={memory.hook}>
      <RegisterPage />
    </Router>,
  );
  return { ...view, history: memory.history };
}

describe("RegisterPage ↔ LoginPage cross-nav preserves query", () => {
  beforeEach(() => {
    useAuthStore.setState({
      token: null,
      username: null,
      isAuthenticated: false,
      isLoading: false,
      googleEnabled: false,
      googleClientId: null,
    });
  });

  it("navigates to /login?from=... when search is present", () => {
    const { getByRole, history } = renderRegisterAt("/register?from=%2Fapp%2Fprojects");
    fireEvent.click(getByRole("button", { name: "已有账号？去登录" }));
    expect(history.at(-1)).toBe("/login?from=%2Fapp%2Fprojects");
  });

  it("navigates to /login when search is empty", () => {
    const { getByRole, history } = renderRegisterAt("/register");
    fireEvent.click(getByRole("button", { name: "已有账号？去登录" }));
    expect(history.at(-1)).toBe("/login");
  });
});

describe("RegisterPage brand identity", () => {
  it("identifies oioi.bio and marks the registration page as non-indexable", () => {
    const { getByRole, getByText } = renderRegisterAt("/register");

    expect(getByRole("img", { name: "oioi.bio 猫咪标识" })).toHaveAttribute(
      "src",
      "/android-chrome-192x192.png",
    );
    expect(getByText("从故事、分镜到会动的画面，都在这里完成。")).toBeInTheDocument();
    expect(document.title).toBe("注册账号 — oioi.bio");
    expect(document.querySelector('meta[name="robots"]')).toHaveAttribute(
      "content",
      "noindex, nofollow, noarchive",
    );
    expect(document.querySelector('link[rel="canonical"]')).toHaveAttribute(
      "href",
      "http://localhost:3000/register",
    );
  });
});

describe("RegisterPage validation errors", () => {
  beforeEach(() => {
    useAuthStore.setState({
      token: null,
      username: null,
      isAuthenticated: false,
      isLoading: false,
      googleEnabled: false,
      googleClientId: null,
    });
    vi.unstubAllGlobals();
  });

  it("shows field-level messages from 422 detail arrays", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        json: async () => ({
          detail: [
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
        }),
      }),
    );

    const { container, getByRole } = renderRegisterAt("/register");
    fireEvent.change(container.querySelector<HTMLInputElement>("#register-username")!, {
      target: { value: "alice" },
    });
    fireEvent.change(container.querySelector<HTMLInputElement>("#register-password")!, {
      target: { value: "password1" },
    });
    fireEvent.change(container.querySelector<HTMLInputElement>("#register-confirm-password")!, {
      target: { value: "password1" },
    });
    fireEvent.submit(container.querySelector("form")!);

    await waitFor(() => {
      expect(container.querySelector("#register-username-error")).toHaveTextContent(
        /用户名须以字母或数字开头/,
      );
      expect(container.querySelector("#register-password-error")).toHaveTextContent(/密码至少 8 位/);
      expect(getByRole("alert")).toHaveTextContent(/用户名须以字母或数字开头/);
      expect(getByRole("alert")).toHaveTextContent(/密码至少 8 位/);
    });
  });
});
