"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusPanel } from "@/components/status-panel";
import { frontendApi as mockApi } from "@/lib/api/frontend-api";
import type { ProjectSummaryView, Scenario } from "@/lib/api/ports";

export function ProjectList({ scenario = "ready" }: { scenario?: Scenario }) {
  const [items, setItems] = useState<ProjectSummaryView[]>([]); const [query, setQuery] = useState(scenario === "filtered-empty" ? "不存在的项目" : ""); const [loading, setLoading] = useState(true); const [error, setError] = useState("");
  async function load() { setLoading(true); setError(""); try { setItems(await mockApi.projects.list(scenario === "loading" ? "ready" : scenario)); } catch (reason) { setError(reason instanceof Error ? reason.message : "加载失败"); } finally { setLoading(false); } }
  useEffect(() => { mockApi.projects.list(scenario === "loading" ? "ready" : scenario).then(setItems).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "加载失败")).finally(() => setLoading(false)); }, [scenario]);
  const shown = useMemo(() => items.filter((item) => item.name.toLowerCase().includes(query.toLowerCase())), [items, query]);
  return <section aria-labelledby="projects-title">
    <div className="flex flex-wrap items-end justify-between gap-token-md"><div><p className="text-sm font-medium text-ai">PC-01 · FE-102</p><h1 id="projects-title" className="mt-token-xs text-3xl font-semibold">项目</h1><p className="mt-token-xs text-secondary">仅显示你有权访问的项目。</p></div><Link href="/projects/new"><Button>新建项目</Button></Link></div>
    <div className="mt-token-xl max-w-md"><label htmlFor="project-search" className="field-label">搜索项目</label><Input id="project-search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="项目名称" /></div>
    <div className="mt-token-xl">
      {loading ? <div role="status" className="grid gap-token-md sm:grid-cols-2"><span className="panel animate-pulse text-muted">正在加载项目…</span><span className="panel animate-pulse text-muted">正在加载项目…</span></div> : null}
      {error ? <StatusPanel tone="error" title="项目加载失败" action={<Button variant="secondary" onClick={load}>重试</Button>}>{error} 筛选条件已保留。</StatusPanel> : null}
      {!loading && !error && items.length === 0 && !query ? <StatusPanel title="还没有项目" action={<Link href="/projects/new"><Button>创建第一个项目</Button></Link>}>创建项目后会自动生成并进入 V1 项目概览。</StatusPanel> : null}
      {!loading && !error && shown.length === 0 && query ? <StatusPanel title="没有匹配的项目" action={<Button variant="secondary" onClick={() => setQuery("")}>清除筛选</Button>}>当前筛选“{query}”没有结果。</StatusPanel> : null}
      {!loading && !error && shown.length > 0 ? <ul className="grid gap-token-md sm:grid-cols-2">{shown.map((item) => <li key={item.id} className="panel min-w-0"><p className="truncate font-semibold">{item.name}</p><p className="mt-token-xs line-clamp-2 text-sm text-secondary">{item.goal}</p><div className="mt-token-lg flex flex-wrap gap-token-sm text-xs text-muted"><span>工作版本 {item.workingVersionNo}</span><span aria-hidden="true">·</span><span>{item.stage}</span></div><Link className="mt-token-lg inline-block text-sm font-medium text-primary-action" href={`/projects/${item.id}`}>打开项目 →</Link></li>)}</ul> : null}
    </div>
  </section>;
}
