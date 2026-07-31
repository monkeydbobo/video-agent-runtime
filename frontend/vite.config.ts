import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "path";
import homePages from "./src/seo/home.json";
import seoPages from "./src/seo/seo-pages.json";

type SeoPage = (typeof seoPages)[number];
type HomePage = (typeof homePages)[keyof typeof homePages];

const SITE_ORIGIN = "https://oioi.bio";
const OG_IMAGE_PATH = "/og-default-1200x630.jpg";
const OG_IMAGE = {
    url: `${SITE_ORIGIN}${OG_IMAGE_PATH}`,
    width: 1200,
    height: 630,
    type: "image/jpeg",
};

function escapeHtml(value: string): string {
    return value
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function htmlLang(locale: string): string {
    return locale === "zh" ? "zh-CN" : "en";
}

function ogLocale(locale: string): string {
    return locale === "zh" ? "zh_CN" : "en_US";
}

function ogImageAlt(locale: string): string {
    return locale === "zh" ? "oioi.bio — AI 叙事影像创作工作台" : "oioi.bio — AI narrative filmmaking studio";
}

function stripModuleScripts(html: string): string {
    return html.replace(/<script type="module"[^>]*>[\s\S]*?<\/script>/g, "");
}

function injectFontStylesheet(html: string, locale: string): string {
    const families =
        locale === "zh"
            ? "family=Inter:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;600;700"
            : "family=Inter:wght@400;500;600;700";
    const tags = `
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?${families}&display=swap" rel="stylesheet" media="print" onload="this.media='all'" />
    <noscript><link href="https://fonts.googleapis.com/css2?${families}&display=swap" rel="stylesheet" /></noscript>`;
    return html.replace("</head>", `${tags}\n</head>`);
}

function applyCommonMeta(
    html: string,
    page: {
        path: string;
        locale: string;
        alternatePath: string;
        title: string;
        description: string;
        dateModified?: string;
    },
    structuredData: string,
    options: { stripScripts?: boolean; robots?: string } = {},
): string {
    const url = `${SITE_ORIGIN}${page.path === "/" ? "/" : page.path}`;
    const alternateUrl = `${SITE_ORIGIN}${page.alternatePath === "/" ? "/" : page.alternatePath}`;
    const xDefaultUrl = `${SITE_ORIGIN}/`;
    const locale = page.locale;
    const imageAlt = escapeHtml(ogImageAlt(locale));
    const robots = options.robots ?? "index, follow, max-image-preview:large";

    let next = html
        .replace(/<html lang="[^"]+"/, `<html lang="${htmlLang(locale)}"`)
        .replace(/<title>[\s\S]*?<\/title>/, `<title>${escapeHtml(page.title)}</title>`)
        .replace(
            /<meta name="description" content="[^"]*"\s*\/>/,
            `<meta name="description" content="${escapeHtml(page.description)}" />`,
        )
        .replace(/<meta name="robots" content="[^"]*"\s*\/>/, `<meta name="robots" content="${robots}" />`)
        .replace(
            /<link rel="canonical" href="[^"]*"\s*\/>[\s\S]*?(?=<meta property="og:type"|<meta property="og:site_name"|<script type="application\/ld\+json">)/,
            `<link rel="canonical" href="${url}" />
    <link rel="alternate" hreflang="${locale}" href="${url}" />
    <link rel="alternate" hreflang="${locale === "zh" ? "en" : "zh"}" href="${alternateUrl}" />
    <link rel="alternate" hreflang="x-default" href="${xDefaultUrl}" />
    `,
        )
        .replace(/<meta property="og:title" content="[^"]*"\s*\/>/, `<meta property="og:title" content="${escapeHtml(page.title)}" />`)
        .replace(
            /<meta property="og:description" content="[^"]*"\s*\/>/,
            `<meta property="og:description" content="${escapeHtml(page.description)}" />`,
        )
        .replace(/<meta property="og:url" content="[^"]*"\s*\/>/, `<meta property="og:url" content="${url}" />`)
        .replace(/<meta property="og:image" content="[^"]*"\s*\/>/, `<meta property="og:image" content="${OG_IMAGE.url}" />`)
        .replace(/<meta property="og:image:type" content="[^"]*"\s*\/>/, `<meta property="og:image:type" content="${OG_IMAGE.type}" />`)
        .replace(
            /<meta property="og:image:width" content="[^"]*"\s*\/>/,
            `<meta property="og:image:width" content="${OG_IMAGE.width}" />`,
        )
        .replace(
            /<meta property="og:image:height" content="[^"]*"\s*\/>/,
            `<meta property="og:image:height" content="${OG_IMAGE.height}" />`,
        )
        .replace(/<meta property="og:image:alt" content="[^"]*"\s*\/>/, `<meta property="og:image:alt" content="${imageAlt}" />`)
        .replace(/<meta property="og:locale" content="[^"]*"\s*\/>/, `<meta property="og:locale" content="${ogLocale(locale)}" />`)
        .replace(/<meta name="twitter:title" content="[^"]*"\s*\/>/, `<meta name="twitter:title" content="${escapeHtml(page.title)}" />`)
        .replace(
            /<meta name="twitter:description" content="[^"]*"\s*\/>/,
            `<meta name="twitter:description" content="${escapeHtml(page.description)}" />`,
        )
        .replace(/<meta name="twitter:image" content="[^"]*"\s*\/>/, `<meta name="twitter:image" content="${OG_IMAGE.url}" />`)
        .replace(/<meta name="twitter:image:alt" content="[^"]*"\s*\/>/, `<meta name="twitter:image:alt" content="${imageAlt}" />`)
        .replace(/<script type="application\/ld\+json">[\s\S]*?<\/script>/, `<script type="application/ld+json">${structuredData}</script>`);

    if (options.stripScripts) {
        next = stripModuleScripts(next);
    }
    return injectFontStylesheet(next, locale);
}

