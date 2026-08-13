"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { StatusPanel } from "@/components/status-panel";
import { frontendApi as mockApi } from "@/lib/api/frontend-api";
import type { ProjectOverviewView, Scenario } from "@/lib/api/ports";

export function ProjectOverview({ projectId, viewedVersionId, created, scenario = "ready" }: { projectId: string; viewedVersionId?: string; created?: boolean; scenario?: Scenario }) {
  const [data, setData] = useState<ProjectOverviewView | null>(null);
  const [error, setError] = useState("");
  async function load() { setError(""); try { if (scenario === "failure") throw new Error("项目概览暂时无法加载。"); setData(await mockApi.projects.overview(projectId, viewedVersionId)); } catch (reason) { setError(reason instanceof Error ? reason.message : "加载失败"); } }
  useEffect(() => { const request = scenario === "failure" ? Promise.reject(new Error("项目概览暂时无法加载。")) : mockApi.projects.overview(projectId, viewedVersionId); request.then(setData).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "加载失败")); }, [projectId, viewedVersionId, scenario]);
  if (scenario === "forbidden") return <StatusPanel tone="error" title="无权查看此项目" action={<Link href="/projects"><Button variant="secondary">返回项目列表</Button></Link>}>业务正文已隐藏。请联系项目负责人申请查看权限。</StatusPanel>;
  if (error) return <StatusPanel tone="error" title="概览加载失败" action={<Button variant="secondary" onClick={load}>重试</Button>}>{error}</StatusPanel>;
  if (!data) return <div role="status" className="panel animate-pulse text-muted">正在加载项目概览…</div>;
  const readOnly = scenario === "readonly" || data.isHistory;
  return <section aria-labelledby="overview-title"><div className="flex flex-wrap items-end justify-between gap-token-md"><div><p className="text-sm font-medium text-ai">PC-03 · FE-102</p><h1 id="overview-title" className="mt-token-xs text-3xl font-semibold">{data.name}</h1><p className="mt-token-xs text-secondary">查看版本 {data.viewedVersionNo} · 工作版本 {data.workingVersionNo}</p></div><div className="flex flex-wrap gap-token-sm"><Link href={`/projects/${projectId}/files`}><Button variant="secondary">项目资料</Button></Link><Link href={`/projects/${projectId}/versions`}><Button variant="secondary">版本管理</Button></Link></div></div><div className="mt-token-xl space-y-token-md">{created ? <StatusPanel tone="success" title="项目与 V1 已创建">已进入 V1 项目概览，请选择下一步。</StatusPanel> : null}{readOnly ? <StatusPanel tone="warning" title="历史版本只读">切换查看版本不会改变当前工作版本。若需修改，请基于此版本安全派生。</StatusPanel> : null}<div className="grid gap-token-md lg:grid-cols-3"><article className="panel lg:col-span-2"><h2 className="font-semibold">下一步</h2><p className="mt-token-sm text-secondary">{data.blocker ? `先补充：${data.blocker}` : "可继续需求澄清"}</p><div className="mt-token-lg">{readOnly ? <Button disabled>历史版本不可编辑</Button> : <Link href={`/projects/${projectId}/versions/${data.viewedVersionId}/requirements`}><Button>继续当前阶段</Button></Link>}</div></article><article className="panel"><h2 className="font-semibold">版本上下文</h2><dl className="mt-token-sm space-y-token-xs text-sm"><div className="flex justify-between gap-token-md"><dt className="text-muted">查看</dt><dd>{data.viewedVersionNo}</dd></div><div className="flex justify-between gap-token-md"><dt className="text-muted">工作</dt><dd>{data.workingVersionNo}</dd></div><div className="flex justify-between gap-token-md"><dt className="text-muted">阶段</dt><dd>{data.stage}</dd></div></dl></article></div><article className="panel"><h2 className="font-semibold">产物与最近活动</h2><p className="mt-token-sm text-secondary">当前尚无正式产物。项目创建不会自动生成 Requirement、PRD 或 Flow。</p></article></div></section>;
}
