// Signing in with Google or GitHub happens by navigating to the backend, which sends the
// browser to the provider and back; when it cannot sign the browser in, it comes back
// to the sign-in page with `?error=<reason>`.

export type Provider = "github" | "google";

export const PROVIDER_LABELS: Record<Provider, string> = { github: "GitHub", google: "Google" };

/** Where the browser goes to sign in with `provider`. */
export function signInUrl(provider: Provider): string {
  return `/api/auth/${provider}/start`;
}

const REASONS: Record<string, string> = {
  too_new: "GitHub 账号注册满一年后才能用来登录。",
  email_unverified: "这个 Google 账号的邮箱还没有验证，验证后才能用来登录。",
  banned: "这位用户已被封禁，无法登录。",
  state: "登录请求已失效，请重新登录。",
  cancelled: "已取消登录。",
  provider: "暂时无法向登录服务确认你的身份，请稍后再试。",
};

/** What to tell the user about the reason the backend gave for not signing them in. */
export function signInFailure(reason: string | null): string | null {
  if (!reason) return null;
  return REASONS[reason] ?? "登录失败，请重新登录。";
}
