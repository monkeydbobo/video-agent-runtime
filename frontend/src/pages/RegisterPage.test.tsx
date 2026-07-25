import { fireEvent, render } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
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
