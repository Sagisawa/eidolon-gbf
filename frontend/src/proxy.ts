// Gives every page the site's Content-Security-Policy as it is served. It is set here rather
// than in next.config, which is fixed when the image is built: where the stands are kept is
// only known where it runs. Pages rendered ahead of time stay so.

import { NextResponse } from "next/server";
import { contentSecurityPolicy } from "@/lib/contentSecurityPolicy";

export function proxy() {
  const response = NextResponse.next();
  response.headers.set(
    "Content-Security-Policy",
    contentSecurityPolicy(process.env.EIDOLON_STAND_ASSETS_URL),
  );
  return response;
}

export const config = {
  // Not the API or Next's own files; what is served from public/ gets it too, harmlessly.
  matcher: ["/((?!api/|_next/).*)"],
};
