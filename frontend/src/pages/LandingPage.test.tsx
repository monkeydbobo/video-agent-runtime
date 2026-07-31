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

  it("keeps the poster-first hero until the user expands the decorative video", () => {
    const { container } = renderLandingPage();

    expect(container.querySelector(".landing-page")).not.toHaveClass("landing-page--hero-video");
    expect(container.querySelector(".landing-particles")).toBeInTheDocument();
    expect(container.querySelector(".hero-atmosphere")).toBeInTheDocument();

    const expandButton = screen.getByRole("button", { name: "将演示视频铺满首屏播放" });
    // 首屏默认不挂 source；交互或空闲后才注入，避免抢 LCP。
    expect(expandButton.querySelectorAll("source")).toHaveLength(0);

    fireEvent.click(expandButton);

    expect(container.querySelector(".landing-page")).toHaveClass("landing-page--hero-video");
    const navigation = screen.getByRole("navigation", { name: "主导航" });
    expect(navigation).toHaveClass("landing-nav--immersive");
    expect(container.querySelector(".landing-particles")).not.toBeInTheDocument();

    const videoBackdrop = container.querySelector(".landing-hero__video-backdrop");
    const heroVideo = videoBackdrop?.querySelector("video") as HTMLVideoElement;
    expect(heroVideo).toHaveAttribute("loop");
    expect(heroVideo.muted).toBe(true);

    const sources = heroVideo.querySelectorAll("source");
    expect(sources).toHaveLength(2);
    expect(sources[0]).toHaveAttribute(
      "src",
      "https://s15-sl.cybercut.ai/kos/s101/nlav112623/oioi_demo_web_vp9_audio.webm",
    );

    const soundButton = screen.getByRole("button", { name: "打开声音" });
    fireEvent.click(soundButton);
    expect(heroVideo.muted).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "退出首屏视频并恢复初始效果" }));
    expect(container.querySelector(".landing-page")).not.toHaveClass("landing-page--hero-video");
    expect(container.querySelector(".landing-particles")).toBeInTheDocument();
  });

  it("exposes crawlable language links instead of in-place locale toggles", () => {
    renderLandingPage();
    expect(screen.getByRole("link", { name: "中" })).toHaveAttribute("href", "/zh");
    expect(screen.getByRole("link", { name: "EN" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "登录" })).toHaveAttribute("href", "/login");
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
      takeRecords(): IntersectionObserverEntry[] {
        return [];
      }
      unobserve() {}
    }
    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);

    const { container } = renderLandingPage();
    const showreel = container.querySelector(".landing-player video");
    expect(showreel).not.toHaveAttribute("src");
    expect(showreel).toHaveAttribute("preload", "none");

    act(() => {
      callback?.([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver);
    });

    expect(showreel).toHaveAttribute("src", "/showreel/elephants-dream-1.mp4");
    expect(showreel).toHaveAttribute("preload", "auto");
  });
});