function renderStaticSeoContent(page: SeoPage): string {
    const isZh = page.locale === "zh";
    const homeHref = isZh ? "/zh" : "/";
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
                <details>
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

    // 专题页默认不自动下载装饰视频：仅 poster，无 <source>。
    return `
      <main class="seo-page">
        <nav class="seo-nav" aria-label="${isZh ? "主导航" : "Main navigation"}">
          <a class="seo-brand" href="${homeHref}"><span class="seo-brand__mark"><img src="/android-chrome-192x192.png" alt="" width="29" height="29" /></span>oioi.bio</a>
          <div><a href="${page.alternatePath}">${isZh ? "EN" : "中文"}</a><a class="seo-nav__login" href="/login">${isZh ? "进入工作台" : "Enter studio"} →</a></div>
        </nav>
        <article>
          <header class="seo-hero">
            <div class="seo-hero__video" aria-hidden="true">
              <img src="/hero/oioi-demo-poster.jpg" alt="" width="1920" height="1080" style="width:100%;height:100%;object-fit:cover" />
            </div>
            <div class="seo-hero__copy">
              <a class="seo-back" href="${homeHref}">${isZh ? "返回首页" : "Back home"}</a>
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
        <footer class="seo-footer"><span>© 2026 oioi.bio</span><a href="${homeHref}">${isZh ? "产品首页" : "Product home"}</a></footer>
      </main>`;
}

function seoStructuredData(page: SeoPage): string {
    // FAQ 内容保留在可见 HTML；不再输出 FAQPage（Google 已退役 FAQ 富结果目标）。
    // SoftwareApplication 不编造评分或评论。
    return JSON.stringify({
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                name: page.title,
                description: page.description,
                url: `${SITE_ORIGIN}${page.path}`,
                inLanguage: htmlLang(page.locale),
                dateModified: page.dateModified,
                isPartOf: { "@id": `${SITE_ORIGIN}/#website` },
                about: { "@id": `${SITE_ORIGIN}/#software` },
                primaryImageOfPage: {
                    "@type": "ImageObject",
                    url: OG_IMAGE.url,
                    width: OG_IMAGE.width,
                    height: OG_IMAGE.height,
                },
            },
            {
                "@type": "BreadcrumbList",
                itemListElement: [
                    {
                        "@type": "ListItem",
                        position: 1,
                        name: "oioi.bio",
                        item: page.locale === "zh" ? `${SITE_ORIGIN}/zh` : `${SITE_ORIGIN}/`,
                    },
                    {
                        "@type": "ListItem",
                        position: 2,
                        name: page.eyebrow,
                        item: `${SITE_ORIGIN}${page.path}`,
                    },
                ],
            },
        ],
    });
}

