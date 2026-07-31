// @author wanghaobo
// 营销站路由：首页 + 专题页预览；工作台路由不在此入口同步加载。

import { useEffect } from "react";
import { Route, Switch, useLocation } from "wouter";
import { useTranslation } from "react-i18next";
import { LandingPage } from "@/pages/LandingPage";
import { SeoLandingPage } from "@/pages/SeoLandingPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { useAuthStore } from "@/stores/auth-store";
import type { SupportedLanguage } from "@/i18n";

function usePublicLocaleFromPath(): void {
  const [location] = useLocation();
  const { i18n } = useTranslation();

  useEffect(() => {
    const locale: SupportedLanguage = location === "/zh" || location.startsWith("/zh/") ? "zh" : "en";
    if ((i18n.resolvedLanguage?.split("-", 1)[0] ?? "en") !== locale) {
      void i18n.changeLanguage(locale);
    }
  }, [i18n, location]);
}

function HomeRoute({ locale }: { locale: "en" | "zh" }) {
  const { isAuthenticated, isLoading } = useAuthStore();
  const { i18n } = useTranslation();

  useEffect(() => {
    if ((i18n.resolvedLanguage?.split("-", 1)[0] ?? "en") !== locale) {
      void i18n.changeLanguage(locale);
    }
  }, [i18n, locale]);

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      window.location.replace("/app/projects");
    }
  }, [isAuthenticated, isLoading]);

  if (isLoading) return null;
  if (isAuthenticated) return null;
  return <LandingPage />;
}

export function MarketingRoutes() {
  usePublicLocaleFromPath();

  return (
    <Switch>
      <Route path="/zh/:seoSlug" component={SeoLandingPage} />
      <Route path="/en/:seoSlug" component={SeoLandingPage} />
      <Route path="/zh">{() => <HomeRoute locale="zh" />}</Route>
      <Route path="/">{() => <HomeRoute locale="en" />}</Route>
      <Route>
        <NotFoundPage />
      </Route>
    </Switch>
  );
}
