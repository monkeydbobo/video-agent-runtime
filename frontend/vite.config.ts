import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "path";
import seoPages from "./src/seo/seo-pages.json";

type SeoPage = (typeof seoPages)[number];

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
          <a class="seo-brand" href="/"><span>◫</span>oioi.bio</a>
          <div><a href="${page.alternatePath}">${isZh ? "EN" : "中文"}</a><a href="/login">${isZh ? "进入工作台" : "Enter studio"}</a></div>
        </nav>
        <article>
          <header class="seo-hero">
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
        .replace(/<link rel="canonical" href="[^"]*"\s*\/>/, `<link rel="canonical" href="${url}" />\n    <link rel="alternate" hreflang="${page.locale}" href="${url}" />\n    <link rel="alternate" hreflang="${page.locale === "zh" ? "en" : "zh"}" href="https://oioi.bio${page.alternatePath}" />\n    <link rel="alternate" hreflang="x-default" href="https://oioi.bio/" />`)
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
