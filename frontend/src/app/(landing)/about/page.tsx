import type { Metadata } from "next";
import { cookies } from "next/headers";

import { isSignedIn } from "@/lib/backend";

import { Landing } from "../Landing";

export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

/** `/about`：和 `/` 同一个落地页，但不把已登录的用户送走（设置页的「关于 Eidolon-SC」到这里），只是入口换成「继续」。 */
export default async function About() {
  return <Landing isSignedIn={await isSignedIn((await cookies()).toString())} />;
}
