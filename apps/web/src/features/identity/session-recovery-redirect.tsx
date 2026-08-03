"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function SessionRecoveryRedirect() {
  const router = useRouter();
  useEffect(() => {
    const redirect = (event: Event) => {
      const returnTo = (event as CustomEvent<{ returnTo?: string }>).detail?.returnTo;
      const safeReturnTo = returnTo?.startsWith("/") && !returnTo.startsWith("//") ? returnTo : "/projects";
      if (window.location.pathname !== "/session/recover") router.push(`/session/recover?returnTo=${encodeURIComponent(safeReturnTo)}`);
    };
    window.addEventListener("aipdv:session-recovery", redirect);
    return () => window.removeEventListener("aipdv:session-recovery", redirect);
  }, [router]);
  return null;
}
