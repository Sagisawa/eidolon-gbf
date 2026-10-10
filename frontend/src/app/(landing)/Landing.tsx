import { buttonVariants } from "@/components/ui/button";
import { copy } from "@/i18n";

import { LandingEntry } from "./LandingEntry";

const t = copy.landing;

/**
 * 落地页（ADR-0016）：`/` 和 `/about` 共用。这一版是骨架：第 0 幕的标题、首屏声明、CSS 画的静态白光，
 * 右上角的入口和页脚；光、各幕和正式字体由后续的 ticket 接上。
 *
 * 标题是服务端渲染的 DOM 文字，从一开始就可见，不用透明度动画压住：它是首屏的 LCP 元素。
 * 文案和入口按钮的类名都在服务端算好，传给客户端组件的只有字符串：文案目录、cn 不进落地页的包。
 */
export function Landing({ isSignedIn }: { isSignedIn: boolean }) {
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
      </main>

      {/* 隐私政策、使用条款在应用的根 layout 下，跨根 layout 本来就是整页加载，用普通的 <a>。 */}
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
