/** 日语原文：标上 lang，换成日文字体。Astryx 的 Text/Stack 不接受 lang，所以用一个语义 span。 */
export function Ja({ children }: { children: React.ReactNode }) {
  return (
    <span lang="ja" style={{ display: "contents", fontFamily: "var(--font-ja), var(--font-family-body)" }}>
      {children}
    </span>
  );
}
