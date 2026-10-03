import type { NextConfig } from "next";

const backendApiUrl =
  process.env.BACKEND_API_URL?.trim() || "http://127.0.0.1:5000";
const backend = new URL(backendApiUrl);

if (
  !["http:", "https:"].includes(backend.protocol) ||
  backend.username ||
  backend.password ||
  backend.pathname !== "/" ||
  backend.search ||
  backend.hash
) {
  throw new Error("BACKEND_API_URL must be an HTTP(S) origin without credentials or a path.");
}

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: backend.origin + "/api/:path*",
      },
    ];
  },
};

export default nextConfig;
