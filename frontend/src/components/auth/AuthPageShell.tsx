// @author wanghaobo

import { House, LifeBuoy, LockKeyhole } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { BRAND } from "@/branding";
import { ambientGlowStyle, CARD_STYLE, posterGridStyle } from "@/components/ui/darkroom-tokens";

const POSTER_GRID_STYLE = posterGridStyle({ size: 44, maskShape: "70% 70% at 50% 45%", opacity: 0.045 });
const AMBIENT_GLOW_STYLE = ambientGlowStyle({ at: "22% 18%", intensity: 0.2 });

const TRUST_LINKS = [
  { href: "/", labelKey: "home_link", Icon: House, external: false },
  { href: "https://discord.gg/4fdsuGXE5", labelKey: "support_link", Icon: LifeBuoy, external: true },
] as const;

interface AuthPageShellProps {
  canonicalPath: "/login" | "/register";
  pageTitle: string;
  children: ReactNode;
}

export function AuthPageShell({ canonicalPath, pageTitle, children }: AuthPageShellProps) {
  const { t } = useTranslation("auth");

  useEffect(() => {
    const previousTitle = document.title;
    const previousDescription = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    const previousRobots = document.querySelector<HTMLMetaElement>('meta[name="robots"]');
    const previousCanonical = document.querySelector<HTMLLinkElement>('link[rel="canonical"]');

    const description = previousDescription ?? document.head.appendChild(document.createElement("meta"));
    const robots = previousRobots ?? document.head.appendChild(document.createElement("meta"));
    const canonical = previousCanonical ?? document.head.appendChild(document.createElement("link"));

    if (!previousDescription) description.name = "description";
    if (!previousRobots) robots.name = "robots";
    if (!previousCanonical) canonical.rel = "canonical";

    const previousDescriptionContent = description.content;
    const previousRobotsContent = robots.content;
    const previousCanonicalHref = canonical.href;

    document.title = `${pageTitle} — ${BRAND.name}`;
    description.content = t("auth_meta_description", { brand: BRAND.name });
    robots.content = "noindex, nofollow, noarchive";
    canonical.href = new URL(canonicalPath, window.location.origin).href;

    return () => {
      document.title = previousTitle;
      if (previousDescription) description.content = previousDescriptionContent;
      else description.remove();
      if (previousRobots) robots.content = previousRobotsContent;
      else robots.remove();
      if (previousCanonical) canonical.href = previousCanonicalHref;
      else canonical.remove();
    };
  }, [canonicalPath, pageTitle, t]);

  return (
    <div className="relative min-h-dvh overflow-y-auto bg-bg px-4 py-8 text-text sm:px-6 lg:flex lg:items-center">
      <div aria-hidden className="pointer-events-none fixed inset-0" style={AMBIENT_GLOW_STYLE} />
      <div aria-hidden className="pointer-events-none fixed inset-0" style={POSTER_GRID_STYLE} />

      <main className="relative mx-auto grid w-full max-w-[880px] overflow-hidden rounded-[28px] border border-hairline bg-bg-grad-a/80 shadow-[0_32px_90px_-42px_oklch(0.28_0.06_285_/_0.36)] backdrop-blur-xl lg:grid-cols-[1.06fr_0.94fr]">
        <section
          aria-label={t("brand_identity_label", { brand: BRAND.name })}
          className="relative flex flex-col justify-between overflow-hidden border-b border-hairline bg-[linear-gradient(145deg,oklch(0.99_0.008_285_/_0.96),oklch(0.94_0.025_285_/_0.9))] p-7 sm:p-10 lg:min-h-[560px] lg:border-b-0 lg:border-r"
        >
          <div aria-hidden className="absolute -right-14 -top-14 h-52 w-52 rounded-full border border-accent/15" />
          <div aria-hidden className="absolute -right-2 top-4 h-28 w-28 rounded-full border border-accent/10" />

          <div className="relative">
            <a
              className="inline-flex items-center gap-3 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              href="/"
            >
              <img
                alt={t("brand_logo_alt", { brand: BRAND.name })}
                className="h-16 w-16 rounded-[20px] border border-hairline bg-white object-cover shadow-[0_14px_34px_-18px_oklch(0.42_0.1_70_/_0.75)]"
                height="64"
                src="/android-chrome-192x192.png"
                width="64"
              />
              <span>
                <span className="block font-mono text-[9px] font-bold uppercase tracking-[0.2em] text-accent">
                  {t("official_workspace")}
                </span>
                <span className="mt-1 block text-[23px] font-semibold tracking-[-0.035em] text-text">{BRAND.name}</span>
              </span>
            </a>

            <h2 className="mt-9 max-w-[390px] text-[30px] font-semibold leading-[1.12] tracking-[-0.045em] text-text sm:text-[36px]">
              {t("product_identity")}
            </h2>
            <p className="mt-4 max-w-[420px] text-[14px] leading-7 text-text-2">
              {t("account_context", { brand: BRAND.name })}
            </p>
          </div>

          <div className="relative mt-9 lg:mt-12">
            <div className="flex gap-3 rounded-2xl border border-accent/15 bg-white/55 p-4">
              <LockKeyhole aria-hidden className="mt-0.5 shrink-0 text-accent" size={18} strokeWidth={1.7} />
              <p className="text-[12px] leading-5 text-text-2">
                {t("credential_notice", { brand: BRAND.name })}
              </p>
            </div>

            <nav aria-label={t("trust_links_label")} className="mt-5 flex flex-wrap gap-x-5 gap-y-2">
              {TRUST_LINKS.map(({ href, labelKey, Icon, external }) => (
                <a
                  className="inline-flex items-center gap-1.5 text-[11px] font-medium text-text-3 underline-offset-4 transition-colors hover:text-text hover:underline focus-visible:rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  href={href}
                  key={labelKey}
                  rel={external ? "noreferrer" : undefined}
                  target={external ? "_blank" : undefined}
                >
                  <Icon aria-hidden size={13} strokeWidth={1.8} />
                  {t(labelKey)}
                </a>
              ))}
            </nav>
          </div>
        </section>

        <section className="flex items-center p-7 sm:p-10" style={CARD_STYLE}>
          <div className="w-full">
            <p className="font-mono text-[9px] font-bold uppercase tracking-[0.2em] text-text-4">
              {BRAND.name} · {t("secure_account")}
            </p>
            <h1 className="font-editorial mt-2 text-[34px] tracking-tight text-text">{pageTitle}</h1>
            <p className="mt-2 text-[12px] leading-5 text-text-3">{t("form_context", { brand: BRAND.name })}</p>
            <div className="mt-7">{children}</div>
          </div>
        </section>
      </main>
    </div>
  );
}
