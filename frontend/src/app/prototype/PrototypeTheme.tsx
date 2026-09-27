"use client";

import { Theme } from "@astryxdesign/core/theme";
import { VStack } from "@astryxdesign/core/VStack";

import { notebookTheme } from "./theme";

export function PrototypeTheme({ className, children }: { className: string; children: React.ReactNode }) {
  return (
    <Theme theme={notebookTheme} mode="system">
      <VStack
        className={className}
        height="100dvh"
        style={
          {
            background: "var(--color-background-body)",
            color: "var(--color-text-primary)",
            // 制作人的墨水色：在这里取下主题的强调色，角色子树换掉强调色后仍然可用。
            "--office-ink": "var(--color-accent)",
          } as React.CSSProperties
        }
      >
        {children}
      </VStack>
    </Theme>
  );
}
