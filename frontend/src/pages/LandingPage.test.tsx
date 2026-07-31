import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { LandingPage } from "@/pages/LandingPage";

function renderLandingPage() {
  const memory = memoryLocation({ path: "/", record: true });
  return render(
    <Router hook={memory.hook}>
      <LandingPage />
    </Router>,
  );
}

describe("LandingPage hero video", () => {
  it("starts as the hero background, restores the original effects, and expands again", () => {
    const { container } = renderLandingPage();

    const restoreButton = screen.getByRole("button", { name: "退出首屏视频并恢复初始效果" });
    expect(container.querySelector(".landing-page")).toHaveClass("landing-page--hero-video");
    expect(container.querySelector(".landing-particles")).not.toBeInTheDocument();
    expect(container.querySelector(".hero-atmosphere")).not.toBeInTheDocument();
    expect(restoreButton.querySelector("video")).toHaveAttribute("loop");

    fireEvent.click(restoreButton);

    expect(container.querySelector(".landing-page")).not.toHaveClass("landing-page--hero-video");
    expect(container.querySelector(".landing-particles")).toBeInTheDocument();
    expect(container.querySelector(".hero-atmosphere")).toBeInTheDocument();

    const expandButton = screen.getByRole("button", { name: "将演示视频铺满首屏播放" });
    expect(expandButton.querySelector("video")).toHaveAttribute(
      "src",
      "https://media.oioi.bio/api/v1/static-media/oioi_demo_oioi_bio.mp4",
    );
    fireEvent.click(expandButton);

    expect(container.querySelector(".landing-page")).toHaveClass("landing-page--hero-video");
    expect(container.querySelector(".landing-particles")).not.toBeInTheDocument();
  });
});
