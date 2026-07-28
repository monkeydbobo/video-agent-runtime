// wanghaobo
import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";

type Node = { id: string; x: number; y: number; labelKey: string; delay: number };

const NODES: Node[] = [
  { id: "script", x: 5, y: 12, labelKey: "atmosphere_node_script", delay: 0 },
  { id: "assets", x: 13, y: 88, labelKey: "atmosphere_node_assets", delay: 1.1 },
  { id: "storyboard", x: 47, y: 4, labelKey: "atmosphere_node_storyboard", delay: 2.2 },
  { id: "video", x: 90, y: 5, labelKey: "atmosphere_node_video", delay: 0.6 },
  { id: "export", x: 90, y: 95, labelKey: "atmosphere_node_export", delay: 1.7 },
];

const LINKS: [string, string][] = [
  ["script", "storyboard"],
  ["storyboard", "video"],
  ["video", "export"],
  ["script", "assets"],
  ["assets", "export"],
];

const BAR_COLORS = ["#5a54e0", "#8d6ff2", "#ff8f6b", "#ffd479"];
const BAR_COUNT = 18;

function nodeById(id: string): Node {
  const node = NODES.find((candidate) => candidate.id === id);
  if (!node) throw new Error(`Unknown hero atmosphere node: ${id}`);
  return node;
}

/**
 * Hero 背景氛围层：起伏的音浪光柱 + 呼吸感光晕 + 带标签的脉冲网络节点。
 * 纯 CSS/SVG 装饰，aria-hidden，不承载交互，遵循 prefers-reduced-motion 由全局样式统一处理。
 */
export function HeroAtmosphere() {
  const { t } = useTranslation("landing");

  return (
    <div aria-hidden className="hero-atmosphere">
      <div className="hero-atmosphere__eclipse" />

      <div className="hero-atmosphere__flames">
        {Array.from({ length: BAR_COUNT }, (_, index) => {
          const style = {
            "--bar-color": BAR_COLORS[index % BAR_COLORS.length],
            "--bar-delay": `${(index * -0.37).toFixed(2)}s`,
            "--bar-duration": `${(2.6 + (index % 5) * 0.35).toFixed(2)}s`,
          } as CSSProperties;
          return <span className="hero-atmosphere__bar" key={index} style={style} />;
        })}
      </div>

      <svg className="hero-atmosphere__wires">
        {LINKS.map(([fromId, toId]) => {
          const from = nodeById(fromId);
          const to = nodeById(toId);
          return (
            <line
              className="hero-atmosphere__wire"
              key={`${fromId}-${toId}`}
              x1={`${from.x}%`}
              y1={`${from.y}%`}
              x2={`${to.x}%`}
              y2={`${to.y}%`}
            />
          );
        })}
      </svg>

      <div className="hero-atmosphere__nodes">
        {NODES.map((node) => (
          <span
            className="hero-atmosphere__node"
            key={node.id}
            style={{ left: `${node.x}%`, top: `${node.y}%`, animationDelay: `${node.delay}s` }}
          >
            <i className="hero-atmosphere__dot" style={{ animationDelay: `${node.delay}s` }} />
            <b>{t(node.labelKey)}</b>
          </span>
        ))}
      </div>
    </div>
  );
}
