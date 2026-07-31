import { ArrowLeft, ArrowRight, Check, Play, Sparkles } from "lucide-react";
import { useEffect } from "react";
import { useLocation } from "wouter";
import { BRAND } from "@/branding";
import { NotFoundPage } from "@/pages/NotFoundPage";
import seoPages from "@/seo/seo-pages.json";
import "./SeoLandingPage.css";

type SeoPageData = (typeof seoPages)[number];

const SEO_HERO_VIDEO_WEBM = "https://s15-sl.cybercut.ai/kos/s101/nlav112623/oioi_demo_web_vp9_audio.webm";
const SEO_HERO_VIDEO_MP4 = "https://s15-sl.cybercut.ai/kos/s101/nlav112623/oioi_demo_web_h264_audio.mp4";

function setMeta(selector: string, content: string): void {
  const element = document.querySelector<HTMLMetaElement>(selector);
  if (element) element.content = content;
}

function findPage(pathname: string): SeoPageData | undefined {
  return seoPages.find((page) => page.path === pathname.replace(/\/$/, ""));
}

export function SeoLandingPage() {
  const [location, setLocation] = useLocation();
  const page = findPage(location);

  useEffect(() => {
    if (!page) return;
    document.documentElement.lang = page.locale === "zh" ? "zh-CN" : "en";
    document.title = page.title;
    setMeta('meta[name="description"]', page.description);
    setMeta('meta[property="og:title"]', page.title);
    setMeta('meta[property="og:description"]', page.description);
    setMeta('meta[property="og:url"]', `https://oioi.bio${page.path}`);
    setMeta('meta[name="twitter:title"]', page.title);
    setMeta('meta[name="twitter:description"]', page.description);
    const canonical = document.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (canonical) canonical.href = `https://oioi.bio${page.path}`;
  }, [page]);

  if (!page) return <NotFoundPage />;

  const isZh = page.locale === "zh";
  const related = seoPages.filter((candidate) => candidate.locale === page.locale && candidate.path !== page.path);

  return (
    <main className="seo-page">
      <div aria-hidden className="seo-page__grain" />
      <nav className="seo-nav" aria-label={isZh ? "主导航" : "Main navigation"}>
        <button type="button" className="seo-brand" onClick={() => setLocation("/")}>
          <span className="seo-brand__mark"><img alt="" height="29" src="/android-chrome-192x192.png" width="29" /></span>
          {BRAND.name}
        </button>
        <div>
          <a href={page.alternatePath}>{isZh ? "EN" : "中文"}</a>
          <button className="seo-nav__login" type="button" onClick={() => setLocation("/login")}>
            {isZh ? "进入工作台" : "Enter studio"} <ArrowRight aria-hidden size={14} />
          </button>
        </div>
      </nav>

      <article>
        <header className="seo-hero">
          <div className="seo-hero__video" aria-hidden>
            {/* Decorative background video mirrors the homepage hero and carries no page content. */}
            <video autoPlay loop muted playsInline poster="/hero/oioi-demo-poster.jpg" preload="metadata">
              <source src={SEO_HERO_VIDEO_WEBM} type='video/webm; codecs="vp9"' />
              <source src={SEO_HERO_VIDEO_MP4} type="video/mp4" />
            </video>
          </div>
          <div className="seo-hero__copy">
            <a href="/" className="seo-back"><ArrowLeft aria-hidden size={13} /> {isZh ? "返回首页" : "Back home"}</a>
            <p className="seo-eyebrow"><Sparkles aria-hidden size={13} /> {page.eyebrow}</p>
            <h1>{page.headline}</h1>
            <p className="seo-lede">{page.lede}</p>
            <button type="button" className="seo-primary" onClick={() => setLocation("/login")}>
              <Play aria-hidden fill="currentColor" size={13} />
              {isZh ? "开始创作" : "Start creating"} <ArrowRight aria-hidden size={16} />
            </button>
          </div>
          <aside className="seo-cut-sheet" aria-label={isZh ? "能力摘要" : "Capability summary"}>
            <p>OIOI / PRODUCTION NOTE</p>
            <strong>{page.eyebrow}</strong>
            <ul>
              {page.highlights.map((highlight) => <li key={highlight}><Check aria-hidden size={14} />{highlight}</li>)}
            </ul>
            <span>TEXT → SCRIPT → SHOT → MOTION</span>
          </aside>
        </header>

        <section className="seo-problem">
          <p>{isZh ? "为什么需要工作流" : "Why workflow matters"}</p>
          <div>
            <h2>{page.problemTitle}</h2>
            <p>{page.problemBody}</p>
          </div>
        </section>

        <section className="seo-process" aria-labelledby="seo-process-title">
          <div className="seo-section-heading">
            <p>{isZh ? "制作路径" : "Production path"}</p>
            <h2 id="seo-process-title">{isZh ? "从输入到可以审阅的画面。" : "From source material to reviewable motion."}</h2>
          </div>
          <ol>
            {page.steps.map((step, index) => (
              <li key={step.title}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <div><h3>{step.title}</h3><p>{step.body}</p></div>
              </li>
            ))}
          </ol>
        </section>

        <section className="seo-faq" aria-labelledby="seo-faq-title">
          <div className="seo-section-heading">
            <p>FAQ</p>
            <h2 id="seo-faq-title">{isZh ? "创作者通常会问。" : "What creators usually ask."}</h2>
          </div>
          <div className="seo-faq__list">
            {page.faq.map((item) => (
              <details key={item.question}>
                <summary>{item.question}<span>+</span></summary>
                <p>{item.answer}</p>
              </details>
            ))}
          </div>
        </section>

        <section className="seo-related" aria-label={isZh ? "相关指南" : "Related guides"}>
          <p>{isZh ? "继续了解" : "Continue exploring"}</p>
          <div>
            {related.map((item) => (
              <a key={item.path} href={item.path}>
                <span>{item.eyebrow}</span>
                <strong>{item.headline}</strong>
                <ArrowRight aria-hidden size={17} />
              </a>
            ))}
          </div>
        </section>
      </article>

      <footer className="seo-footer">
        <span>© {new Date().getFullYear()} {BRAND.name}</span>
        <a href="/">{isZh ? "产品首页" : "Product home"}</a>
      </footer>
    </main>
  );
}
