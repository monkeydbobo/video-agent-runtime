// @author wanghaobo
// 营销站入口：仅加载首页所需样式与逻辑，不拉工作台 CSS/页面。

import { createRoot } from "react-dom/client";
import { MarketingRoutes } from "./marketing-router";
import { i18nReady } from "@/i18n";
import { useAuthStore } from "@/stores/auth-store";

import "./index.css";
import "./css/styles.css";
import "./pages/LandingPage.css";
import "./pages/SeoLandingPage.css";

useAuthStore.getState().initialize();

const root = document.getElementById("app-root");

async function boot(): Promise<void> {
  if (!root) return;

  // 预渲染专题页不应挂载 React（构建期已剥离 script；此处仅为防御）。
  if (root.dataset.staticSeo === "true") {
    return;
  }

  // 首页：静态 HTML 只服务无 JS 抓取/首屏占位；有 JS 时挂载完整 LandingPage，
  // 恢复粒子、大气层、showreel 与原有视觉，避免停留在精简静态壳上。
  const render = () => createRoot(root).render(<MarketingRoutes />);
  i18nReady.then(render, (err) => {
    console.error("i18n initialization failed", err);
    render();
  });
}

void boot();
