// Brand configuration — single source of truth for product naming.
// Override at build time via Vite env vars
// (VITE_BRAND_NAME / VITE_BRAND_TAGLINE / VITE_BRAND_DESCRIPTION).
//
// 公开页 SEO 文案以 frontend/src/seo/home.json 为准；此处仅保留应用内品牌短名与
// 工作台 fallback，避免再与 index.html / JSON-LD 各写一套冲突中文。

import { HOME_PAGES } from "@/seo/site";

const env = import.meta.env as Record<string, string | undefined>;

function fallback(value: string | undefined, defaultValue: string): string {
  if (typeof value !== "string") return defaultValue;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : defaultValue;
}

const defaultHome = HOME_PAGES.en;

export const BRAND = {
  name: fallback(env.VITE_BRAND_NAME, "oioi.bio"),
  tagline: fallback(env.VITE_BRAND_TAGLINE, defaultHome.eyebrow),
  description: fallback(env.VITE_BRAND_DESCRIPTION, defaultHome.description),
} as const;

export const BRAND_DOCUMENT_TITLE = `${BRAND.name} · ${BRAND.tagline}`;
