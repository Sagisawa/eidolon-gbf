import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type PageShellProps = {
  /** 页首内容（通常是 SubpageHeader），放在实底、下沿一条细线的页首里。 */
  header?: ReactNode;
  /** 页脚内容（例如 LegalFooter），固定在底部，上沿一条细线。 */
  footer?: ReactNode;
  /** `column`：页首、内容、页脚都收在 640px 的一栏里居中，表单、设置和文字页用它（默认）。`full`：铺满。 */
  width?: "column" | "full";
  /** 内容区自己滚动（默认）；内容自带滚动时（例如对话页）关掉。 */
  isScrollable?: boolean;
  children: ReactNode;
};

/**
 * 全站共用的页面外壳：占满视口的中性底（DESIGN.md「The Producer's Phone」），上面是页首、内容、页脚。
 * 任何新页面都从这里起步，不自己铺底色。
 */
export function PageShell({ header, footer, width = "column", isScrollable = true, children }: PageShellProps) {
  const column = width === "column" && "mx-auto w-full max-w-160 px-4";
  return (
    <div className="flex h-dvh flex-col bg-background text-foreground">
      {header !== undefined && (
        <header className="shrink-0 border-b">
          <div className={cn("flex min-h-14 items-center", column || "px-4")}>{header}</div>
        </header>
      )}
      <main className={cn("flex min-h-0 flex-1 flex-col", isScrollable ? "overflow-y-auto" : "overflow-hidden")}>
        <div className={cn("flex flex-1 flex-col", column && cn(column, "py-6"))}>{children}</div>
      </main>
      {footer !== undefined && (
        <footer className="shrink-0 border-t">
          <div className={cn("py-3", column || "px-4")}>{footer}</div>
        </footer>
      )}
    </div>
  );
}
