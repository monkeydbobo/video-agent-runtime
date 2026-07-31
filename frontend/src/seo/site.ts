// @author wanghaobo
// 公开页 SEO 共享常量：构建期与运行时共用，避免 index.html / branding / main 各写一套。

import homePages from "./home.json";

export const SITE_ORIGIN = "https://oioi.bio";

export const OG_IMAGE = {
  url: `${SITE_ORIGIN}/og-default-1200x630.jpg`,
  width: 1200,
  height: 630,
  type: "image/jpeg",
  altEn: "oioi.bio — AI narrative filmmaking studio",
  altZh: "oioi.bio — AI 叙事影像创作工作台",
} as const;

export const HOME_PAGES = homePages;

export type HomeLocale = keyof typeof homePages;

export function homePageForLocale(locale: HomeLocale) {
  return homePages[locale];
}
