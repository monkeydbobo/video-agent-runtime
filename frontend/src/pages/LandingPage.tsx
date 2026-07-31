import {
  ArrowDownRight,
  ArrowRight,
  FileText,
  Layers3,
  Maximize2,
  MessageCircle,
  Minimize2,
  Pause,
  Play,
  Sparkles,
  Volume2,
  VolumeX,
  WandSparkles,
} from "lucide-react";
import { type Ref, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation } from "wouter";
import { BRAND } from "@/branding";
import { HeroAtmosphere } from "@/components/landing/HeroAtmosphere";
import { ParticleField } from "@/components/landing/ParticleField";
import "./LandingPage.css";

const FEATURE_ICONS = [FileText, Layers3, WandSparkles] as const;
const HERO_VIDEO_MP4_SRC = "https://s15-sl.cybercut.ai/kos/s101/nlav112623/oioi_demo_web_h264_audio.mp4";
const HERO_VIDEO_WEBM_SRC = "https://s15-sl.cybercut.ai/kos/s101/nlav112623/oioi_demo_web_vp9_audio.webm";
const HERO_VIDEO_POSTER = "/hero/oioi-demo-poster.jpg";

function HeroVideo({ muted = true, videoRef }: { muted?: boolean; videoRef?: Ref<HTMLVideoElement> }) {
  return (
    // The decorative soundtrack does not carry page content, so captions are not required.
    // eslint-disable-next-line jsx-a11y/media-has-caption
    <video
      aria-hidden
      ref={videoRef}
      autoPlay
      crossOrigin="anonymous"
      loop
      muted={muted}
      playsInline
      poster={HERO_VIDEO_POSTER}
      preload="auto"
    >
      <source src={HERO_VIDEO_WEBM_SRC} type='video/webm; codecs="vp9"' />
      <source src={HERO_VIDEO_MP4_SRC} type="video/mp4" />
    </video>
  );
}

