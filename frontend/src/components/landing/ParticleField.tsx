// wanghaobo
import { memo, useEffect, useRef } from "react";

type Particle = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  hue: number;
};

const PARTICLE_COLORS = [
  "90, 84, 224", // iris
  "141, 111, 242", // iris-2
  "255, 143, 107", // coral
  "255, 212, 121", // gold
];

const DENSITY = 1 / 22000; // particles per px^2
const MAX_PARTICLES = 140;
const LINK_DISTANCE = 130;
const SPEED = 0.18;

function createParticles(width: number, height: number): Particle[] {
  const count = Math.min(MAX_PARTICLES, Math.round(width * height * DENSITY));
  return Array.from({ length: count }, () => ({
    x: Math.random() * width,
    y: Math.random() * height,
    vx: (Math.random() - 0.5) * SPEED,
    vy: (Math.random() - 0.5) * SPEED,
    radius: 1 + Math.random() * 1.6,
    hue: Math.floor(Math.random() * PARTICLE_COLORS.length),
  }));
}

/**
 * 全屏固定的流动粒子背景，纯 Canvas 实现，低透明度不干扰内容阅读。
 * 遵循 prefers-reduced-motion，标签页不可见时暂停动画以节省资源。
 */
function ParticleFieldImpl() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let width = window.innerWidth;
    let height = window.innerHeight;
    let dpr = Math.min(window.devicePixelRatio || 1, 2);
    let particles: Particle[] = createParticles(width, height);
    let animationFrame = 0;
    let running = true;

    const resize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      particles = createParticles(width, height);
    };

    const step = () => {
      ctx.clearRect(0, 0, width, height);

      for (const particle of particles) {
        particle.x += particle.vx;
        particle.y += particle.vy;
        if (particle.x < -20) particle.x = width + 20;
        if (particle.x > width + 20) particle.x = -20;
        if (particle.y < -20) particle.y = height + 20;
        if (particle.y > height + 20) particle.y = -20;
      }

      for (let i = 0; i < particles.length; i++) {
        const a = particles[i];
        for (let j = i + 1; j < particles.length; j++) {
          const b = particles[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const distance = Math.sqrt(dx * dx + dy * dy);
          if (distance < LINK_DISTANCE) {
            const alpha = (1 - distance / LINK_DISTANCE) * 0.16;
            ctx.strokeStyle = `rgba(${PARTICLE_COLORS[a.hue]}, ${alpha})`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
      }

      for (const particle of particles) {
        ctx.beginPath();
        ctx.fillStyle = `rgba(${PARTICLE_COLORS[particle.hue]}, 0.55)`;
        ctx.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
        ctx.fill();
      }

      if (running) animationFrame = requestAnimationFrame(step);
    };

    const handleVisibility = () => {
      running = document.visibilityState === "visible" && !prefersReducedMotion;
      if (running) {
        cancelAnimationFrame(animationFrame);
        animationFrame = requestAnimationFrame(step);
      }
    };

    resize();
    window.addEventListener("resize", resize);
    document.addEventListener("visibilitychange", handleVisibility);

    if (prefersReducedMotion) {
      step();
      running = false;
    } else {
      running = true;
      animationFrame = requestAnimationFrame(step);
    }

    return () => {
      running = false;
      cancelAnimationFrame(animationFrame);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, []);

  return <canvas aria-hidden className="landing-particles" ref={canvasRef} />;
}

export const ParticleField = memo(ParticleFieldImpl);