function renderStaticHomeContent(page: HomePage): string {
    const isZh = page.locale === "zh";
    const features = page.features
        .map(
            (feature, index) => `
          <article class="landing-feature">
            <span class="landing-feature__number">0${index + 1}</span>
            <h2>${escapeHtml(feature.title)}</h2>
            <p>${escapeHtml(feature.body)}</p>
          </article>`,
        )
        .join("");
    const workflow = page.workflowSteps
        .map(
            (step, index) => `
            <li><span>0${index + 1}</span><p>${escapeHtml(step)}</p></li>`,
        )
        .join("");
    const guides = page.guides
        .map(
            (guide, index) => `
            <a href="/${page.locale === "zh" ? "zh" : "en"}/${guide.slug}">
              <span>0${index + 1}</span>
              <div><strong>${escapeHtml(guide.title)}</strong><p>${escapeHtml(guide.body)}</p></div>
            </a>`,
        )
        .join("");

    return `
      <main class="landing-page">
        <nav class="landing-nav" aria-label="${isZh ? "主导航" : "Main navigation"}">
          <a class="landing-brand" href="${page.path}"><span class="landing-brand__mark"><img alt="" height="26" src="/android-chrome-192x192.png" width="26" /></span><span>oioi.bio</span></a>
          <div class="landing-nav__right">
            <a href="#capabilities">${isZh ? "核心能力" : "Capabilities"}</a>
            <a href="#workflow">${isZh ? "创作流程" : "Workflow"}</a>
            <div class="landing-language" aria-label="${isZh ? "语言切换" : "Language switcher"}">
              <a class="${isZh ? "is-active" : ""}" href="/zh" hreflang="zh">中</a>
              <a class="${isZh ? "" : "is-active"}" href="/" hreflang="en">EN</a>
            </div>
            <a class="landing-login" href="/login">${isZh ? "登录" : "Log in"} →</a>
          </div>
        </nav>
        <section class="landing-hero" aria-labelledby="landing-title">
          <div class="landing-hero__copy">
            <p class="landing-badge">${escapeHtml(page.eyebrow)}</p>
            <h1 id="landing-title"><span>${escapeHtml(page.titleBefore)}</span> <em>${escapeHtml(page.titleEmphasis)}</em>${escapeHtml(page.titleAfter)}</h1>
            <p class="landing-lede">${escapeHtml(page.lede)}</p>
            <div class="landing-actions">
              <a class="landing-cta" href="/login">${escapeHtml(page.start)} →</a>
              <a class="landing-text-link" href="#workflow">${escapeHtml(page.learnMore)}</a>
            </div>
          </div>
          <div class="landing-reel" aria-hidden="true">
            <img src="/hero/oioi-demo-poster.jpg" alt="" width="960" height="540" style="width:100%;height:100%;object-fit:cover;border-radius:inherit" />
          </div>
        </section>
        <section class="landing-features" id="capabilities" aria-label="${escapeHtml(page.featuresLabel)}">
          <div class="landing-features__intro"><p>${escapeHtml(page.featuresLabel)}</p><span>01 — 03</span></div>
          ${features}
        </section>
        <section class="landing-workflow" id="workflow" aria-labelledby="workflow-title">
          <div>
            <p class="landing-kicker">${escapeHtml(page.workflowEyebrow)}</p>
            <h2 id="workflow-title">${escapeHtml(page.workflowTitle)}</h2>
          </div>
          <ol>${workflow}</ol>
        </section>
        <section class="landing-guides" aria-labelledby="guides-title">
          <div class="landing-guides__heading">
            <p class="landing-kicker">${escapeHtml(page.guidesEyebrow)}</p>
            <h2 id="guides-title">${escapeHtml(page.guidesTitle)}</h2>
          </div>
          <div class="landing-guides__list">${guides}</div>
        </section>
        <footer class="landing-footer">
          <p>© 2026 oioi.bio</p>
          <a href="/login">${isZh ? "进入工作台" : "Enter studio"}</a>
        </footer>
      </main>`;
}