export function LandingPage() {
  const { t, i18n } = useTranslation("landing");
  const [, setLocation] = useLocation();
  const isChinese = i18n.resolvedLanguage?.startsWith("zh") ?? true;
  const [activeClip, setActiveClip] = useState(0);
  const [isPaused, setIsPaused] = useState(true);
  const [isHeroVideoActive, setIsHeroVideoActive] = useState(true);
  const [isHeroMuted, setIsHeroMuted] = useState(true);
  const [isShowreelReady, setIsShowreelReady] = useState(false);
  const heroRef = useRef<HTMLElement>(null);
  const heroVideoRef = useRef<HTMLVideoElement>(null);
  const showreelRef = useRef<HTMLElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  const clips = [
    { src: "/showreel/elephants-dream-1.mp4", poster: "/showreel/elephants-dream-1.jpg", label: t("clip_dream_one"), number: "01" },
    { src: "/showreel/elephants-dream-2.mp4", poster: "/showreel/elephants-dream-2.jpg", label: t("clip_dream_two"), number: "02" },
    { src: "/showreel/big-buck-bunny.mp4", poster: "/showreel/big-buck-bunny.jpg", label: t("clip_bunny"), number: "03" },
  ];
  const selectedClip = clips[activeClip];

  const selectClip = (index: number) => {
    setIsShowreelReady(true);
    setActiveClip(index);
    setIsPaused(false);
  };

  const togglePlayback = () => {
    if (!isShowreelReady) {
      setIsShowreelReady(true);
      setIsPaused(false);
      return;
    }
    const player = videoRef.current;
    if (!player) return;
    if (player.paused) {
      void player.play().then(() => setIsPaused(false), () => setIsPaused(true));
    } else {
      player.pause();
      setIsPaused(true);
    }
  };

  const activateHeroVideo = () => {
    setIsHeroMuted(true);
    setIsHeroVideoActive(true);
    requestAnimationFrame(() => {
      const hero = heroRef.current;
      if (!hero || typeof hero.scrollIntoView !== "function") return;
      const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
      hero.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
    });
  };

  const toggleHeroSound = () => {
    const nextMuted = !isHeroMuted;
    if (heroVideoRef.current) heroVideoRef.current.muted = nextMuted;
    setIsHeroMuted(nextMuted);
  };

  const restoreHeroEffects = () => {
    setIsHeroMuted(true);
    setIsHeroVideoActive(false);
  };

  useEffect(() => {
    if (heroVideoRef.current) heroVideoRef.current.muted = isHeroMuted;
  }, [isHeroMuted, isHeroVideoActive]);

  useEffect(() => {
    const section = showreelRef.current;
    if (!section || typeof IntersectionObserver === "undefined") {
      setIsShowreelReady(true);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return;
        setIsShowreelReady(true);
        observer.disconnect();
      },
      { threshold: 0.25 },
    );
    observer.observe(section);
    return () => observer.disconnect();
  }, []);

  const features = [
    { title: t("feature_script_title"), body: t("feature_script_body") },
    { title: t("feature_assets_title"), body: t("feature_assets_body") },
    { title: t("feature_video_title"), body: t("feature_video_body") },
  ];
  const guideLocale = isChinese ? "zh" : "en";
  const guides = [
    { slug: "novel-to-video", title: t("guide_novel_title"), body: t("guide_novel_body") },
    { slug: "ai-storyboard-generator", title: t("guide_storyboard_title"), body: t("guide_storyboard_body") },
  ];

  return (
    <main className={`landing-page${isHeroVideoActive ? " landing-page--hero-video" : ""}`}>
      {isHeroVideoActive ? null : <ParticleField />}
      <div aria-hidden className="landing-mesh" />
      <div aria-hidden className="landing-mesh landing-mesh--alt" />

      <nav
        className={`landing-nav${isHeroVideoActive ? " landing-nav--immersive" : ""}`}
        aria-label={t("navigation")}
      >
        <button className="landing-brand" onClick={() => setLocation("/")} type="button">
          <span className="landing-brand__mark"><img alt="" height="26" src="/android-chrome-192x192.png" width="26" /></span>
          <span>{BRAND.name}</span>
        </button>
        <div className="landing-nav__right">
          <a href="#capabilities">{t("nav_capabilities")}</a>
          <a href="#workflow">{t("nav_workflow")}</a>
          <div className="landing-language" aria-label={t("language_switcher")}>
            <button className={isChinese ? "is-active" : ""} type="button" onClick={() => void i18n.changeLanguage("zh")}>中</button>
            <button className={!isChinese ? "is-active" : ""} type="button" onClick={() => void i18n.changeLanguage("en")}>EN</button>
          </div>
          <button className="landing-login" type="button" onClick={() => setLocation("/login")}>
            {t("login")}
            <ArrowRight aria-hidden size={15} />
          </button>
        </div>
      </nav>

      <section
        className={`landing-hero${isHeroVideoActive ? " landing-hero--video-active" : ""}`}
        aria-labelledby="landing-title"
        ref={heroRef}
      >
        {isHeroVideoActive ? (
          <>
            <div className="landing-hero__video-backdrop">
              <HeroVideo muted={isHeroMuted} videoRef={heroVideoRef} />
              <span aria-hidden className="landing-hero__video-shade" />
            </div>
            <div className="landing-hero__video-controls" aria-label={t("hero_video_controls")} role="group">
              <button
                aria-label={isHeroMuted ? t("hero_video_unmute") : t("hero_video_mute")}
                aria-pressed={!isHeroMuted}
                className={`landing-hero__video-control${isHeroMuted ? "" : " is-active"}`}
                onClick={toggleHeroSound}
                type="button"
              >
                {isHeroMuted ? <VolumeX aria-hidden size={15} /> : <Volume2 aria-hidden size={15} />}
                <span>{isHeroMuted ? t("hero_video_unmute") : t("hero_video_mute")}</span>
              </button>
              <button
                aria-label={t("hero_video_exit")}
                className="landing-hero__video-control"
                onClick={restoreHeroEffects}
                type="button"
              >
                <Minimize2 aria-hidden size={15} />
                <span>{t("hero_video_restore")}</span>
              </button>
            </div>
          </>
        ) : (
          <HeroAtmosphere />
        )}
        <div className="landing-hero__copy">
          <p className="landing-badge"><Sparkles aria-hidden size={13} /> {t("eyebrow")}</p>
          <h1 id="landing-title"><span>{t("title_before")}</span> <em>{t("title_emphasis")}</em>{t("title_after")}</h1>
          <p className="landing-lede">{t("description")}</p>
          <div className="landing-actions">
            <button className="landing-cta" type="button" onClick={() => setLocation("/login")}>
              <Play aria-hidden size={14} fill="currentColor" />
              {t("start")}
              <ArrowRight aria-hidden size={17} />
            </button>
            <a className="landing-text-link" href="#workflow">{t("learn_more")}</a>
          </div>
        </div>

        {isHeroVideoActive ? null : (
          <button
            aria-label={t("hero_video_enter")}
            className="landing-reel"
            onClick={activateHeroVideo}
            type="button"
          >
            <span className="landing-reel__code">A-01 / 24 FPS</span>
            <span className="landing-reel__scene">
              <HeroVideo />
            </span>
            <span className="landing-reel__caption">
              <span>{t("reel_project")}</span>
              <strong>00:00:10</strong>
            </span>
            <span className="landing-reel__tag">
              <Maximize2 aria-hidden size={15} />
              {t("hero_video_expand")}
            </span>
          </button>
        )}
      </section>

      <section className="landing-showreel" aria-labelledby="showreel-title" ref={showreelRef}>
        <div className="landing-showreel__heading">
          <p className="landing-kicker">{t("showreel_kicker")}</p>
          <h2 id="showreel-title">{t("showreel_title")}</h2>
          <p>{t("showreel_body")}</p>
        </div>
        <div className="landing-player">
          <video
            key={selectedClip.src}
            ref={videoRef}
            autoPlay={isShowreelReady}
            loop
            muted
            playsInline
            poster={selectedClip.poster}
            preload={isShowreelReady ? "auto" : "none"}
            src={isShowreelReady ? selectedClip.src : undefined}
            onCanPlay={(event) => {
              void event.currentTarget.play().then(() => setIsPaused(false), () => setIsPaused(true));
            }}
            onPause={() => setIsPaused(true)}
            onPlay={() => setIsPaused(false)}
          />
          <div className="landing-player__shade" />
          <button className="landing-player__toggle" type="button" onClick={togglePlayback} aria-label={isPaused ? t("play_clip") : t("pause_clip")}>
            {isPaused ? <Play aria-hidden size={17} fill="currentColor" /> : <Pause aria-hidden size={17} fill="currentColor" />}
          </button>
          <div className="landing-player__label"><span>{selectedClip.number} / 03</span><strong>{selectedClip.label}</strong></div>
        </div>
        <div className="landing-clip-list" role="tablist" aria-label={t("clips_label")}>
          {clips.map((clip, index) => (
            <button
              aria-selected={activeClip === index}
              className={activeClip === index ? "is-active" : ""}
              key={clip.number}
              onClick={() => selectClip(index)}
              role="tab"
              type="button"
            >
              <span>{clip.number}</span><strong>{clip.label}</strong><ArrowDownRight aria-hidden size={16} />
            </button>
          ))}
        </div>
        <p className="landing-attribution">
          {t("clip_attribution")}{" "}
          <a href="https://orange.blender.org/" rel="noreferrer" target="_blank">Elephants Dream</a> (
          <a href="https://creativecommons.org/licenses/by/2.5/" rel="noreferrer" target="_blank">CC BY 2.5</a>) ·{" "}
          <a href="https://www.bigbuckbunny.org/" rel="noreferrer" target="_blank">Big Buck Bunny</a> (
          <a href="https://creativecommons.org/licenses/by/3.0/" rel="noreferrer" target="_blank">CC BY 3.0</a>)
        </p>
      </section>

      <section className="landing-features" id="capabilities" aria-label={t("features_label")}>
        <div className="landing-features__intro">
          <p>{t("features_label")}</p>
          <span>01 — 03</span>
        </div>
        {features.map((feature, index) => {
          const Icon = FEATURE_ICONS[index];
          return (
            <article className="landing-feature" key={feature.title}>
              <span className="landing-feature__number">0{index + 1}</span>
              <Icon aria-hidden size={20} strokeWidth={1.35} />
              <h2>{feature.title}</h2>
              <p>{feature.body}</p>
            </article>
          );
        })}
      </section>

      <section className="landing-workflow" id="workflow" aria-labelledby="workflow-title">
        <div>
          <p className="landing-kicker">{t("workflow_eyebrow")}</p>
          <h2 id="workflow-title">{t("workflow_title")}</h2>
        </div>
        <ol>
          {["workflow_one", "workflow_two", "workflow_three", "workflow_four"].map((key, index) => (
            <li key={key}>
              <span>0{index + 1}</span>
              <p>{t(key)}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="landing-guides" aria-labelledby="guides-title">
        <div className="landing-guides__heading">
          <p className="landing-kicker">{t("guides_eyebrow")}</p>
          <h2 id="guides-title">{t("guides_title")}</h2>
        </div>
        <div className="landing-guides__list">
          {guides.map((guide, index) => (
            <a href={`/${guideLocale}/${guide.slug}`} key={guide.slug}>
              <span>0{index + 1}</span>
              <div><strong>{guide.title}</strong><p>{guide.body}</p></div>
              <ArrowRight aria-hidden size={17} />
            </a>
          ))}
        </div>
      </section>

      <section className="landing-contact" aria-labelledby="contact-title">
        <div className="landing-contact__intro">
          <p className="landing-kicker">{t("contact_eyebrow")}</p>
          <h2 id="contact-title">{t("contact_title")}</h2>
          <p>{t("contact_body")}</p>
        </div>
        <div className="landing-contact__channels">
          <a className="landing-contact__discord" href="https://discord.gg/4fdsuGXE5" rel="noreferrer" target="_blank">
            <span className="landing-contact__icon"><MessageCircle aria-hidden size={22} /></span>
            <span>
              <strong>{t("contact_discord_title")}</strong>
              <small>{t("contact_discord_body")}</small>
            </span>
            <ArrowRight aria-hidden size={20} />
          </a>
        </div>
      </section>

      <footer className="landing-footer">
        <p>© {new Date().getFullYear()} {BRAND.name}</p>
        <button type="button" onClick={() => setLocation("/login")}>{t("footer_login")}</button>
      </footer>
    </main>
  );
}
