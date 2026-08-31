"use client";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { StatusPanel } from "@/components/status-panel";
import { frontendApi as mockApi } from "@/lib/api/frontend-api";
import type { ProjectOverviewView, Scenario, VersionView } from "@/lib/api/ports";
export function VersionManager({ projectId, scenario = "ready" }: { projectId: string; scenario?: Scenario }) {
  const [items, setItems] = useState<VersionView[]>([]);
  const [loadedProjectId, setLoadedProjectId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState("");
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let active = true;

    void mockApi.projects
      .versions(projectId)
      .then((next) => {
        if (!active) return;
        setItems(next);
        setLoadError("");
        setLoadedProjectId(projectId);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setLoadError(reason instanceof Error ? reason.message : "版本列表加载失败，请重试。");
        setLoadedProjectId(projectId);
      });

    return () => {
      active = false;
    };
  }, [projectId, retryCount]);

  const loading = loadedProjectId !== projectId;

  const header = (
    <div>
      <p className="text-sm font-medium text-ai">PC-06 · FE-103</p>
      <h1 className="mt-token-xs text-3xl font-semibold">版本管理</h1>
      <p className="mt-token-xs text-secondary">查看、设为工作版本与派生是三个独立操作。</p>
    </div>
  );

  if (loading) {
    return (
      <section>
        {header}
        <div role="status" className="panel mt-token-xl animate-pulse text-muted">
          正在加载版本谱系…
        </div>
      </section>
    );
  }

  if (loadError) {
    return (
      <section>
        {header}
        <div className="mt-token-xl">
          <StatusPanel
            tone="error"
            title="版本列表加载失败"
            action={
              <Button
                onClick={() => {
                  setLoadedProjectId(null);
                  setLoadError("");
                  setItems([]);
                  setRetryCount((count) => count + 1);
                }}
              >
                重试
              </Button>
            }
          >
            {loadError} 当前页面未改变工作版本。
          </StatusPanel>
        </div>
      </section>
    );
  }

  if (!items.length) {
    return (
      <section>
        {header}
        <div className="mt-token-xl">
          <StatusPanel tone="neutral" title="暂无版本">
            该项目尚未形成可查看的版本谱系。
          </StatusPanel>
        </div>
      </section>
    );
  }

  return <section>{header}{scenario === "forbidden" ? <div className="mt-token-xl"><StatusPanel tone="error" title="无版本管理权限">你仍可查看允许访问的版本，但不能设为工作版本或派生。</StatusPanel></div> : null}<ol className="mt-token-xl space-y-token-md">{items.map((version) => <li key={version.id} className="panel flex flex-wrap items-center justify-between gap-token-md"><div><div className="flex items-center gap-token-sm"><strong>{version.number}</strong>{version.isWorking ? <span className="rounded-full bg-primary-subtle px-token-sm py-token-xs text-xs text-success">当前工作版本</span> : null}</div><p className="mt-token-xs text-sm text-secondary">{version.reason}</p></div><div className="flex flex-wrap gap-token-sm"><Link href={`/projects/${projectId}/versions/${version.id}?state=${scenario}`}><Button variant="secondary">查看详情</Button></Link><Link href={`/projects/${projectId}/versions/${version.id}/implementation-plan?state=${scenario}`}><Button variant="secondary">实现计划</Button></Link><Link href={`/projects/${projectId}/versions/${version.id}/confirmation?state=${scenario}`}><Button variant="secondary">实现确认</Button></Link></div></li>)}</ol></section>;
}

export function VersionDetail({ projectId, versionId, scenario = "ready" }: { projectId: string; versionId: string; scenario?: Scenario }) { const [message, setMessage] = useState(""); const [error, setError] = useState(""); const [reason, setReason] = useState(""); const [confirmWorking, setConfirmWorking] = useState(false); const [busy, setBusy] = useState(false); const [overview, setOverview] = useState<ProjectOverviewView | null>(null); useEffect(() => { void mockApi.projects.overview(projectId, versionId).then(setOverview).catch((value: unknown) => setError(value instanceof Error ? value.message : "版本详情加载失败")); }, [projectId, versionId]); const history = overview?.isHistory ?? false; async function setWorking() { setBusy(true); setError(""); try { await mockApi.projects.setWorking(projectId, versionId, overview?.projectVersion ?? 1, scenario); setMessage("工作版本已更新。重复请求不会产生额外版本。"); } catch (e) { setError(e instanceof Error ? e.message : "设置失败"); } finally { setBusy(false); } } async function derive(event: FormEvent) { event.preventDefault(); setBusy(true); setError(""); try { const result = await mockApi.projects.derive(projectId, { sourceVersionId: versionId, reason, inheritContext: true, expectedProjectVersion: overview?.projectVersion ?? 1 }, scenario); setMessage(`${result.number} 已从 ${versionId.endsWith("v1") ? "V1" : "V2"} 派生；尚未自动设为工作版本。`); } catch (e) { setError(e instanceof Error ? e.message : "派生失败"); } finally { setBusy(false); } } const forbidden = scenario === "forbidden"; return <section><p className="text-sm font-medium text-ai">版本 · 查看与派生</p><h1 className="mt-token-xs text-3xl font-semibold">版本详情</h1><p className="mt-token-xs text-secondary">查看 {history ? "V1" : "V2"} · 当前工作版本 V2</p><div className="mt-token-xl space-y-token-md">{history ? <StatusPanel tone="warning" title="历史版本只读">查看此页绝不会改变当前工作版本。</StatusPanel> : null}{scenario === "conflict" ? <StatusPanel tone="warning" title="存在并发更新">确认操作时将校验最新项目版本；冲突后不会覆盖其他成员的更新。</StatusPanel> : null}{error ? <StatusPanel tone="error" title={scenario === "conflict" ? "版本冲突" : "操作失败"}>{error} 当前选择与原因已保留。</StatusPanel> : null}{message ? <StatusPanel tone="success" title="操作成功">{message}</StatusPanel> : null}<article className="panel"><h2 className="font-semibold">设置工作版本</h2><p className="mt-token-xs text-sm text-secondary">这是独立确认操作，不由“查看版本”触发。</p><label className="mt-token-md block text-sm"><input type="checkbox" checked={confirmWorking} onChange={(e) => setConfirmWorking(e.target.checked)} /> <span className="ml-token-xs">我确认了解对当前协作上下文的影响</span></label><Button className="mt-token-md" onClick={setWorking} loading={busy} disabled={!confirmWorking || forbidden}>设为工作版本</Button></article><form onSubmit={derive} className="panel"><h2 className="font-semibold">基于此版本派生</h2><p className="mt-token-xs text-sm text-secondary">来源固定；默认仅继承允许的项目上下文，不默认继承流程或计划。</p><label className="mt-token-md block"><span className="field-label">派生原因</span><textarea className="textarea-field min-h-24" value={reason} onChange={(e) => setReason(e.target.value)} required /></label><Button className="mt-token-md" type="submit" loading={busy} disabled={forbidden}>确认派生新版本</Button></form></div></section>; }
