"use client";

import { useResizable, type UseResizableSingleConfig } from "@astryxdesign/core/Resizable";
import { useLayoutEffect, useRef } from "react";

import { loadPanelSize, savePanelSize, type Panel } from "@/lib/panelSizes";

/**
 * 宽屏上可以拖动调节的一块（对话列表的宽度、输入框的高度），记住制作人上次拖到的尺寸。
 * 不用 useResizable 自带的 autoSaveId：它在渲染时读 localStorage，服务端按默认尺寸渲染的 HTML
 * 水合时对不上；这里挂上之后、浏览器画出来之前才换成记下的尺寸。
 */
export function useSavedSize(panel: Panel, config: Omit<UseResizableSingleConfig, "autoSaveId" | "onSizeChange">) {
  const region = useResizable({ ...config, onSizeChange: (size) => savePanelSize(panel, size) });
  const restored = useRef(false);
  const { resize } = region;

  useLayoutEffect(() => {
    if (restored.current) return;
    restored.current = true;
    const saved = loadPanelSize(panel);
    if (saved !== null) resize(saved);
  }, [panel, resize]);

  return region;
}
