import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  const token = request.cookies.get('access_token')?.value;
  const isLoginPage = request.nextUrl.pathname.startsWith('/login');

  // 1. If not logged in and trying to access a protected route, redirect to login
  if (!token && !isLoginPage) {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  // 2. If logged in and trying to access login page, redirect to dashboard
  if (token && isLoginPage) {
    return NextResponse.redirect(new URL('/', request.url));
  }

  if (token) {
    try {
      // Decode the JWT payload to get the user's role
      const payloadBase64 = token.split('.')[1];
      const decodedJson = Buffer.from(payloadBase64, 'base64').toString();
      const payload = JSON.parse(decodedJson);
      
      const role = payload.role;

      // 3. Prevent non-super-admins from accessing the /admin route
      if (request.nextUrl.pathname.startsWith('/admin') && role !== 'super_admin') {
        return NextResponse.redirect(new URL('/', request.url));
      }
    } catch {
      // If token decoding fails, clear it and redirect to login
      const response = NextResponse.redirect(new URL('/login', request.url));
      response.cookies.delete('access_token');
      return response;
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - api (API routes)
     * - demo (the public client-facing voice demo — must be reachable without a
     *   login, since the whole point is handing a prospect a URL. It spawns agent
     *   workers, so it is rate limited server-side in tms_backend/routers/demo.py
     *   rather than by this middleware.)
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico, sitemap.xml, robots.txt (metadata files)
     */
    '/((?!api|demo|_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt).*)',
  ],
};
