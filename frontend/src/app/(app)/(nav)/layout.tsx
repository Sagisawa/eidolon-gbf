import type { ReactNode } from "react";

import { DirectoryProvider } from "@/components/conversations/ConversationDirectory";

/**
 * 导航外壳：对话（列表和她的对话页）和设置共用的 layout（.scratch/app-navigation「路由和外壳」）。
 * 对话目录由这里持有，整个外壳只载入一次，在对话和设置之间换页时不重新载入。
 * 记忆、后台、`/about`、隐私政策、使用条款、登录、同意条款在外壳外面。
 */
export default function NavLayout({ children }: { children: ReactNode }) {
  return <DirectoryProvider>{children}</DirectoryProvider>;
}
