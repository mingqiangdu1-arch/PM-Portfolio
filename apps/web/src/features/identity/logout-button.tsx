"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { StatusPanel } from "@/components/status-panel";
import { Button } from "@/components/ui/button";
import { frontendApi } from "@/lib/api/frontend-api";

export function LogoutButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  async function logout() {
    setBusy(true);
    setError(false);
    try {
      // The adapter owns local credential cleanup in its finally block, even
      // when the server-side logout request fails.
      await frontendApi.identity.logout();
      router.push("/login?loggedOut=1");
    } catch {
      // Do not expose adapter errors (which may contain trace or transport
      // details) in the shell. The local session has already been cleared by
      // the adapter, so leave an explicit, safe path back to login.
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-token-sm">
      <button
        type="button"
        onClick={logout}
        disabled={busy}
        className="rounded-token-md px-token-sm py-token-xs text-secondary hover:bg-subtle disabled:cursor-not-allowed"
      >
        {busy ? "正在退出…" : "退出"}
      </button>
      {error ? (
        <StatusPanel
          tone="error"
          title="退出未完成"
          action={
            <Button variant="secondary" onClick={() => router.push("/login?loggedOut=1")}>
              前往登录
            </Button>
          }
        >
          本地会话已清理，请重新登录后继续。
        </StatusPanel>
      ) : null}
    </div>
  );
}
