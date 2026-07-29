// @author wanghaobo

import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GoogleSignInButton } from "@/components/auth/GoogleSignInButton";
import { useAuthStore } from "@/stores/auth-store";

describe("GoogleSignInButton", () => {
  beforeEach(() => {
    useAuthStore.setState({
      googleEnabled: false,
      googleClientId: null,
    });
  });

  it("renders nothing when Google login is disabled", () => {
    const { queryByTestId } = render(
      <GoogleSignInButton onSuccess={vi.fn()} onError={vi.fn()} />,
    );
    expect(queryByTestId("google-sign-in")).toBeNull();
  });

  it("renders host when Google login is enabled", () => {
    useAuthStore.setState({
      googleEnabled: true,
      googleClientId: "example.apps.googleusercontent.com",
    });
    const { getByTestId } = render(
      <GoogleSignInButton onSuccess={vi.fn()} onError={vi.fn()} />,
    );
    expect(getByTestId("google-sign-in")).toBeInTheDocument();
  });
});
