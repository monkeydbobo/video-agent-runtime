// @author wanghaobo

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GoogleSignInButton } from "@/components/auth/GoogleSignInButton";
import { useAuthStore } from "@/stores/auth-store";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "zh" },
  }),
}));

describe("GoogleSignInButton", () => {
  beforeEach(() => {
    useAuthStore.setState({
      googleEnabled: false,
      googleClientId: null,
    });
  });

  it("renders nothing when Google login is disabled", () => {
    const { container } = render(
      <GoogleSignInButton onSuccess={vi.fn()} onError={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId("google-sign-in")).toBeNull();
  });

  it("renders host when Google login is enabled", () => {
    useAuthStore.setState({
      googleEnabled: true,
      googleClientId: "example.apps.googleusercontent.com",
    });
    render(<GoogleSignInButton onSuccess={vi.fn()} onError={vi.fn()} />);
    expect(screen.getByTestId("google-sign-in")).toBeInTheDocument();
  });
});
