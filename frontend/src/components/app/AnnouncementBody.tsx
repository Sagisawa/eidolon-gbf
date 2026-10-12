import Markdown, { type Components } from "react-markdown";

/** 正文里留下的写法；别的写法不成为对应的元素，字照样留下（见 `DEGRADED`）。 */
const ALLOWED = ["p", "br", "strong", "em", "a", "ul", "ol", "li", "code"];

/** 不开放、但有字的写法：标题退成一段，引用、代码块拆掉外壳只留里面的字，图片只留说明文字。 */
const DEGRADED = ["h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "img"];

const COMPONENTS: Components = {
  p: ({ children }) => <p className="whitespace-pre-line">{children}</p>,
  h1: ({ children }) => <p>{children}</p>,
  h2: ({ children }) => <p>{children}</p>,
  h3: ({ children }) => <p>{children}</p>,
  h4: ({ children }) => <p>{children}</p>,
  h5: ({ children }) => <p>{children}</p>,
  h6: ({ children }) => <p>{children}</p>,
  blockquote: ({ children }) => <>{children}</>,
  pre: ({ children }) => <p className="whitespace-pre-line">{children}</p>,
  img: ({ alt }) => <>{alt}</>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="rounded-sm text-foreground underline underline-offset-4 outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      {children}
    </a>
  ),
  ul: ({ children }) => <ul className="flex list-disc flex-col gap-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="flex list-decimal flex-col gap-1 pl-5">{children}</ol>,
  li: ({ children }) => <li className="whitespace-pre-line">{children}</li>,
  code: ({ children }) => <code className="rounded-sm bg-muted px-1 font-mono">{children}</code>,
};

/**
 * 一条公告的正文（GLOSSARY.md「公告」），Markdown 写的。后台的预览和用户看到的都用它，两边一模一样。
 * 只开段落、换行、加粗、斜体、链接、列表和行内代码；标题、引用、代码块、图片退成纯文字，分隔线去掉，
 * 不解析原始 HTML。段内的换行照原样换行（不必行尾加两个空格）。链接都在新标签页打开，不打断进行中的通话。
 * 字号是 Body（15px）。
 */
export function AnnouncementBody({ body }: { body: string }) {
  return (
    <div className="flex flex-col gap-3 text-body break-words">
      <Markdown
        allowedElements={[...ALLOWED, ...DEGRADED]}
        unwrapDisallowed
        skipHtml
        components={COMPONENTS}
      >
        {body}
      </Markdown>
    </div>
  );
}
