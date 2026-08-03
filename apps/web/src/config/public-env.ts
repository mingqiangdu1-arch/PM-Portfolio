const allowedEnvironments = ["local", "ci", "staging", "production"] as const;

export type PublicAppEnvironment = (typeof allowedEnvironments)[number];

export type PublicApiMode = "mock" | "real";

export const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function getPublicApiMode(value = process.env.NEXT_PUBLIC_API_MODE): PublicApiMode {
  const candidate = value ?? "mock";
  if (candidate !== "mock" && candidate !== "real") {
    throw new Error("NEXT_PUBLIC_API_MODE must be mock or real.");
  }
  return candidate;
}

export function getPublicAppEnvironment(
  value = process.env.NEXT_PUBLIC_APP_ENV,
): PublicAppEnvironment {
  const candidate = value ?? "local";
  if (!allowedEnvironments.includes(candidate as PublicAppEnvironment)) {
    throw new Error("NEXT_PUBLIC_APP_ENV must be local, ci, staging, or production.");
  }
  return candidate as PublicAppEnvironment;
}
