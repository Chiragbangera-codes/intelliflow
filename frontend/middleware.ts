import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  // In Milestone 2, Next.js middleware provides a route protection foundation.
  // Full cookie-based middleware token verification will be active once
  // cookie storage is enabled for production.
  const path = request.nextUrl.pathname;

  // Example public paths
  const isPublicPath = path === "/login" || path === "/register";

  // Check for session cookie if present
  const token = request.cookies.get("intelliflow_access_token")?.value;

  if (isPublicPath && token) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/login", "/register", "/dashboard/:path*"],
};
