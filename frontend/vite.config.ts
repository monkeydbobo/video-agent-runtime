import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "path";
import seoPages from "./src/seo/seo-pages.json";

type SeoPage = (typeof seoPages)[number];

const SEO_HERO_VIDEO_WEBM = "https://s15-sl.cybercut.ai/kos/s101/nlav112623/oioi_demo_web_vp9_audio.webm";
const SEO_HERO_VIDEO_MP4 = "https://s15-sl.cybercut.ai/kos/s101/nlav112623/oioi_demo_web_h264_audio.mp4";

function escapeHtml(value: string): string {
    return value
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function renderStaticSeoContent(page: SeoPage): string {
    const isZh = page.locale === "zh";
    const steps = page.steps
        .map(
            (step, index) => `
                <li>
                    <span>${String(index + 1).padStart(2, "0")}</span>
                    <div><h3>${escapeHtml(step.title)}</h3><p>${escapeHtml(step.body)}</p></div>
                </li>`,
        )
        .join("");
    const highlights = page.highlights.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    const faq = page.faq
        .map(
            (item) => `
                <details open>
                    <summary>${escapeHtml(item.question)}</summary>
                    <p>${escapeHtml(item.answer)}</p>
                </details>`,
        )
        .join("");
    const related = seoPages
        .filter((candidate) => candidate.locale === page.locale && candidate.path !== page.path)
        .map(
            (candidate) => `
                <a href="${candidate.path}">
                    <span>${escapeHtml(candidate.eyebrow)}</span>
                    <strong>${escapeHtml(candidate.headline)}</strong>
                </a>`,
        )
        .join("");

    return `
      <main class="seo-page">
        <nav class="seo-nav" aria-label="${isZh ? "主导航" : "Main navigation"}">
          <a class="seo-brand" href="/"><span class="seo-brand__mark"><img src="/android-chrome-192x192.png" alt="" width="29" height="29" /></span>oioi.bio</a>
          <div><a href="${page.alternatePath}">${isZh ? "EN" : "中文"}</a><a class="seo-nav__login" href="/login">${isZh ? "进入工作台" : "Enter studio"} →</a></div>
        </nav>
        <article>
          <header class="seo-hero">
            <div class="seo-hero__video" aria-hidden="true">
              <video autoplay loop muted playsinline poster="/hero/oioi-demo-poster.jpg" preload="metadata">
                <source src="${SEO_HERO_VIDEO_WEBM}" type="video/webm; codecs=vp9" />
                <source src="${SEO_HERO_VIDEO_MP4}" type="video/mp4" />
              </video>
            </div>
            <div class="seo-hero__copy">
              <a class="seo-back" href="/">${isZh ? "返回首页" : "Back home"}</a>
              <p class="seo-eyebrow">${escapeHtml(page.eyebrow)}</p>
              <h1>${escapeHtml(page.headline)}</h1>
              <p class="seo-lede">${escapeHtml(page.lede)}</p>
              <a class="seo-primary" href="/login">${isZh ? "开始创作" : "Start creating"} →</a>
            </div>
            <aside class="seo-cut-sheet">
              <p>OIOI / PRODUCTION NOTE</p>
              <strong>${escapeHtml(page.eyebrow)}</strong>
              <ul>${highlights}</ul>
              <span>TEXT → SCRIPT → SHOT → MOTION</span>
            </aside>
          </header>
          <section class="seo-problem">
            <p>${isZh ? "为什么需要工作流" : "Why workflow matters"}</p>
            <div><h2>${escapeHtml(page.problemTitle)}</h2><p>${escapeHtml(page.problemBody)}</p></div>
          </section>
          <section class="seo-process">
            <div class="seo-section-heading"><p>${isZh ? "制作路径" : "Production path"}</p><h2>${isZh ? "从输入到可以审阅的画面。" : "From source material to reviewable motion."}</h2></div>
            <ol>${steps}</ol>
          </section>
          <section class="seo-faq">
            <div class="seo-section-heading"><p>FAQ</p><h2>${isZh ? "创作者通常会问。" : "What creators usually ask."}</h2></div>
            <div class="seo-faq__list">${faq}</div>
          </section>
          <section class="seo-related">
            <p>${isZh ? "继续了解" : "Continue exploring"}</p>
            <div>${related}</div>
          </section>
        </article>
        <footer class="seo-footer"><span>© 2026 oioi.bio</span><a href="/">${isZh ? "产品首页" : "Product home"}</a></footer>
      </main>`;
}

function seoStructuredData(page: SeoPage): string {
    return JSON.stringify({
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                name: page.title,
                description: page.description,
                url: `https://oioi.bio${page.path}`,
                inLanguage: page.locale === "zh" ? "zh-CN" : "en",
                isPartOf: { "@id": "https://oioi.bio/#website" },
                about: { "@id": "https://oioi.bio/#software" },
            },
            {
                "@type": "BreadcrumbList",
                itemListElement: [
                    { "@type": "ListItem", position: 1, name: "oioi.bio", item: "https://oioi.bio/" },
                    {
                        "@type": "ListItem",
                        position: 2,
                        name: page.eyebrow,
                        item: `https://oioi.bio${page.path}`,
                    },
                ],
            },
            {
                "@type": "FAQPage",
                mainEntity: page.faq.map((item) => ({
                    "@type": "Question",
                    name: item.question,
                    acceptedAnswer: { "@type": "Answer", text: item.answer },
                })),
            },
        ],
    });
}

