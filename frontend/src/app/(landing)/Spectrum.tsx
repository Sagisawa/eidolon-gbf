import type { CSSProperties } from "react";

import type { Spectrum as SpectrumModel } from "./model/spectrum";

/**
 * 第 2 幕的光谱：全部偶像的竖排日文名，按组合分段，每段开头是组合名。名字和组合名都是真文本，
 * 服务端渲染，不带客户端 JS。这一版只有 DOM；光、横滚和聚焦由后续的 ticket 接上。
 * 她的颜色由落地页模型在服务端算好，以 CSS 变量交给样式表。
 */
export function Spectrum({ spectrum }: { spectrum: SpectrumModel }) {
  if (spectrum.idols.length === 0) return null;
  return (
    <div className="lp-spectrum">
      {spectrum.units.map((unit, u) => (
        <section key={unit.name ?? ""} className="lp-seg" aria-labelledby={unit.name ? `lp-unit-${u}` : undefined}>
          {unit.name && (
            <h2 id={`lp-unit-${u}`} className="lp-seg-name" lang="ja">
              {unit.name}
            </h2>
          )}
          <ol className="lp-seg-row">
            {unit.idols.map(({ id, name, idolId, colors }) => (
              <li
                key={id}
                className="lp-plate"
                style={{ "--her-ink": colors.ink, "--her-halo": colors.halo } as CSSProperties}
              >
                {idolId !== null && (
                  <span className="lp-no" aria-hidden>
                    {String(idolId).padStart(2, "0")}
                  </span>
                )}
                <span className="lp-name" lang="ja">
                  {name}
                </span>
                <span className="lp-hex" aria-hidden>
                  {colors.official.toUpperCase()}
                </span>
              </li>
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}
