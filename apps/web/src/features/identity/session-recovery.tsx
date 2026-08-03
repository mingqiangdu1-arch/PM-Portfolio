"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { StatusPanel } from "@/components/status-panel";
import { frontendApi } from "@/lib/api/frontend-api";

const safeReturnTo = (value: string | null | undefined) =>
  value?.startsWith("/") && !value.startsWith("//") ? value : "/projects";

export function SessionRecovery({ returnTo }: { returnTo: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const target = safeReturnTo(returnTo);

  async function refresh() {
    setBusy(true);
    setError("");
    try {
      await frontendApi.identity.refresh();
      // A successful refresh only restores the session. It never replays the
      // operation that was interrupted by the expiry.
      router.push(target);
    } catch {
      setError("会话恢复失败，请重新登录。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <StatusPanel
      tone={error ? "error" : "warning"}
      title="会话已失效"
      action={
        <div className="flex flex-wrap gap-token-sm">
          <Button onClick={refresh} loading={busy}>
            恢复会话
          </Button>
          <Button
            variant="secondary"
            onClick={() => router.push(`/login?returnTo=${encodeURIComponent(target)}`)}
          >
            重新登录
          </Button>
        </div>
      }
    >
      <p>安全返回地址与未提交内容应保留；恢复后不会自动重放敏感动作。</p>
      {error ? <p className="mt-token-xs">{error}</p> : null}
    </StatusPanel>
  );
}