function replaceMeta(html: string, page: SeoPage): string {
    const url = `https://oioi.bio${page.path}`;
    const locale = page.locale === "zh" ? "zh_CN" : "en_US";
    return html
        .replace(/<html lang="[^"]+"/, `<html lang="${page.locale === "zh" ? "zh-CN" : "en"}"`)
        .replace(/<title>[\s\S]*?<\/title>/, `<title>${escapeHtml(page.title)}</title>`)
        .replace(/<meta name="description" content="[^"]*"\s*\/>/, `<meta name="description" content="${escapeHtml(page.description)}" />`)
        .replace(/<link rel="canonical" href="[^"]*"\s*\/>/, `<link rel="canonical" href="${url}" />\n    <link rel="alternate" hreflang="${page.locale}" href="${url}" />\n    <link rel="alternate" hreflang="${page.locale === "zh" ? "en" : "zh"}" href="https://oioi.bio${page.alternatePath}" />\n    <link rel="alternate" hreflang="x-default" href="https://oioi.bio${xDefaultPath(page)}" />`)
        .replace(/<meta property="og:title" content="[^"]*"\s*\/>/, `<meta property="og:title" content="${escapeHtml(page.title)}" />`)
        .replace(/<meta property="og:description" content="[^"]*"\s*\/>/, `<meta property="og:description" content="${escapeHtml(page.description)}" />`)
        .replace(/<meta property="og:url" content="[^"]*"\s*\/>/, `<meta property="og:url" content="${url}" />`)
        .replace(/<meta property="og:locale" content="[^"]*"\s*\/>/, `<meta property="og:locale" content="${locale}" />`)
        .replace(/<meta name="twitter:title" content="[^"]*"\s*\/>/, `<meta name="twitter:title" content="${escapeHtml(page.title)}" />`)
        .replace(/<meta name="twitter:description" content="[^"]*"\s*\/>/, `<meta name="twitter:description" content="${escapeHtml(page.description)}" />`)
        .replace(/<script type="application\/ld\+json">[\s\S]*?<\/script>/, `<script type="application/ld+json">${seoStructuredData(page)}</script>`)
        .replace('<div id="app-root">', '<div id="app-root" data-static-seo="true">')
        .replace('<div id="app-root" data-static-seo="true"></div>', `<div id="app-root" data-static-seo="true">${renderStaticSeoContent(page)}</div>`);
}

const SITE_ORIGIN = "https://oioi.bio";

// 同一语言组（zh/en 互为 alternate）的 x-default 统一指向英文版（站点主语言），
// 保证 sitemap 与页面内 hreflang 信号一致。
function xDefaultPath(page: SeoPage): string {
    return page.locale === "en" ? page.path : page.alternatePath;
}

