"use client";

import { useCallback, useLayoutEffect } from "react";
import { usePanelRef, type PanelSize } from "react-resizable-panels";

import { loadPanelSize, savePanelSize, type Panel } from "@/lib/panelSizes";

/**
 * 宽屏上可以拖动调宽窄的一栏（对话列表），记住制作人上次拖到的像素宽度。
 * 交给 shadcn Resizable 的 ResizablePanel：`panelRef` 和 `onResize` 都要传上去。
 * 不用 Group 的 defaultLayout 在渲染时读 localStorage：服务端按默认尺寸渲染的 HTML 水合时会对不上；
 * 这里挂上之后、浏览器画出来之前（layout effect）才换成记下的宽度。
 * `isShown`：这一栏现在挂着没有（对话列表只在宽屏挂上）；每次挂上都恢复一次。
 */
export function useSavedSize(panel: Panel, isShown: boolean) {
  const panelRef = usePanelRef();

  useLayoutEffect(() => {
    if (!isShown) return;
    const saved = loadPanelSize(panel);
    if (saved !== null) panelRef.current?.resize(saved);
  }, [panel, panelRef, isShown]);

  // 挂上时的第一次回调（没有上一次的尺寸）只是报告默认宽度，不记。
  const onResize = useCallback(
    (size: PanelSize, _id: string | number | undefined, previous: PanelSize | undefined) => {
      if (previous) savePanelSize(panel, size.inPixels);
    },
    [panel],
  );

  return { panelRef, onResize };
}
