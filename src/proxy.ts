import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE, authDisabled, verifySessionToken } from "@/lib/auth";

export async function proxy(request: NextRequest) {
  if (authDisabled()) return NextResponse.next();
  const ok = await verifySessionToken(request.cookies.get(SESSION_COOKIE)?.value);
  if (ok) return NextResponse.next();
  if (request.nextUrl.pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "Yetkisiz" }, { status: 401 });
  }
  const url = new URL("/login", request.url);
  url.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(url);
}

export const config = {
  // Giriş sayfası, sağlık kontrolü ve statik dosyalar hariç her şey korunur.
  matcher: ["/((?!login|api/health|_next/static|_next/image|favicon.ico).*)"],
};
