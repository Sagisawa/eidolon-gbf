"use client";

// 临时示例路由用（清理波随 /preview 一起删）：给 <html> 加上或去掉 .dark，不改系统设置也能看深色。
import { useState } from "react";

import { Button } from "@/components/ui/button";

export function DarkToggle() {
  const [dark, setDark] = useState(false);
  return (
    <Button
      variant="outline"
      size="sm"
      aria-pressed={dark}
      onClick={() => {
        document.documentElement.classList.toggle("dark", !dark);
        setDark(!dark);
      }}
    >
      {dark ? "取消强制深色" : "强制深色"}
    </Button>
  );
}
