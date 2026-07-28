import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { CurrentUserBadge } from "@/components/auth/CurrentUserBadge";
import { useAuthStore } from "@/stores/auth-store";

describe("CurrentUserBadge", () => {
  beforeEach(() => {
    useAuthStore.setState({
      token: null,
      username: null,
      isAuthenticated: false,
      isLoading: false,
    });
  });

  it("renders nothing when username is missing", () => {
    const { container } = render(<CurrentUserBadge />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the signed-in username", () => {
    useAuthStore.setState({
      token: "tok",
      username: "alice",
      isAuthenticated: true,
    });

    render(<CurrentUserBadge />);

    const badge = screen.getByTestId("current-user-badge");
    expect(badge).toHaveAttribute("aria-label", "当前用户：alice");
    expect(badge).toHaveTextContent("alice");
  });
});
