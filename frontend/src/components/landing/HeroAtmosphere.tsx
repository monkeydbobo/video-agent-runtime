// wanghaobo
import type { CSSProperties } from "react";

const BAR_COUNT = 48;

/**
 * Hero 背景氛围层：一条全宽的火焰光柱波形。
 * 每根光柱的峰值高度沿包络线分布（中轴最高、两端收束），动画延迟按到中轴的距离递进，
 * 形成从中心向两侧扩散的呼吸波；颜色沿横向从 iris 渐变到珊瑚。
 * 纯 CSS 装饰，aria-hidden，不承载交互，prefers-reduced-motion 下静止为固定波形。
 */
export function HeroAtmosphere() {
  return (
    <div aria-hidden className="hero-atmosphere">
      <div className="hero-atmosphere__flames">
        {Array.from({ length: BAR_COUNT }, (_, index) => {
          const progress = index / (BAR_COUNT - 1);
          // 包络线：sin 主峰叠加一层低频起伏，避免机械的对称拱形
          const envelope = 0.3 + Math.sin(progress * Math.PI) ** 1.3 * 0.56 + Math.sin(progress * Math.PI * 3) * 0.05;
          const style = {
            "--bar-progress": progress.toFixed(3),
            "--bar-peak": `${(envelope * 100).toFixed(1)}%`,
            "--bar-delay": `${(-Math.abs(progress - 0.5) * 3.2).toFixed(2)}s`,
            "--bar-duration": `${(4.2 + Math.sin(progress * Math.PI * 3) * 0.6).toFixed(2)}s`,
          } as CSSProperties;
          return <span className="hero-atmosphere__bar" key={index} style={style} />;
        })}
      </div>
      <div className="hero-atmosphere__horizon" />
    </div>
  );
}
