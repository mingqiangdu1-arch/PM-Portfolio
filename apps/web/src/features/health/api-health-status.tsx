"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { frontendApi, frontendApiMode } from "@/lib/api/frontend-api";
import type { HealthView } from "@/lib/api/ports";

export function ApiHealthStatus() {
  const [health, setHealth] = useState<HealthView | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { setHealth(await frontendApi.health.get()); }
    catch (reason) { setHealth(null); setError(reason instanceof Error ? reason.message : "API 健康检查失败。"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => {
    let active = true;
    frontendApi.health.get()
      .then((value) => { if (active) setHealth(value); })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "API 健康检查失败。"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  if (loading) return <p role="status" className="mt-token-lg text-sm text-secondary">正在检查 API 健康状态…</p>;
  if (error) return <div role="alert" className="mt-token-lg status-banner bg-error-subtle text-error"><strong>API 不可用。</strong> {error}<div className="mt-token-sm"><Button variant="secondary" onClick={load}>重新检查</Button></div></div>;
  return <dl className="mt-token-lg grid grid-cols-[auto_1fr] gap-x-token-lg gap-y-token-sm text-sm"><dt className="text-muted">API 模式</dt><dd>{frontendApiMode}</dd><dt className="text-muted">API 状态</dt><dd>{health?.status}</dd><dt className="text-muted">API 服务</dt><dd>{health?.service}</dd><dt className="text-muted">API 发布</dt><dd>{health?.release}</dd><dt className="text-muted">Trace</dt><dd className="break-all">{health?.traceId}</dd></dl>;
}
