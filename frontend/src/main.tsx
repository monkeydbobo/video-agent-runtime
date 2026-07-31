// @author wanghaobo
// 工作台 / 认证入口：加载完整 studio 资源。营销首页走 marketing.tsx。

import { createRoot } from "react-dom/client";
import { AppRoutes } from "./router";
import { useAuthStore } from "@/stores/auth-store";
import { i18nReady } from "@/i18n";
import { BRAND } from "@/branding";

import "./index.css";
import "./css/styles.css";
import "./css/app.css";
import "./css/studio.css";

// 应用壳默认标题；各页面可再覆盖。不写入营销站冲突文案。
document.title = `${BRAND.name} Studio`;

useAuthStore.getState().initialize();

{
  const timers = new WeakMap<Element, ReturnType<typeof setTimeout>>();

  document.addEventListener(
    "scroll",
    (e) => {
      const el = e.target;
      if (!(el instanceof HTMLElement)) return;

      el.dataset.scrolling = "";

      const prev = timers.get(el);
      if (prev) clearTimeout(prev);

      timers.set(
        el,
        setTimeout(() => {
          delete el.dataset.scrolling;
          timers.delete(el);
        }, 1200),
      );
    },
    true,
  );
}

const root = document.getElementById("app-root");
if (root) {
  const render = () => createRoot(root).render(<AppRoutes />);
  i18nReady.then(render, (err) => {
    console.error("i18n initialization failed", err);
    render();
  });
}
