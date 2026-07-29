// wanghaobo
import { memo, useEffect, useRef } from "react";

type Particle = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  hue: number;
  drift: number;
};

/** 品牌配色的粒子/连线色板：iris → iris-2 → 珊瑚 → 金 */
const PARTICLE_COLORS = ["90, 84, 224", "141, 111, 242", "255, 143, 107", "255, 180, 90"];

const DENSITY = 1 / 11000; // particles per px^2 —— 比初版密一倍多
const MAX_PARTICLES = 220;
const LINK_DISTANCE = 150;
const BASE_SPEED = 0.32;
const MOUSE_RADIUS = 170;
const TRAIL_FADE = "rgba(251, 251, 253, 0.14)"; // 与页面底色一致，制造拖尾而不留白痕

function createParticles(width: number, height: number): Particle[] {
  const count = Math.min(MAX_PARTICLES, Math.max(40, Math.round(width * height * DENSITY)));
  return Array.from({ length: count }, () => ({
    x: Math.random() * width,
    y: Math.random() * height,
    vx: (Math.random() - 0.5) * BASE_SPEED,
    vy: (Math.random() - 0.5) * BASE_SPEED,
    radius: 1.4 + Math.random() * 2.6,
    hue: Math.floor(Math.random() * PARTICLE_COLORS.length),
    drift: Math.random() * Math.PI * 2,
  }));
}

/** 简单的多层正弦噪声场，代替 perlin noise，让粒子沿着平滑弯曲的流线运动 */
function flowAngle(x: number, y: number, t: number): number {
  return (
    Math.sin(x * 0.0022 + t * 0.35) * 1.4 +
    Math.cos(y * 0.0026 - t * 0.28) * 1.4 +
    Math.sin((x + y) * 0.0016 + t * 0.18) * 1.1
  );
}

/**
 * 全屏固定的流动粒子背景：流场驱动的运动轨迹 + 拖尾辉光 + 鼠标交互连线。
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
    let clock = 0;
    const mouse = { x: -9999, y: -9999, active: false };

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
      ctx.fillStyle = "rgba(251, 251, 253, 1)";
      ctx.fillRect(0, 0, width, height);
    };

    const handlePointerMove = (event: PointerEvent) => {
      mouse.x = event.clientX;
      mouse.y = event.clientY;
      mouse.active = true;
    };
    const handlePointerLeave = () => {
      mouse.active = false;
    };

    const step = () => {
      clock += 0.016;

      // 用极低透明度的底色覆盖整帧，而不是完全清空，从而留下拖尾轨迹
      ctx.fillStyle = TRAIL_FADE;
      ctx.fillRect(0, 0, width, height);

      for (const particle of particles) {
        const angle = flowAngle(particle.x, particle.y, clock);
        const targetVx = Math.cos(angle) * BASE_SPEED;
        const targetVy = Math.sin(angle) * BASE_SPEED;
        particle.vx += (targetVx - particle.vx) * 0.045;
        particle.vy += (targetVy - particle.vy) * 0.045;

        if (mouse.active) {
          const dx = particle.x - mouse.x;
          const dy = particle.y - mouse.y;
          const distance = Math.sqrt(dx * dx + dy * dy);
          if (distance < MOUSE_RADIUS && distance > 0.01) {
            const push = ((MOUSE_RADIUS - distance) / MOUSE_RADIUS) * 0.9;
            particle.vx += (dx / distance) * push;
            particle.vy += (dy / distance) * push;
          }
        }

        particle.x += particle.vx;
        particle.y += particle.vy;
        if (particle.x < -30) particle.x = width + 30;
        if (particle.x > width + 30) particle.x = -30;
        if (particle.y < -30) particle.y = height + 30;
        if (particle.y > height + 30) particle.y = -30;
      }

      ctx.lineWidth = 1;
      for (let i = 0; i < particles.length; i++) {
        const a = particles[i];
        for (let j = i + 1; j < particles.length; j++) {
          const b = particles[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const distance = Math.sqrt(dx * dx + dy * dy);
          if (distance < LINK_DISTANCE) {
            const alpha = (1 - distance / LINK_DISTANCE) ** 1.6 * 0.42;
            ctx.strokeStyle = `rgba(${PARTICLE_COLORS[a.hue]}, ${alpha})`;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
      }

      for (const particle of particles) {
        const pulse = 0.75 + Math.sin(clock * 1.6 + particle.drift) * 0.25;
        const radius = particle.radius * pulse;
        const glow = ctx.createRadialGradient(particle.x, particle.y, 0, particle.x, particle.y, radius * 4.5);
        glow.addColorStop(0, `rgba(${PARTICLE_COLORS[particle.hue]}, 0.85)`);
        glow.addColorStop(0.4, `rgba(${PARTICLE_COLORS[particle.hue]}, 0.28)`);
        glow.addColorStop(1, `rgba(${PARTICLE_COLORS[particle.hue]}, 0)`);
        ctx.beginPath();
        ctx.fillStyle = glow;
        ctx.arc(particle.x, particle.y, radius * 4.5, 0, Math.PI * 2);
        ctx.fill();

        ctx.beginPath();
        ctx.fillStyle = `rgba(${PARTICLE_COLORS[particle.hue]}, 0.95)`;
        ctx.arc(particle.x, particle.y, radius, 0, Math.PI * 2);
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
    window.addEventListener("pointermove", handlePointerMove, { passive: true });
    window.addEventListener("pointerleave", handlePointerLeave, { passive: true });
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
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerleave", handlePointerLeave);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, []);

  return <canvas aria-hidden className="landing-particles" ref={canvasRef} />;
}

export const ParticleField = memo(ParticleFieldImpl);
