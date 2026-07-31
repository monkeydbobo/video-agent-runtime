import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
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
  afterEach(() => {
    vi.unstubAllGlobals();
  });

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
    const sources = expandButton.querySelectorAll("source");
    expect(sources).toHaveLength(2);
    expect(sources[0]).toHaveAttribute(
      "src",
      "https://s15-sl.cybercut.ai/kos/s101/nlav112623/oioi_demo_web_vp9.webm",
    );
    expect(sources[1]).toHaveAttribute(
      "src",
      "https://s15-sl.cybercut.ai/kos/s101/nlav112623/oioi_demo_web_h264.mp4",
    );
    fireEvent.click(expandButton);

    expect(container.querySelector(".landing-page")).toHaveClass("landing-page--hero-video");
    expect(container.querySelector(".landing-particles")).not.toBeInTheDocument();
  });

  it("defers the below-fold showreel until it enters the viewport", () => {
    let callback: IntersectionObserverCallback | undefined;
    class MockIntersectionObserver implements IntersectionObserver {
      readonly root = null;
      readonly rootMargin = "0px";
      readonly scrollMargin = "0px";
      readonly thresholds = [0.25];

      constructor(nextCallback: IntersectionObserverCallback) {
        callback = nextCallback;
      }

      disconnect() {}
      observe() {}
      takeRecords(): IntersectionObserverEntry[] { return []; }
      unobserve() {}
    }
    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);

    const { container } = renderLandingPage();
    const showreel = container.querySelector(".landing-player video");
    expect(showreel).not.toHaveAttribute("src");
    expect(showreel).toHaveAttribute("preload", "none");
    expect(screen.queryByRole("link", { name: /如何组织 AI 视频工作流/ })).not.toBeInTheDocument();

    act(() => {
      callback?.([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver);
    });

    expect(showreel).toHaveAttribute("src", "/showreel/elephants-dream-1.mp4");
    expect(showreel).toHaveAttribute("preload", "auto");
  });
});
