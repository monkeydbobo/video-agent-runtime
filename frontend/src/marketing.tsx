// @author wanghaobo
// 营销站入口：仅加载首页所需样式与逻辑，不拉工作台 CSS/页面。

import { createRoot } from "react-dom/client";
import { MarketingRoutes } from "./marketing-router";
import { i18nReady } from "@/i18n";
import { useAuthStore } from "@/stores/auth-store";
import { enhanceStaticHome } from "@/seo/enhance-static-home";

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

  // 生产预渲染首页：保留静态正文供抓取/LCP，只做认证跳转与视频延迟加载。
  if (root.dataset.staticHome === "true") {
    await i18nReady.catch((err) => {
      console.error("i18n initialization failed", err);
    });
    enhanceStaticHome(root);
    return;
  }

  // 开发态（无预渲染正文）：挂载轻量营销路由。
  const render = () => createRoot(root).render(<MarketingRoutes />);
  i18nReady.then(render, (err) => {
    console.error("i18n initialization failed", err);
    render();
  });
}

void boot();