function homeStructuredData(page: HomePage): string {
    return JSON.stringify({
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": `${SITE_ORIGIN}/#organization`,
                name: "oioi.bio",
                url: `${SITE_ORIGIN}/`,
                logo: `${SITE_ORIGIN}/android-chrome-192x192.png`,
            },
            {
                "@type": "WebSite",
                "@id": `${SITE_ORIGIN}/#website`,
                name: "oioi.bio",
                url: `${SITE_ORIGIN}/`,
                description: page.description,
                inLanguage: ["en", "zh-CN"],
                publisher: { "@id": `${SITE_ORIGIN}/#organization` },
            },
            {
                "@type": "WebPage",
                "@id": `${SITE_ORIGIN}${page.path === "/" ? "/" : page.path}#webpage`,
                name: page.title,
                description: page.description,
                url: `${SITE_ORIGIN}${page.path === "/" ? "/" : page.path}`,
                inLanguage: htmlLang(page.locale),
                dateModified: page.dateModified,
                isPartOf: { "@id": `${SITE_ORIGIN}/#website` },
                about: { "@id": `${SITE_ORIGIN}/#software` },
                primaryImageOfPage: {
                    "@type": "ImageObject",
                    url: OG_IMAGE.url,
                    width: OG_IMAGE.width,
                    height: OG_IMAGE.height,
                },
            },
            {
                "@type": "SoftwareApplication",
                "@id": `${SITE_ORIGIN}/#software`,
                name: "oioi.bio",
                applicationCategory: "MultimediaApplication",
                operatingSystem: "Web",
                url: `${SITE_ORIGIN}/`,
                description: page.description,
                featureList: page.featureList,
                publisher: { "@id": `${SITE_ORIGIN}/#organization` },
            },
        ],
    });
}

function renderSitemap(): string {
    const homeEntries = (["en", "zh"] as const).map((locale) => {
        const page = homePages[locale];
        const loc = `${SITE_ORIGIN}${page.path === "/" ? "/" : page.path}`;
        const alternate = homePages[locale === "en" ? "zh" : "en"];
        const alternateLoc = `${SITE_ORIGIN}${alternate.path === "/" ? "/" : alternate.path}`;
        return `  <url>
    <loc>${loc}</loc>
    <lastmod>${page.dateModified}</lastmod>
    <xhtml:link rel="alternate" hreflang="${page.locale}" href="${loc}" />
    <xhtml:link rel="alternate" hreflang="${alternate.locale}" href="${alternateLoc}" />
    <xhtml:link rel="alternate" hreflang="x-default" href="${SITE_ORIGIN}/" />
  </url>`;
    });

    const pageEntries = seoPages.map((page) => {
        const alternate = seoPages.find((candidate) => candidate.path === page.alternatePath);
        const links = [
            `<xhtml:link rel="alternate" hreflang="${page.locale}" href="${SITE_ORIGIN}${page.path}" />`,
            alternate
                ? `<xhtml:link rel="alternate" hreflang="${alternate.locale}" href="${SITE_ORIGIN}${alternate.path}" />`
                : "",
            `<xhtml:link rel="alternate" hreflang="x-default" href="${SITE_ORIGIN}${page.locale === "en" ? page.path : page.alternatePath}" />`,
        ]
            .filter(Boolean)
            .map((line) => `    ${line}`)
            .join("\n");
        return `  <url>
    <loc>${SITE_ORIGIN}${page.path}</loc>
    <lastmod>${page.dateModified}</lastmod>
${links}
  </url>`;
    });

    return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
${homeEntries.join("\n")}
${pageEntries.join("\n")}
</urlset>
`;
}

function renderLlmsFullTxt(): string {
    const homeSection = (["en", "zh"] as const)
        .map((locale) => {
            const page = homePages[locale];
            return `## ${page.title}

Canonical URL: ${SITE_ORIGIN}${page.path === "/" ? "/" : page.path}

${page.lede}
`;
        })
        .join("\n");

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

${homeSection}
---

${sections.join("\n\n---\n\n")}
`;
}

