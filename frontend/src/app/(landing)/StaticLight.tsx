import { describeScene, type BandLight, type Viewport } from "./model/scene";

/** 横屏和竖屏各画一张，样式表按画面比例选一张（和模型里竖屏的界线一样）。 */
const VIEWS: { viewport: Viewport; className: string }[] = [
  { viewport: { w: 1600, h: 900 }, className: "lp-static-light lp-static-landscape" },
  { viewport: { w: 900, h: 1600 }, className: "lp-static-light lp-static-portrait" },
];

/**
 * 静态档（省流量、不支持 WebGL，或者没有 JS）的第 1 幕：SVG 画的第 1 幕完成态，几何和着色器版同一套，
 * 都来自落地页模型。服务端渲染，不带客户端 JS。定格档里它先顶着，着色器那一帧画好就让开。
 */
export function StaticLight({ lights }: { lights: BandLight[] }) {
  return VIEWS.map(({ viewport, className }) => {
    const { beam, prism, bands } = describeScene({ lights, scroll: 1, viewport, tier: "static" });
    const glow = `lp-glow-${viewport.w}x${viewport.h}`;
    return (
      <svg
        key={className}
        className={className}
        viewBox={`0 0 ${viewport.w} ${viewport.h}`}
        preserveAspectRatio="xMidYMid slice"
        aria-hidden
      >
        <defs>
          <filter id={glow} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="7" />
          </filter>
        </defs>
        <line x1={round(beam.x0)} y1={round(beam.y0)} x2={round(beam.x1)} y2={round(beam.y1)} stroke="#fff" strokeOpacity="0.35" strokeWidth="12" filter={`url(#${glow})`} />
        <line x1={round(beam.x0)} y1={round(beam.y0)} x2={round(beam.x1)} y2={round(beam.y1)} stroke="#fff" strokeWidth="2" />
        <polygon
          points={[prism.apex, prism.left, prism.right].map((p) => p.map(round).join(",")).join(" ")}
          fill="#fff"
          fillOpacity="0.03"
          stroke="#e8eeff"
          strokeOpacity="0.6"
          strokeWidth="1.2"
        />
        {/* 棱镜里的一段光路：从入射点到出射点。 */}
        <line x1={round(beam.x1)} y1={round(beam.y1)} x2={round(prism.exit[0])} y2={round(prism.exit[1])} stroke="#fff" strokeOpacity="0.7" strokeWidth="1.5" />
        {bands.map((b) => {
          const from = [b.x + b.dx * b.start, b.y + b.dy * b.start].map(round);
          const to = [b.x + b.dx * b.length, b.y + b.dy * b.length].map(round);
          return (
            <g key={b.id} opacity={round(Math.min(1, b.intensity * 1.6))}>
              <line x1={from[0]} y1={from[1]} x2={to[0]} y2={to[1]} stroke={b.color} strokeWidth="10" strokeOpacity="0.55" filter={`url(#${glow})`} />
              <line x1={from[0]} y1={from[1]} x2={to[0]} y2={to[1]} stroke="#fff" strokeOpacity="0.85" strokeWidth="1.2" />
            </g>
          );
        })}
      </svg>
    );
  });
}

/** 坐标留一位小数，HTML 小一点。 */
const round = (x: number) => Math.round(x * 10) / 10;
