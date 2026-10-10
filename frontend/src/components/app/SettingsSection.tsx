import { useId, type ReactNode } from "react";

import { SectionHeading } from "@/components/app/SubpageHeader";

/** 说明文字的行长上限：一行四十来个汉字。是 Tailwind 类，写进 className。 */
export const PROSE_WIDTH = "max-w-[42em]";

type Props = {
  /**
   * 节标题。设置页里只有一节的标签页不写（标签名就是标题），这时这一节也不自己声明标签关系，
   * 读屏靠外面的标签面板读出它属于哪个标签。
   */
  title?: string;
  /** 页内链接跳到这一节用的锚点。 */
  id?: string;
  /** 标题下的一段说明。 */
  description?: ReactNode;
  children?: ReactNode;
};

/**
 * 设置页的一节：标题、说明、内容，下沿一条细分隔线。
 * 不套卡片、不加描边（DESIGN.md「The Flat Rule」），一节一节靠分隔线和留白分开。
 */
export function SettingsSection({ title, id, description, children }: Props) {
  const headingId = useId();
  return (
    <section
      id={id}
      aria-labelledby={title ? headingId : undefined}
      className="flex flex-col gap-4 border-b py-6"
    >
      {(title || description) && (
        <div className="flex flex-col gap-1">
          {title && <SectionHeading id={headingId}>{title}</SectionHeading>}
          {description && <p className={`${PROSE_WIDTH} text-body text-muted-foreground`}>{description}</p>}
        </div>
      )}
      {children}
    </section>
  );
}