function replaceHomeRoot(html: string, page: HomePage): string {
    const withMeta = applyCommonMeta(html, page, homeStructuredData(page), { stripScripts: false });
    return withMeta
        .replace(/<noscript>[\s\S]*?<\/noscript>/, `<noscript>${escapeHtml(page.noscript)}</noscript>`)
        .replace('<div id="app-root">', '<div id="app-root" data-static-home="true">')
        .replace(
            /<div id="app-root" data-static-home="true"><\/div>/,
            `<div id="app-root" data-static-home="true" data-home-locale="${page.locale}">${renderStaticHomeContent(page)}</div>`,
        );
}

function replaceSeoPage(html: string, page: SeoPage): string {
    const withMeta = applyCommonMeta(html, page, seoStructuredData(page), { stripScripts: true });
    return withMeta
        .replace('<div id="app-root">', '<div id="app-root" data-static-seo="true">')
        .replace(
            /<div id="app-root" data-static-seo="true"><\/div>/,
            `<div id="app-root" data-static-seo="true">${renderStaticSeoContent(page)}</div>`,
        );
}

function generateSeoPages(): Plugin {
    return {
        name: "generate-static-seo-pages",
        closeBundle() {
            const distDir = path.resolve(__dirname, "dist");
            const marketingShell = readFileSync(path.join(distDir, "index.html"), "utf-8");

            // 英文根首页：覆盖 index.html，保留营销 bundle 供交互增强。
            writeFileSync(path.join(distDir, "index.html"), replaceHomeRoot(marketingShell, homePages.en), "utf-8");

            // 中文首页
            const zhDir = path.join(distDir, "zh");
            mkdirSync(zhDir, { recursive: true });
            writeFileSync(path.join(zhDir, "index.html"), replaceHomeRoot(marketingShell, homePages.zh), "utf-8");

            // 专题页：无 JS，原生 details / a 即可用。
            for (const page of seoPages) {
                const targetDir = path.join(distDir, page.path.slice(1));
                mkdirSync(targetDir, { recursive: true });
                writeFileSync(path.join(targetDir, "index.html"), replaceSeoPage(marketingShell, page), "utf-8");
            }

            writeFileSync(path.join(distDir, "sitemap.xml"), renderSitemap(), "utf-8");
            writeFileSync(path.join(distDir, "llms-full.txt"), renderLlmsFullTxt(), "utf-8");
        },
    };
}

function appShellDevMiddleware(): Plugin {
    return {
        name: "app-shell-dev-middleware",
        configureServer(server) {
            server.middlewares.use((req, _res, next) => {
                const url = req.url?.split("?")[0] ?? "";
                if (url === "/login" || url === "/register" || url === "/app" || url.startsWith("/app/")) {
                    req.url = "/app.html";
                } else if (url === "/zh" || url === "/zh/") {
                    // 开发态没有预渲染 zh/index.html，走营销入口由前端路由渲染。
                    req.url = "/index.html";
                }
                next();
            });
        },
    };
}

export default defineConfig({
    plugins: [react(), tailwindcss(), appShellDevMiddleware(), generateSeoPages()],
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
        rollupOptions: {
            input: {
                marketing: path.resolve(__dirname, "index.html"),
                app: path.resolve(__dirname, "app.html"),
            },
        },
    },
});
