import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { LogoutButton } from "@/components/auth/LogoutButton";
import { useAuthStore } from "@/stores/auth-store";

describe("LogoutButton", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("arcreel_auth_token", "test-token");
    useAuthStore.setState({
      token: "test-token",
      username: "alice",
      isAuthenticated: true,
      isLoading: false,
    });
  });

  it("clears authentication and returns to the login page", () => {
    const memory = memoryLocation({ path: "/app/projects", record: true });
    render(
      <Router hook={memory.hook}>
        <LogoutButton />
      </Router>,
    );

    fireEvent.click(screen.getByRole("button", { name: "退出登录" }));

    expect(useAuthStore.getState()).toMatchObject({
      token: null,
      username: null,
      isAuthenticated: false,
    });
    expect(localStorage.getItem("arcreel_auth_token")).toBeNull();
    expect(memory.history.at(-1)).toBe("/login");
  });
});
