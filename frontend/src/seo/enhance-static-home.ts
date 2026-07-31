// @author wanghaobo
// 生产预渲染首页增强：不替换静态正文树，只做认证跳转与装饰视频延迟加载。

import i18n from "i18next";
import { useAuthStore } from "@/stores/auth-store";

const HERO_VIDEO_WEBM = "https://s15-sl.cybercut.ai/kos/s101/nlav112623/oioi_demo_web_vp9_audio.webm";
const HERO_VIDEO_MP4 = "https://s15-sl.cybercut.ai/kos/s101/nlav112623/oioi_demo_web_h264_audio.mp4";

function shouldDeferDecorativeVideo(): boolean {
  if (typeof navigator !== "undefined") {
    const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
    if (connection?.saveData) return true;
  }
  if (typeof window !== "undefined") {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return true;
    if (window.matchMedia?.("(max-width: 768px)").matches) return true;
  }
  return false;
}

function loadHeroVideo(container: Element): void {
  if (container.querySelector("video")) return;
  const video = document.createElement("video");
  video.setAttribute("aria-hidden", "true");
  video.autoplay = true;
  video.loop = true;
  video.muted = true;
  video.playsInline = true;
  video.preload = "metadata";
  video.poster = "/hero/oioi-demo-poster.jpg";
  video.style.width = "100%";
  video.style.height = "100%";
  video.style.objectFit = "cover";
  video.style.borderRadius = "inherit";

  const webm = document.createElement("source");
  webm.src = HERO_VIDEO_WEBM;
  webm.type = 'video/webm; codecs="vp9"';
  const mp4 = document.createElement("source");
  mp4.src = HERO_VIDEO_MP4;
  mp4.type = "video/mp4";
  video.append(webm, mp4);

  const img = container.querySelector("img");
  if (img) img.replaceWith(video);
  else container.append(video);
  void video.play().catch(() => undefined);
}

function scheduleHeroVideo(root: HTMLElement): void {
  const reel = root.querySelector(".landing-reel");
  if (!reel || shouldDeferDecorativeVideo()) return;

  const start = () => loadHeroVideo(reel);
  const onIntent = () => {
    start();
    window.removeEventListener("pointerdown", onIntent);
    window.removeEventListener("keydown", onIntent);
  };

  window.addEventListener("pointerdown", onIntent, { once: true, passive: true });
  window.addEventListener("keydown", onIntent, { once: true });

  const ric = (
    window as Window & {
      requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
    }
  ).requestIdleCallback;
  if (typeof ric === "function") {
    ric(start, { timeout: 4000 });
  } else {
    window.setTimeout(start, 2500);
  }
}

export function enhanceStaticHome(root: HTMLElement): void {
  const locale = root.dataset.homeLocale === "zh" ? "zh" : "en";
  void i18n.changeLanguage(locale);

  const { isAuthenticated, isLoading } = useAuthStore.getState();
  if (!isLoading && isAuthenticated) {
    window.location.replace("/app/projects");
    return;
  }

  const unsub = useAuthStore.subscribe((state) => {
    if (!state.isLoading && state.isAuthenticated) {
      unsub();
      window.location.replace("/app/projects");
    }
  });

  scheduleHeroVideo(root);
}
