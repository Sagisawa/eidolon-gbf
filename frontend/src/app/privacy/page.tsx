import Link from "next/link";

export const metadata = { title: "隐私政策 · Eidolon-SC" };

export default function PrivacyPage() {
  return (
    <main className="settings prose">
      <header className="page-header">
        <h1>隐私政策</h1>
        <Link href="/login" className="ghost-link">
          返回
        </Link>
      </header>

      <h2>我们保存哪些数据</h2>
      <ul>
        <li>
          <strong>登录方式</strong>：你用来登录的 Google 或 GitHub 账号的编号、显示名和邮箱。我们拿不到你的密码。
        </li>
        <li>
          <strong>对话</strong>：你对角色说的话（打字的，以及通话时语音识别出的文字）和角色的回复。通话的录音不保存。
        </li>
        <li>
          <strong>记忆</strong>：角色从对话中记下的关于你的事，所有角色共用，你可以在「管理记忆」页查看和删除。
        </li>
        <li>
          <strong>制作人档案</strong>：你设置的称呼、性别和时区。
        </li>
        <li>
          <strong>自带密钥</strong>：如果你填了自己的 API key，它会加密后保存，界面上只显示末 4 位。
        </li>
        <li>
          <strong>会话和用量</strong>：保持登录用的会话，以及最近 24 小时内的对话和通话次数（用于限额）。
        </li>
      </ul>

      <h2>这些数据会交给哪些第三方处理</h2>
      <ul>
        <li>
          <strong>语言模型服务</strong>：扮演角色、提炼记忆、判断要不要回忆剧情时，对话内容和相关记忆会发给部署者配置的语言模型服务。
        </li>
        <li>
          <strong>语音服务</strong>：通话时，你的声音会发给 Soniox 做语音识别，角色的回复会发给 Fish Audio 合成语音。
        </li>
        <li>
          <strong>向量化和重排服务</strong>：为了在对话中找到相关的剧情和记忆，你说的话和记忆会发给部署者选择的向量化服务（硅基流动或
          Google Gemini）和重排服务（硅基流动）。
        </li>
        <li>
          <strong>登录服务</strong>：登录时，Google 或 GitHub 会知道你登录了这个网站。
        </li>
      </ul>
      <p>
        如果你填了自带密钥，对应的内容会发到<strong>你自己选择的服务商</strong>，由你和该服务商之间的约定管辖。
      </p>

      <h2>怎样删除你的全部数据</h2>
      <p>
        在设置页点「删除我的全部数据」，再确认一次，你的记忆、对话、制作人档案、登录方式、自带密钥、会话和用量记录都会被彻底删除（不是标记删除），所有设备都会退出登录。之后再用同一个
        Google 或 GitHub 账号登录，会是一位全新的用户。
      </p>
      <p>已经发给第三方服务的内容，按各服务自己的政策保存和删除。</p>
    </main>
  );
}
