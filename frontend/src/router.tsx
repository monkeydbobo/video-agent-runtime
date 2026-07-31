// router.tsx — Route definitions for the studio / auth shell (app.html entry)

import { lazy, Suspense, useEffect, type ReactNode } from "react";
import { Route, Switch, Redirect, useParams } from "wouter";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { LoginPage } from "@/pages/LoginPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { ToastOverlay } from "@/components/layout/ToastOverlay";
import { API } from "@/api";
import { useProjectsStore } from "@/stores/projects-store";
import { useAssistantStore } from "@/stores/assistant-store";
import { useAuthStore } from "@/stores/auth-store";
import { useConfigStatusStore } from "@/stores/config-status-store";

const StudioLayout = lazy(() =>
  import("@/components/layout").then((m) => ({ default: m.StudioLayout })),
);
const StudioCanvasRouter = lazy(() =>
  import("@/components/canvas/StudioCanvasRouter").then((m) => ({ default: m.StudioCanvasRouter })),
);
const ProjectsPage = lazy(() =>
  import("@/components/pages/ProjectsPage").then((m) => ({ default: m.ProjectsPage })),
);
const SystemConfigPage = lazy(() =>
  import("@/components/pages/SystemConfigPage").then((m) => ({ default: m.SystemConfigPage })),
);
const ProjectSettingsPage = lazy(() =>
  import("@/components/pages/ProjectSettingsPage").then((m) => ({ default: m.ProjectSettingsPage })),
);
const AssetLibraryPage = lazy(() =>
  import("@/components/pages/AssetLibraryPage").then((m) => ({ default: m.AssetLibraryPage })),
);

function ConfigStatusLoader() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  useEffect(() => {
    if (!isAuthenticated) return;
    let cancelled = false;
    let attempts = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      await useConfigStatusStore.getState().fetch();
      if (cancelled) return;
      if (!useConfigStatusStore.getState().initialized && attempts < 5) {
        attempts += 1;
        timer = setTimeout(() => void tick(), 800 * attempts);
      }
    };
    void tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [isAuthenticated]);

  return null;
}

function AuthLoading() {
  const { t } = useTranslation("common");

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex h-screen items-center justify-center gap-2 bg-bg text-[13px] text-text-4"
    >
      <Loader2 aria-hidden className="h-4 w-4 motion-safe:animate-spin" />
      <span>{t("loading")}</span>
    </div>
  );
}

function AuthGuard({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuthStore();

  if (isLoading) {
    return <AuthLoading />;
  }

  if (!isAuthenticated) {
    const from = window.location.pathname + window.location.search + window.location.hash;
    return <Redirect to={`~/login?from=${encodeURIComponent(from)}`} />;
  }

  return <>{children}</>;
}

function StudioSuspense({ children }: { children: ReactNode }) {
  return <Suspense fallback={<AuthLoading />}>{children}</Suspense>;
}

function StudioWorkspace() {
  const params = useParams<{ projectName: string }>();
  const projectName = params.projectName ?? null;
  const { setCurrentProject, setProjectDetailLoading } = useProjectsStore();

  useEffect(() => {
    if (!projectName) return;
    let cancelled = false;

    const assistantState = useAssistantStore.getState();
    assistantState.setSessions([]);
    assistantState.setCurrentSessionId(null);
    assistantState.resetTimeline();
    assistantState.setSessionStatus(null);
    assistantState.setIsDraftSession(false);

    setProjectDetailLoading(true);
    void API.ensureProjectMediaToken(projectName);
    const mediaTokenRefreshId = window.setInterval(() => {
      API.invalidateProjectMediaToken(projectName);
      void API.ensureProjectMediaToken(projectName);
    }, 4 * 60 * 1000);
    API.getProject(projectName)
      .then((res) => {
        if (!cancelled) {
          setCurrentProject(projectName, res.project, res.scripts ?? {}, res.asset_fingerprints);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCurrentProject(projectName, null);
        }
      })
      .finally(() => {
        if (!cancelled) setProjectDetailLoading(false);
      });

    return () => {
      cancelled = true;
      window.clearInterval(mediaTokenRefreshId);
      setCurrentProject(null, null);
    };
  }, [projectName, setCurrentProject, setProjectDetailLoading]);

  return (
    <StudioSuspense>
      <StudioLayout>
        <StudioCanvasRouter />
      </StudioLayout>
    </StudioSuspense>
  );
}

export function AppRoutes() {
  return (
    <>
      <ConfigStatusLoader />
      <Switch>
        <Route path="/login" component={LoginPage} />
        <Route path="/register" component={RegisterPage} />

        {/* 公开首页由营销入口托管；若误入 app shell，已登录用户进工作台。 */}
        <Route path="/">
          <AuthGuard>
            <Redirect to="/app/projects" />
          </AuthGuard>
        </Route>

        <Route path="/app">
          <Redirect to="/app/projects" />
        </Route>

        <Route path="/app/projects">
          <AuthGuard>
            <StudioSuspense>
              <ProjectsPage />
            </StudioSuspense>
          </AuthGuard>
        </Route>

        <Route path="/app/settings">
          <AuthGuard>
            <StudioSuspense>
              <SystemConfigPage />
            </StudioSuspense>
          </AuthGuard>
        </Route>

        <Route path="/app/assets">
          <AuthGuard>
            <StudioSuspense>
              <AssetLibraryPage />
            </StudioSuspense>
          </AuthGuard>
        </Route>

        <Route path="/app/projects/:projectName/settings">
          <AuthGuard>
            <StudioSuspense>
              <ProjectSettingsPage />
            </StudioSuspense>
          </AuthGuard>
        </Route>

        <Route path="/app/projects/:projectName" nest>
          <AuthGuard>
            <StudioWorkspace />
          </AuthGuard>
        </Route>

        <Route>
          <NotFoundPage />
        </Route>
      </Switch>
      <ToastOverlay />
    </>
  );
}
