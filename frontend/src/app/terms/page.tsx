import Link from "next/link";

export const metadata = { title: "使用条款 · Eidolon-SC" };

export default function TermsPage() {
  return (
    <main className="settings prose">
      <header className="page-header">
        <h1>使用条款</h1>
        <Link href="/login" className="ghost-link">
          返回
        </Link>
      </header>

      <ul>
        <li>
          这是<strong>非官方的粉丝作品</strong>，与《偶像大师 闪耀色彩》的版权方和官方没有任何关系。
        </li>
        <li>
          和你说话的角色由 <strong>AI 扮演</strong>，不是真人，也不代表官方设定。她们说的话可能出错，请不要当真，也不要依赖她们做重要的决定。
        </li>
        <li>
          服务由个人部署和负担费用，<strong>不保证一直可用</strong>，可能随时调整限额、暂停或关闭，数据也可能因故丢失。
        </li>
        <li>
          你需要<strong>年满 13 岁</strong>才能使用。
        </li>
        <li>
          请不要用它做违法的事，或刻意刷用量；部署者可以封禁这样的用户。
        </li>
      </ul>
      <p>
        数据怎样保存和处理，见<Link href="/privacy">隐私政策</Link>。
      </p>
    </main>
  );
}
