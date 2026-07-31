// @author wanghaobo
// 构建产物 SEO 断言：首页/专题页正文、唯一 title/canonical、hreflang、sitemap URL。

import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const distDir = path.resolve(__dirname, "../dist");
const siteOrigin = "https://oioi.bio";

function fail(message) {
  console.error(`verify-seo-build: ${message}`);
  process.exit(1);
}

function read(rel) {
  const full = path.join(distDir, rel);
  if (!existsSync(full)) fail(`missing file ${rel}`);
  return readFileSync(full, "utf-8");
}

function countMatches(html, re) {
  return [...html.matchAll(re)].length;
}

function assertPage(rel, { locale, path: pagePath, mustInclude }) {
  const html = read(rel);
  if (!html.includes("<main")) fail(`${rel} missing main content`);
  for (const snippet of mustInclude) {
    if (!html.includes(snippet)) fail(`${rel} missing content: ${snippet}`);
  }
  if (countMatches(html, /<title>/g) !== 1) fail(`${rel} must have exactly one <title>`);
  if (countMatches(html, /rel="canonical"/g) !== 1) fail(`${rel} must have exactly one canonical`);
  if (!html.includes(`hreflang="${locale}"`)) fail(`${rel} missing hreflang=${locale}`);
  if (!html.includes('hreflang="x-default"')) fail(`${rel} missing x-default`);
  if (!html.includes(`href="${siteOrigin}${pagePath === "/" ? "/" : pagePath}"`)) {
    fail(`${rel} missing canonical/hreflang URL for ${pagePath}`);
  }
  if (rel !== "index.html" && rel !== "zh/index.html") {
    if (html.includes('<script type="module"')) fail(`${rel} SEO page must not include module scripts`);
  }
  return html;
}

if (!existsSync(path.join(distDir, "index.html"))) {
  fail("dist/index.html not found — run pnpm build first");
}

assertPage("index.html", {
  locale: "en",
  path: "/",
  mustInclude: ["Turn a story into", "AI narrative filmmaking studio", 'lang="en"'],
});

assertPage("zh/index.html", {
  locale: "zh",
  path: "/zh",
  mustInclude: ["把故事变成", "AI 叙事影像", 'lang="zh-CN"'],
});

const seoPaths = [
  ["zh/novel-to-video/index.html", "zh", "/zh/novel-to-video", "把几万字的故事"],
  ["zh/ai-storyboard-generator/index.html", "zh", "/zh/ai-storyboard-generator", "分镜不只是好看的图"],
  ["en/novel-to-video/index.html", "en", "/en/novel-to-video", "Turn a long story into shots"],
  ["en/ai-storyboard-generator/index.html", "en", "/en/ai-storyboard-generator", "A storyboard should be more"],
];

for (const [rel, locale, pagePath, snippet] of seoPaths) {
  assertPage(rel, { locale, path: pagePath, mustInclude: [snippet] });
}

if (!existsSync(path.join(distDir, "app.html"))) fail("dist/app.html missing");
const appHtml = read("app.html");
if (!appHtml.includes("noindex")) fail("app.html must be noindex");

const sitemap = read("sitemap.xml");
if (sitemap.includes("<changefreq>") || sitemap.includes("<priority>")) {
  fail("sitemap must not include changefreq/priority");
}
if (!sitemap.includes(`${siteOrigin}/`)) fail("sitemap missing home URL");
if (!sitemap.includes(`${siteOrigin}/zh`)) fail("sitemap missing /zh");
if (!sitemap.includes('hreflang="x-default"')) fail("sitemap missing hreflang");

const locUrls = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
const expected = new Set([
  `${siteOrigin}/`,
  `${siteOrigin}/zh`,
  ...seoPaths.map(([, , pagePath]) => `${siteOrigin}${pagePath}`),
]);
for (const url of locUrls) {
  if (!expected.has(url)) fail(`unexpected sitemap URL: ${url}`);
}
for (const url of expected) {
  if (!locUrls.includes(url)) fail(`sitemap missing URL: ${url}`);
}

if (!existsSync(path.join(distDir, "og-default-1200x630.jpg"))) {
  fail("og-default-1200x630.jpg missing from dist");
}

console.log(`verify-seo-build: ok (${locUrls.length} sitemap URLs)`);
