/** @type {import('next').NextConfig} */

// Where the Next.js SERVER (not the browser) reaches the API. Inside Docker this
// is the compose service name; the browser never sees this value.
const BACKEND_INTERNAL_URL =
  process.env.BACKEND_INTERNAL_URL || 'http://tms-backend:8000';

const nextConfig = {
  eslint: {
    // Warning: This allows production builds to successfully complete even if
    // your project has ESLint errors.
    ignoreDuringBuilds: true,
  },

  async rewrites() {
    // Proxy /api/* through the Next.js server to the backend, so the browser
    // only ever talks to the origin it loaded the page from.
    //
    // This exists because NEXT_PUBLIC_API_URL is inlined into the client bundle
    // at BUILD time, and the value was http://localhost:8001 — which breaks the
    // moment the page is opened anywhere but the machine running Docker:
    //
    //   - On a phone, "localhost" is THE PHONE. The request never leaves the
    //     handset and the demo dies on "Could not reach the demo server".
    //   - Over an ngrok HTTPS tunnel, a page served from https:// calling an
    //     http:// API is blocked as mixed content regardless of the host.
    //   - Any cross-origin host additionally drags in CORS and preflights.
    //
    // A same-origin relative path (/api/demo/session) sidesteps all three: it
    // inherits the page's scheme and host, so the same build works on localhost,
    // through ngrok, and behind a real domain with no per-environment rebuild.
    //
    // middleware.ts deliberately excludes /api from its matcher, so these
    // proxied calls do not hit the dashboard's auth redirect.
    return [
      {
        source: '/api/:path*',
        destination: `${BACKEND_INTERNAL_URL}/:path*`,
      },
    ];
  },
};

export default nextConfig;
