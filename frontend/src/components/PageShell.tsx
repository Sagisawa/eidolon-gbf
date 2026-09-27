import { Layout, LayoutContent, LayoutFooter, LayoutHeader } from "@astryxdesign/core/Layout";
import { VStack } from "@astryxdesign/core/VStack";
import type { CSSProperties, ReactNode } from "react";

type Spacing = 0 | 0.5 | 1 | 1.5 | 2 | 3 | 4 | 5 | 6 | 8 | 10;

type PageShellProps = {
  /** 页首内容，放在带分隔线的实底页首里（DESIGN.md「Layout · 页首」）。 */
  header?: ReactNode;
  /** 起始侧的栏，例如宽屏下的对话列表；传 LayoutPanel。 */
  start?: ReactNode;
  /** 页脚内容，固定在底部。 */
  footer?: ReactNode;
  /** 内容的最大宽度，居中；表单、设置和文字页用 640。不传则铺满。 */
  contentWidth?: number;
  /** 页首、内容、页脚共用的内边距（间距刻度）。 */
  padding?: Spacing;
  /** 内容区自己滚动（默认）；内容自带滚动时（例如 ChatLayout）关掉。 */
  isScrollable?: boolean;
  children: ReactNode;
};

/**
 * 全站共用的页面外壳：占满视口的一张手帐纸（纸面底色、墨水色），里面是 Astryx Layout 的
 * 页首 / 起始栏 / 内容 / 页脚。任何新页面都从这里起步，不自己铺底色或写布局容器。
 *
 * 在这里把主题的强调色记为 `--office-ink`（制作人的墨水）：对话子树用 herVars() 换掉强调色之后，
 * 仍能用它写制作人自己的东西（DESIGN.md「The Scoped Colour Rule」）。
 */
export function PageShell({ header, start, footer, contentWidth, padding, isScrollable, children }: PageShellProps) {
  return (
    <VStack height="100dvh" style={paper}>
      <Layout
        height="fill"
        contentWidth={contentWidth}
        padding={padding}
        header={header === undefined ? undefined : <LayoutHeader hasDivider>{header}</LayoutHeader>}
        start={start}
        content={<LayoutContent role="main" isScrollable={isScrollable}>{children}</LayoutContent>}
        footer={footer === undefined ? undefined : <LayoutFooter hasDivider>{footer}</LayoutFooter>}
      />
    </VStack>
  );
}

const paper = {
  background: "var(--color-background-body)",
  color: "var(--color-text-primary)",
  "--office-ink": "var(--color-accent)",
} as CSSProperties;
