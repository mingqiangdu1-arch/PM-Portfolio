import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  transpilePackages: ["@aipdv/design-tokens"],
};

export default nextConfig;
