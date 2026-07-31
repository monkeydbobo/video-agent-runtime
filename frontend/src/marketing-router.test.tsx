import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { MarketingRoutes } from "@/marketing-router";
import { useAuthStore } from "@/stores/auth-store";

function renderAt(path: string) {
  const memory = memoryLocation({ path, record: true });
  return render(
    <Router hook={memory.hook}>
      <MarketingRoutes />
    </Router>,
  );
}

describe("MarketingRoutes", () => {
  beforeEach(() => {
    useAuthStore.setState({ isAuthenticated: false, isLoading: false });
  });

  it("renders the public product landing page for signed-out users", async () => {
    renderAt("/");
    expect(await screen.findByRole("heading", { name: /moving picture|会动的画面/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "EN" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "中" })).toHaveAttribute("href", "/zh");
  });

  it("renders a public SEO guide with the product visual language", async () => {
    renderAt("/zh/novel-to-video");
    expect(await screen.findByRole("heading", { name: /变成可以逐镜头制作的影像/ })).toBeInTheDocument();
    expect(document.querySelector(".seo-brand__mark img")).toHaveAttribute("src", "/android-chrome-192x192.png");
    expect(screen.getByRole("link", { name: "EN" })).toHaveAttribute("href", "/en/novel-to-video");
  });

  it("renders 404 for a removed SEO guide", async () => {
    renderAt("/en/ai-video-workflow");
    expect(await screen.findByText("404")).toBeInTheDocument();
  });
});
