// Forwards /api/* to the backend at runtime, streaming the response body so that
// server-sent events reach the browser as they arrive.

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

async function forward(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const { search } = new URL(request.url);
  const url = `${BACKEND_URL}/api/${path.map(encodeURIComponent).join("/")}${search}`;
  const headers = new Headers();
  for (const name of ["content-type", "authorization"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const res = await fetch(url, {
    method: request.method,
    headers,
    body: hasBody ? await request.arrayBuffer() : undefined,
    cache: "no-store",
  });

  const out = new Headers();
  for (const name of ["content-type", "cache-control", "www-authenticate"]) {
    const value = res.headers.get(name);
    if (value) out.set(name, value);
  }
  return new Response(res.body, { status: res.status, headers: out });
}

export const dynamic = "force-dynamic";
export { forward as GET, forward as POST, forward as PUT, forward as PATCH, forward as DELETE };
