// wanghaobo
import type { CSSProperties } from "react";

const BAR_COLORS = ["#5a54e0", "#8d6ff2", "#ff8f6b", "#ffd479"];
const BAR_COUNT = 34;

/**
 * Hero 背景氛围层：全宽横向铺开的赛博朋克音浪光柱 + 地平线网格扫描 + 呼吸感光晕。
 * 纯 CSS 装饰，aria-hidden，不承载交互，遵循 prefers-reduced-motion 由全局样式统一处理。
 */
export function HeroAtmosphere() {
  return (
    <div aria-hidden className="hero-atmosphere">
      <div className="hero-atmosphere__eclipse" />
      <div className="hero-atmosphere__grid" />

      <div className="hero-atmosphere__flames">
        {Array.from({ length: BAR_COUNT }, (_, index) => {
          const style = {
            "--bar-color": BAR_COLORS[index % BAR_COLORS.length],
            "--bar-delay": `${(index * -0.24).toFixed(2)}s`,
            "--bar-duration": `${(2.2 + (index % 6) * 0.28).toFixed(2)}s`,
            "--flicker-delay": `${(index * -0.6).toFixed(2)}s`,
          } as CSSProperties;
          return <span className="hero-atmosphere__bar" key={index} style={style} />;
        })}
      </div>

      <div className="hero-atmosphere__scanline" />
    </div>
  );
}