function renderSitemap(buildDate: string): string {
    const pageEntries = seoPages
        .map((page) => {
            const alternate = seoPages.find((candidate) => candidate.path === page.alternatePath);
            const links = [
                `<xhtml:link rel="alternate" hreflang="${page.locale}" href="${SITE_ORIGIN}${page.path}" />`,
                alternate
                    ? `<xhtml:link rel="alternate" hreflang="${alternate.locale}" href="${SITE_ORIGIN}${alternate.path}" />`
                    : "",
                `<xhtml:link rel="alternate" hreflang="x-default" href="${SITE_ORIGIN}${xDefaultPath(page)}" />`,
            ]
                .filter(Boolean)
                .map((line) => `    ${line}`)
                .join("\n");
            return `  <url>
    <loc>${SITE_ORIGIN}${page.path}</loc>
    <lastmod>${buildDate}</lastmod>
${links}
    <changefreq>monthly</changefreq>
    <priority>0.9</priority>
  </url>`;
        })
        .join("\n");

    return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml"
        xmlns:video="http://www.google.com/schemas/sitemap-video/1.1">
  <url>
    <loc>${SITE_ORIGIN}/</loc>
    <lastmod>${buildDate}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
    <video:video>
      <video:thumbnail_loc>${SITE_ORIGIN}/showreel/elephants-dream-1.jpg</video:thumbnail_loc>
      <video:title>oioi.bio narrative filmmaking showreel</video:title>
      <video:description>Open-film moments demonstrating visual continuity and cinematic pacing.</video:description>
      <video:content_loc>${SITE_ORIGIN}/showreel/elephants-dream-1.mp4</video:content_loc>
    </video:video>
  </url>
${pageEntries}
</urlset>
`;
}

function renderLlmsFullTxt(): string {
    const sections = seoPages.map((page) => {
        const steps = page.steps.map((step, index) => `${index + 1}. **${step.title}** — ${step.body}`).join("\n");
        const highlights = page.highlights.map((item) => `- ${item}`).join("\n");
        const faq = page.faq.map((item) => `### ${item.question}\n\n${item.answer}`).join("\n\n");
        return `## ${page.headline}

Canonical URL: ${SITE_ORIGIN}${page.path} (${page.locale === "zh" ? "Chinese" : "English"}; alternate: ${SITE_ORIGIN}${page.alternatePath})

${page.lede}

**${page.problemTitle}**

${page.problemBody}

Workflow:

${steps}

Highlights:

${highlights}

FAQ:

${faq}`;
    });

    return `# oioi.bio — full reference for AI assistants

> oioi.bio is an AI narrative filmmaking workspace for turning ideas and novels into scripts, reusable visual assets, storyboards, and generated video. This file contains the full text of the official guides; a shorter index lives at ${SITE_ORIGIN}/llms.txt.

- Product name: oioi.bio
- Official website: ${SITE_ORIGIN}/
- Category: AI narrative filmmaking and video production workspace
- Primary languages: Chinese and English
- Sign in: ${SITE_ORIGIN}/login
- Create an account: ${SITE_ORIGIN}/register

${sections.join("\n\n---\n\n")}
`;
}

function generateSeoPages() {
    return {
        name: "generate-static-seo-pages",
        closeBundle() {
            const distDir = path.resolve(__dirname, "dist");
            const shell = readFileSync(path.join(distDir, "index.html"), "utf-8");
            for (const page of seoPages) {
                const targetDir = path.join(distDir, page.path.slice(1));
                mkdirSync(targetDir, { recursive: true });
                writeFileSync(path.join(targetDir, "index.html"), replaceMeta(shell, page), "utf-8");
            }
            const buildDate = new Date().toISOString().slice(0, 10);
            writeFileSync(path.join(distDir, "sitemap.xml"), renderSitemap(buildDate), "utf-8");
            writeFileSync(path.join(distDir, "llms-full.txt"), renderLlmsFullTxt(), "utf-8");
        },
    };
}

export default defineConfig({
    plugins: [react(), tailwindcss(), generateSeoPages()],
    resolve: {
        alias: { "@": path.resolve(__dirname, "src") },
        extensions: [".mjs", ".mts", ".ts", ".tsx", ".js", ".jsx", ".json"],
    },
    server: {
        host: "0.0.0.0",
        port: 5173,
        allowedHosts: ["streamlake-incubator-comfyui.corp.kuaishou.com"],
        proxy: {
            "/api": {
                target: "http://127.0.0.1:1241",
                changeOrigin: true,
            },
        },
    },
    build: {
        outDir: "dist",
        emptyOutDir: true,
    },
});
