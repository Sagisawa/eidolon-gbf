"use client";

import { Text } from "@astryxdesign/core/Text";
import { VisuallyHidden } from "@astryxdesign/core/VisuallyHidden";
import { VStack } from "@astryxdesign/core/VStack";
import { useEffect, useRef, useState } from "react";

import { type Bucket, labelledStretches, stretchLabel, stretchSpan } from "@/lib/dashboard";

const HEIGHT = 180;
const AXIS = { left: 56, bottom: 24, top: 8, right: 24 }; // room for the latest label
const MAX_BAR = 24;
const GAP = 2; // the surface gap between touching columns
const RADIUS = 4; // the rounded data end; the baseline end stays square

/** A column from the baseline up to `top`, rounded only at its data end. */
function column(x: number, width: number, top: number, base: number): string {
  const r = Math.min(RADIUS, width / 2, base - top);
  return `M${x},${base} V${top + r} Q${x},${top} ${x + r},${top} H${x + width - r}`
    + ` Q${x + width},${top} ${x + width},${top + r} V${base} Z`;
}

/** One stretch of the range and its value. */
export type TrendValue = { start: string; value: number };

/**
 * One series over the stretches of the range (the turns, the calls, or what was spent in
 * one currency), as columns (dataviz: a single series needs no legend; the heading names
 * it). Hovering a column reads out its stretch and value above the chart (`describe`, given
 * the stretch's index); the same words are in a table for screen readers.
 */
export function TrendChart({
  points,
  bucket,
  title,
  describe,
  empty,
  ticks: ticksFor,
  format,
}: {
  points: TrendValue[];
  bucket: Bucket;
  /** What the chart shows, for screen readers. */
  title: string;
  describe: (span: string, index: number) => string;
  empty: string;
  /** The value axis's ticks, from 0 to at least the largest value. */
  ticks: (max: number) => number[];
  format: (value: number) => string;
}) {
  const ref = useRef<SVGSVGElement>(null);
  const [width, setWidth] = useState(640);
  const [hovered, setHovered] = useState<number | null>(null);

  useEffect(() => {
    const svg = ref.current;
    if (!svg) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width || 640));
    observer.observe(svg);
    return () => observer.disconnect();
  }, []);

  const ticks = ticksFor(Math.max(0, ...points.map((p) => p.value)));
  const top = ticks[ticks.length - 1];
  const plotWidth = Math.max(1, width - AXIS.left - AXIS.right);
  const base = HEIGHT - AXIS.bottom;
  const y = (n: number) => base - (n / top) * (base - AXIS.top);
  const slot = plotWidth / Math.max(1, points.length);
  const bar = Math.max(1, Math.min(MAX_BAR, slot - GAP));
  const labelled = labelledStretches(points.length, Math.max(2, Math.floor(plotWidth / 64)));
  const shown = hovered ?? points.length - 1;
  const readout = points[shown];

  return (
    <VStack gap={2}>
      <Text type="supporting">{readout ? describe(stretchSpan(readout.start, bucket), shown) : empty}</Text>
      <svg
        ref={ref}
        width="100%"
        height={HEIGHT}
        role="img"
        aria-label={title}
        onMouseLeave={() => setHovered(null)}
        style={{ display: "block", overflow: "visible" }}
      >
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={AXIS.left}
              x2={width - AXIS.right}
              y1={y(tick)}
              y2={y(tick)}
              stroke="var(--color-border)"
              strokeWidth={1}
            />
            <text
              x={AXIS.left - 8}
              y={y(tick)}
              textAnchor="end"
              dominantBaseline="middle"
              fill="var(--color-text-secondary)"
              style={{ fontSize: "var(--text-supporting-size)", fontVariantNumeric: "tabular-nums" }}
            >
              {format(tick)}
            </text>
          </g>
        ))}
        {points.map((point, i) => {
          const x = AXIS.left + slot * i + (slot - bar) / 2;
          const isHovered = hovered === i;
          return (
            <g key={point.start} onMouseEnter={() => setHovered(i)}>
              {/* The hit target is the whole slot, taller and wider than the column. */}
              <rect x={AXIS.left + slot * i} y={AXIS.top} width={slot} height={base - AXIS.top} fill="transparent" />
              {isHovered && (
                <rect
                  x={AXIS.left + slot * i}
                  y={AXIS.top}
                  width={slot}
                  height={base - AXIS.top}
                  fill="var(--color-overlay-hover)"
                />
              )}
              {point.value > 0 && (
                <path d={column(x, bar, y(point.value), base)} fill="var(--color-data-categorical-blue)" />
              )}
              {labelled.has(i) && (
                <text
                  x={x + bar / 2}
                  y={HEIGHT - 6}
                  textAnchor="middle"
                  fill="var(--color-text-secondary)"
                  style={{ fontSize: "var(--text-supporting-size)" }}
                >
                  {stretchLabel(point.start, bucket)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <VisuallyHidden>
        <table>
          <tbody>
            {points.map((point, i) => (
              <tr key={point.start}>
                <td>{describe(stretchSpan(point.start, bucket), i)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </VisuallyHidden>
    </VStack>
  );
}
