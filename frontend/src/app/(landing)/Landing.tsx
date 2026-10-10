import { buttonVariants } from "@/components/ui/button";
import { copy } from "@/i18n";
import type { Character } from "@/lib/api";

import { LandingEntry } from "./LandingEntry";
import { LightStage } from "./LightStage";
import { lightsOf, prepareSpectrum } from "./model/spectrum";
import { Spectrum } from "./Spectrum";
import { StaticLight } from "./StaticLight";

const t = copy.landing;

/**
 * 落地页（ADR-0016）：`/` 和 `/about` 共用。第 0 幕的标题、首屏声明和 CSS 画的白光；第 1 幕白光射进
 * 棱镜、散成一道道印象色（LightStage 加 OGL 光层，静态档是 StaticLight 的 SVG）；第 2 幕光谱的
 * 竖排名单；右上角的入口和页脚。其余各幕由后续的 ticket 接上。
 *
 * 标题是服务端渲染的 DOM 文字，从一开始就可见，不用透明度动画压住：它是首屏的 LCP 元素。
 * 文案、颜色和入口按钮的类名都在服务端算好，传给客户端组件的只有字符串和数：文案目录、颜色算法、
 * cn 不进落地页的包。
 */
export function Landing({ isSignedIn, characters }: { isSignedIn: boolean; characters: Character[] }) {
  const spectrum = prepareSpectrum(characters);
  const lights = lightsOf(spectrum);
  return (
    <div className="lp-root">
      <header className="lp-top">
        <LandingEntry
          isSignedIn={isSignedIn}
          label={isSignedIn ? t.continue : t.signIn}
          className={buttonVariants({ variant: "outline" })}
        />
      </header>

      <main>
        <section className="lp-act0" aria-labelledby="lp-title">
          <div className="lp-beam" aria-hidden />
          <div className="lp-act0-text">
            <h1 id="lp-title" className="lp-title">
              {copy.app.name}
            </h1>
            <p className="lp-lede">{copy.app.description}</p>
          </div>
          <p className="lp-disclaimer">{t.disclaimer}</p>
        </section>
        <LightStage lights={lights}>
          <section className="lp-act1" aria-labelledby={lights.length > 0 ? "lp-act1-title" : undefined}>
            <StaticLight lights={lights} />
            {lights.length > 0 && (
              <div className="lp-act1-copy">
                <p className="lp-act1-name" lang="ja" aria-hidden>
                  {t.act1.name}
                </p>
                <div>
                  <h2 id="lp-act1-title" className="lp-act1-title">
                    {t.act1.title(String(lights.length))}
                  </h2>
                  <p className="lp-act1-body">{t.act1.body}</p>
                </div>
              </div>
            )}
          </section>
        </LightStage>
        <Spectrum spectrum={spectrum} />
      </main>

      {/* 用普通的 <a>：next/link 不进落地页首屏的包；隐私政策、使用条款在应用的根 layout 下，跨根 layout 本来就是整页加载。 */}
      <footer className="lp-footer">
        <p>{copy.legal.disclaimer}</p>
        <p className="lp-footer-links">
          <a href="/privacy">{copy.legal.privacy}</a>
          <a href="/terms">{copy.legal.terms}</a>
        </p>
      </footer>
    </div>
  );
}
