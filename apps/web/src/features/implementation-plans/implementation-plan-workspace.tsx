"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { StatusPanel } from "@/components/status-panel";
import { frontendApi } from "@/lib/api/frontend-api";
import type { FrontendApi, ImplementationPlanView, PlanContentView, ProjectCapabilities, Scenario } from "@/lib/api/ports";

const pretty = (value: unknown) => JSON.stringify(value, null, 2);

const planSections = ["features", "businessRules", "stateRequirements", "exceptions", "interactions", "dependencies", "acceptanceScope"] as const;
type PlanSection = (typeof planSections)[number];

const generatedItemKey = (section: PlanSection, index: number) => `${section.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`)}_${index + 1}`;

function normalizePlanContent(raw: unknown): PlanContentView {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("Plan Content JSON 必须是对象。");
  const value = raw as Record<string, unknown>;
  if (value.schemaVersion !== "implementation_plan.mvp3.v1") throw new Error("schemaVersion 必须是 implementation_plan.mvp3.v1。");
  const usedKeys = new Set<string>();
  const normalized = { schemaVersion: "implementation_plan.mvp3.v1" as const } as PlanContentView;
  for (const section of planSections) {
    const items = value[section];
    if (!Array.isArray(items)) throw new Error(`${section} 必须是数组。`);
    normalized[section] = items.map((item, index) => {
      if (typeof item === "string") {
        const description = item.trim();
        if (!description) throw new Error(`${section}[${index}] 描述不能为空。`);
        const key = generatedItemKey(section, index);
        if (usedKeys.has(key)) throw new Error(`Plan item key 重复：${key}`);
        usedKeys.add(key);
        return { key, description };
      }
      if (!item || typeof item !== "object" || Array.isArray(item)) throw new Error(`${section}[${index}] 必须包含 key 和 description。`);
      const candidate = item as Record<string, unknown>;
      if (typeof candidate.key !== "string" || typeof candidate.description !== "string") throw new Error(`${section}[${index}] 必须包含 key 和 description。`);
      const key = candidate.key.trim();
      const description = candidate.description.trim();
      if (!key || !description) throw new Error(`${section}[${index}] 的 key 和 description 不能为空。`);
      if (usedKeys.has(key)) throw new Error(`Plan item key 重复：${key}`);
      usedKeys.add(key);
      return { key, description };
    });
  }
  return normalized;
}

export function ImplementationPlanWorkspace({ projectId, projectVersionId, scenario = "ready", api = frontendApi }: { projectId?: string; projectVersionId: string; scenario?: Scenario; api?: FrontendApi }) {
  const [plans, setPlans] = useState<ImplementationPlanView[]>([]);
  const [selected, setSelected] = useState<ImplementationPlanView | null>(null);
  const [name, setName] = useState("");
  const [sourcePrdVersionId, setSourcePrdVersionId] = useState("");
  const [sourceDesignReviewId, setSourceDesignReviewId] = useState("");
  const [sourceSummary, setSourceSummary] = useState("");
  const [sourceBlocker, setSourceBlocker] = useState("");
  const [contentText, setContentText] = useState("");
  const [changeNote, setChangeNote] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [detailReadyFor, setDetailReadyFor] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<ProjectCapabilities | null>(null);

  const canWrite = scenario !== "forbidden" && capabilities?.canPlanWrite === true;
  const canSetEffective = scenario !== "forbidden" && capabilities?.canSetEffective === true;

  async function load() {
    setLoading(true); setError("");
    try { const next = await api.implementationPlans.list(projectVersionId); const currentPlanId = selected?.id; setPlans(next); setSelected((current) => next.find((item) => item.id === current?.id) ?? next[0] ?? null); setDetailReadyFor(null); setDetailError(""); const first = next.find((item) => item.id === currentPlanId) ?? next[0]; if (first) { if (first.id !== currentPlanId) setContentText(""); void loadDetail(first.id); } }
    catch (reason) { setError(reason instanceof Error ? reason.message : "实现计划加载失败，请重试。"); }
    finally { setLoading(false); }
  }
  async function loadDetail(planId: string) {
    setDetailLoading(true); setDetailError(""); setDetailReadyFor(null);
    try { const detail = await api.implementationPlans.get(planId); setSelected(detail); setPlans((items) => items.map((item) => item.id === detail.id ? detail : item)); setDetailReadyFor(planId); const latest = detail.versions.at(-1); setContentText(latest ? pretty(latest.content) : ""); }
    catch (reason) { setDetailError(reason instanceof Error ? reason.message : "实现计划详情加载失败，请重试。"); }
    finally { setDetailLoading(false); }
  }
  async function loadCapabilities() {
    if (!projectId) return;
    try { const overview = await api.projects.overview(projectId, projectVersionId); setCapabilities(overview.capabilities ?? null); if (!overview.capabilities) setError("当前项目未返回可验证的成员能力，写操作已安全禁用。"); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "项目权限加载失败，写操作已安全禁用。"); }
  }
  async function loadSourceContext() {
    setSourceBlocker("");
    try {
      const prds = await api.prds.list(projectVersionId);
      if (prds.length !== 1) {
        throw new Error(prds.length === 0 ? "当前项目版本尚无 PRD，不能创建实现计划。" : "当前项目版本存在多个 PRD，无法唯一确定实现计划来源。");
      }
      const context = await api.prds.get(prds[0].id);
      const { prd, review } = context;
      if (prd.status !== "confirmed" || !prd.currentVersionId) throw new Error("当前 PRD 尚未确认，不能创建实现计划。");
      if (!review || review.status !== "passed") throw new Error("当前 PRD 没有已通过的设计评审，不能创建实现计划。");
      if (review.prdId !== prd.id || review.prdVersionId !== prd.currentVersionId) throw new Error("当前 PRD 与设计评审关系不一致，不能自动绑定来源。");
      setSourcePrdVersionId(prd.currentVersionId);
      setSourceDesignReviewId(review.id);
      setSourceSummary(`${prd.name} · 设计评审第 ${review.roundNo} 轮已通过`);
    } catch (reason) {
      setSourcePrdVersionId("");
      setSourceDesignReviewId("");
      setSourceSummary("");
      setSourceBlocker(reason instanceof Error ? reason.message : "无法确定实现计划来源。");
    }
  }
  // The async loader synchronizes this client workspace with the selected route context.
  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { void load(); void loadCapabilities(); void loadSourceContext(); }, [projectVersionId, projectId, api]);

  async function create(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try { const plan = await api.implementationPlans.create(projectVersionId, { name: name.trim(), sourcePrdVersionId: sourcePrdVersionId.trim(), sourceDesignReviewId: sourceDesignReviewId.trim() }); setName(""); setPlans([plan]); setSelected(plan); setContentText(""); setMessage("实现计划已创建。后续保存将形成不可变版本。"); await loadDetail(plan.id); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "创建失败，当前输入已保留。"); }
    finally { setBusy(false); }
  }
  async function saveVersion(event: FormEvent) {
    event.preventDefault(); if (!selected || detailReadyFor !== selected.id || !canWrite) return; setBusy(true); setError(""); setMessage("");
    try { const content = normalizePlanContent(JSON.parse(contentText)); const result = await api.implementationPlans.saveVersion(selected.id, { expectedVersion: selected.rowVersion, content, changeNote: changeNote.trim() }); const next = { ...selected, currentVersionId: result.version.id, rowVersion: result.planRowVersion, versions: [...selected.versions, result.version] }; setSelected(next); setPlans((items) => items.map((item) => item.id === next.id ? next : item)); setContentText(pretty(result.version.content)); setChangeNote(""); setMessage(`${result.version.versionNo} 已保存为不可变版本。`); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "保存失败，当前编辑内容已保留。 "); }
    finally { setBusy(false); }
  }
  async function setEffective() {
    if (!selected?.currentVersionId || detailReadyFor !== selected.id || !canSetEffective) return; setBusy(true); setError(""); setMessage("");
    try { const next = await api.implementationPlans.setEffective(selected.currentVersionId, selected.rowVersion); setSelected(next); setPlans((items) => items.map((item) => item.id === next.id ? next : item)); setMessage("当前版本已设为有效版本。确认页将按最新有效版本显示。"); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "设置有效版本失败，当前编辑内容已保留。"); }
    finally { setBusy(false); }
  }

  return <section className="space-y-token-lg">
    <div><p className="text-sm font-medium text-ai">实施计划 · 编写与生效</p><h1 className="mt-token-xs text-3xl font-semibold">实施计划工作台</h1><p className="mt-token-xs text-secondary">从已确认 PRD 与已通过设计评审自动绑定来源，保存不可变版本，并由项目负责人显式设置有效版本。</p></div>
    {scenario === "forbidden" ? <StatusPanel tone="error" title="当前身份只读">你可以查看计划与历史，但不能创建、保存或设置有效版本。</StatusPanel> : null}
    {scenario !== "forbidden" && capabilities ? <StatusPanel tone={capabilities.readOnly ? "warning" : "neutral"} title={`当前项目角色：${capabilities.role ?? "未知"}`}>{capabilities.readOnly ? "计划内容对当前成员只读。" : "计划创建、版本保存和设置有效版本能力已按项目成员角色启用。"}</StatusPanel> : null}
    {error ? <StatusPanel tone={error.includes("冲突") || error.includes("VERSION") ? "warning" : "error"} title={error.includes("冲突") ? "并发冲突" : "操作未完成"}>{error} 当前输入没有被清除。</StatusPanel> : null}
    {message ? <StatusPanel tone="success" title="已完成">{message}</StatusPanel> : null}
    {loading ? <div role="status" className="panel animate-pulse text-muted">正在加载实现计划…</div> : null}
    {!loading && !plans.length ? <form className="panel space-y-token-md" onSubmit={create}><h2 className="font-semibold">创建实现计划</h2><p className="text-sm text-secondary">系统会根据当前项目版本中的已确认 PRD 与已通过设计评审自动绑定来源。</p>{sourceBlocker ? <StatusPanel tone="warning" title="暂不能创建实现计划">{sourceBlocker}</StatusPanel> : <StatusPanel tone="success" title="已自动绑定业务来源">{sourceSummary || "正在确认来源…"}</StatusPanel>}<label className="block"><span className="field-label">计划名称</span><input className="input-field" value={name} onChange={(event) => setName(event.target.value)} required maxLength={200} placeholder="例如：首版实施计划" /></label><Button type="submit" loading={busy} disabled={!canWrite || !sourcePrdVersionId || !sourceDesignReviewId || !name.trim()}>创建计划</Button></form> : null}
    {!loading && plans.length ? <div className="grid gap-token-lg lg:grid-cols-[16rem_1fr]"><aside className="panel"><h2 className="font-semibold">计划</h2><ul className="mt-token-md space-y-token-xs">{plans.map((plan) => <li key={plan.id}><button type="button" className={`w-full rounded-token-md p-token-sm text-left ${selected?.id === plan.id ? "bg-primary-subtle" : "hover:bg-subtle"}`} onClick={() => { setSelected(plan); void loadDetail(plan.id); }}>{plan.name}<span className="mt-token-xs block text-xs text-muted">{{ confirmed: "已确认", needs_confirmation: "待确认", needs_reconfirmation: "需重新确认", not_ready: "未就绪" }[plan.confirmationState]} · 记录版本 {plan.rowVersion}</span></button></li>)}</ul></aside><div className="space-y-token-lg">{selected ? <><article className="panel"><div className="flex flex-wrap items-start justify-between gap-token-md"><div><h2 className="font-semibold">{selected.name}</h2><p className="mt-token-xs text-sm text-secondary">来源：当前已确认 PRD 与已通过设计评审</p></div><span className="rounded-full bg-subtle px-token-sm py-token-xs text-xs">{{ confirmed: "已确认", needs_confirmation: "待确认", needs_reconfirmation: "需重新确认", not_ready: "未就绪" }[selected.confirmationState]}</span></div><div className="mt-token-md flex flex-wrap gap-token-sm text-sm text-secondary"><span>当前版本：{selected.currentVersionId ? "已保存" : "未保存"}</span><span>有效版本：{selected.effectiveVersionId ? "已设置" : "未设置"}</span></div>{projectId && selected.effectiveVersionId ? <Link className="mt-token-md inline-flex" href={`/projects/${projectId}/versions/${projectVersionId}/confirmation?planId=${selected.id}`}><Button>进入实现确认</Button></Link> : null}</article>{detailLoading ? <div role="status" className="panel animate-pulse text-muted">正在读取完整计划详情与历史…</div> : null}{detailError ? <StatusPanel tone="error" title="计划详情加载失败">{detailError}<div className="mt-token-sm"><Button type="button" variant="secondary" onClick={() => void loadDetail(selected.id)}>重试读取详情</Button></div></StatusPanel> : null}<form className="panel space-y-token-md" onSubmit={saveVersion}><h2 className="font-semibold">保存新版本</h2><p className="text-sm text-secondary">历史版本只读；保存失败时保留本地内容，使用最新记录版本重试。</p><label className="block"><span className="field-label">计划内容（JSON）</span><textarea className="textarea-field min-h-80 font-mono text-xs" value={contentText} onChange={(event) => setContentText(event.target.value)} disabled={!canWrite || detailReadyFor !== selected.id} /></label><label className="block"><span className="field-label">变更说明</span><input className="input-field" value={changeNote} onChange={(event) => setChangeNote(event.target.value)} required maxLength={2000} disabled={!canWrite || detailReadyFor !== selected.id} placeholder="说明本次计划变更" /></label><div className="flex flex-wrap gap-token-sm"><Button type="submit" loading={busy} disabled={!canWrite || detailReadyFor !== selected.id}>保存不可变版本</Button><Button type="button" variant="secondary" onClick={setEffective} loading={busy} disabled={!canSetEffective || detailReadyFor !== selected.id || !selected.currentVersionId}>设置当前版本为有效</Button></div></form><article className="panel"><h2 className="font-semibold">版本历史</h2>{detailReadyFor !== selected.id ? <p className="mt-token-md text-sm text-muted">完整详情加载后显示历史，当前不会初始化可保存内容。</p> : selected.versions.length ? <ol className="mt-token-md space-y-token-sm">{selected.versions.map((version) => <li key={version.id} className="rounded-token-md bg-subtle p-token-sm"><div className="flex justify-between gap-token-md"><strong>{version.versionNo}</strong><span className="text-xs text-muted">{version.isEffective ? "有效" : "历史只读"}</span></div><p className="mt-token-xs text-sm text-secondary">{version.changeNote}</p></li>)}</ol> : <p className="mt-token-md text-sm text-muted">尚未保存版本。</p>}</article></> : null}</div></div> : null}
  </section>;
}
