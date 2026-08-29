"use client";

import { FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { StatusPanel } from "@/components/status-panel";
import { TestRecordWorkspace } from "@/features/test-records/test-record-workspace";
import { frontendApi } from "@/lib/api/frontend-api";
import type { ConfirmationRoundView, FrontendApi, ImplementationPlanView, ProjectCapabilities, ReadinessView, Scenario } from "@/lib/api/ports";

const emptyReadiness: ReadinessView = { schemaVersion: "implementation_confirmation.readiness.mvp3.v1", scopeStatus: "not_ready", implementationStatus: "not_ready", configurationStatus: "not_applicable", dataChangeStatus: "not_applicable", knownBlockers: [] };
const json = (value: unknown) => JSON.stringify(value, null, 2);
const roundStatus = { draft: "草稿", confirmed: "已确认", superseded: "已替代" } as const;

function readinessCompletionStatus(readinessText: string): { complete: boolean; issues: string[] } {
  try {
    const readiness = JSON.parse(readinessText) as Partial<ReadinessView>;
    const issues: string[] = [];
    if (readiness.schemaVersion !== "implementation_confirmation.readiness.mvp3.v1") issues.push("schemaVersion 无效");
    if (readiness.scopeStatus !== "ready") issues.push("scopeStatus 必须为 ready");
    if (readiness.implementationStatus !== "ready") issues.push("implementationStatus 必须为 ready");
    if (readiness.configurationStatus !== "ready" && readiness.configurationStatus !== "not_applicable") issues.push("configurationStatus 必须为 ready 或 not_applicable");
    if (readiness.dataChangeStatus !== "ready" && readiness.dataChangeStatus !== "not_applicable") issues.push("dataChangeStatus 必须为 ready 或 not_applicable");
    if (!Array.isArray(readiness.knownBlockers)) issues.push("knownBlockers 必须是数组");
    else if (readiness.knownBlockers.length) issues.push(`knownBlockers 仍有 ${readiness.knownBlockers.length} 项`);
    return { complete: issues.length === 0, issues };
  } catch {
    return { complete: false, issues: ["就绪状态 JSON 格式无效"] };
  }
}

export function ConfirmationWorkspace({ projectId, planId, projectVersionId, scenario = "ready", api = frontendApi }: { projectId?: string; planId?: string; projectVersionId?: string; scenario?: Scenario; api?: FrontendApi }) {
  const [resolvedPlanId, setResolvedPlanId] = useState(planId ?? "");
  const [rounds, setRounds] = useState<ConfirmationRoundView[]>([]);
  const [selected, setSelected] = useState<ConfirmationRoundView | null>(null);
  const [plan, setPlan] = useState<ImplementationPlanView | null>(null);
  const [planVersionId, setPlanVersionId] = useState("");
  const [summary, setSummary] = useState("");
  const [readinessText, setReadinessText] = useState(json(emptyReadiness));
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [capabilities, setCapabilities] = useState<ProjectCapabilities | null>(null);
  const [detailError, setDetailError] = useState("");
  const canCreateDraft = scenario !== "forbidden" && capabilities?.canConfirmationCreate === true;
  const canUpdateDraft = scenario !== "forbidden" && capabilities?.canConfirmationUpdate === true;
  const canConfirm = scenario !== "forbidden" && capabilities?.canConfirm === true;
  const readinessStatus = readinessCompletionStatus(readinessText);

  async function load() {
    setLoading(true); setError(""); setDetailError("");
    try {
      let activePlanId = planId;
      if (!activePlanId && projectVersionId) {
        const candidates = await api.implementationPlans.list(projectVersionId);
        if (candidates.length > 1) throw new Error("当前项目版本存在多个实现计划，无法唯一确定确认对象。请从具体实现计划进入。");
        activePlanId = candidates[0]?.id;
      }
      if (!activePlanId) { setResolvedPlanId(""); setPlan(null); setRounds([]); return; }
      setResolvedPlanId(activePlanId);
      const [detail, next] = await Promise.all([api.implementationPlans.get(activePlanId), api.confirmationRounds.list(activePlanId)]);
      setPlan(detail); setRounds(next);
      const nextSelected = next.find((round) => round.status === "draft") ?? next.at(-1) ?? null;
      setSelected((current) => next.find((round) => round.id === current?.id) ?? nextSelected);
      if (!nextSelected || nextSelected.status !== "draft") setPlanVersionId(detail.effectiveVersionId ?? "");
      if (projectId) {
        const overview = await api.projects.overview(projectId, projectVersionId);
        setCapabilities(overview.capabilities ?? null);
        if (!overview.capabilities) setDetailError("当前项目未返回可验证成员能力，写操作已安全禁用。");
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "确认轮次加载失败，请重试。"); }
    finally { setLoading(false); }
  }

  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { void load(); }, [planId, projectId, projectVersionId, api]);
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { if (selected) { setPlanVersionId(selected.planVersionId); setSummary(selected.implementationSummary); setReadinessText(json(selected.readiness)); } }, [selected]);

  function parseReadiness(): ReadinessView { return JSON.parse(readinessText) as ReadinessView; }
  async function create(event: FormEvent) {
    event.preventDefault(); if (!resolvedPlanId || !planVersionId || !canCreateDraft) return;
    setBusy(true); setError(""); setMessage("");
    try { const round = await api.confirmationRounds.create(resolvedPlanId, { planVersionId, implementationSummary: summary.trim(), readiness: parseReadiness() }); setRounds((old) => [...old, round]); setSelected(round); setMessage("确认草稿已创建；只有项目负责人可以最终确认。"); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "创建失败，当前输入已保留。"); }
    finally { setBusy(false); }
  }
  async function update(event: FormEvent) {
    event.preventDefault(); if (!selected || !canUpdateDraft || selected.status !== "draft") return;
    setBusy(true); setError(""); setMessage("");
    try { const round = await api.confirmationRounds.updateDraft(selected.id, { expectedVersion: selected.rowVersion, planVersionId: selected.planVersionId, implementationSummary: summary.trim(), readiness: parseReadiness() }); setRounds((old) => old.map((item) => item.id === round.id ? round : item)); setSelected(round); setMessage("草稿已更新；历史确认内容保持不变。"); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "更新失败，当前输入已保留。"); }
    finally { setBusy(false); }
  }
  async function confirm() {
    if (!selected || !canConfirm || selected.status !== "draft") return;
    setBusy(true); setError(""); setMessage("");
    try { const confirmed = await api.confirmationRounds.confirm(selected.id, selected.rowVersion); const authoritativeRounds = await api.confirmationRounds.list(resolvedPlanId); const authoritative = authoritativeRounds.find((item) => item.id === confirmed.id) ?? confirmed; setRounds(authoritativeRounds); setSelected(authoritative); setPlan((old) => old ? { ...old, confirmationState: "confirmed" } : old); setMessage("确认轮次已正式确认。"); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "确认失败，当前输入已保留。"); }
    finally { setBusy(false); }
  }

  const draft = rounds.find((round) => round.status === "draft");
  const showCreateDraft = !loading && Boolean(resolvedPlanId) && Boolean(plan) && !draft;
  const readOnly = !canUpdateDraft || selected?.status !== "draft";
  const persistedReadinessStatus = selected ? readinessCompletionStatus(json(selected.readiness)) : readinessStatus;
  const draftDirty = Boolean(selected) && (planVersionId !== selected?.planVersionId || summary !== selected?.implementationSummary || readinessText !== json(selected?.readiness));

  return <section className="space-y-token-lg">
    <div><p className="text-sm font-medium text-ai">实现确认 · 人工就绪判断</p><h1 className="mt-token-xs text-3xl font-semibold">实现确认工作台</h1><p className="mt-token-xs text-secondary">确认记录人工就绪事实；不等同于测试通过、版本可发布或生产就绪。</p></div>
    {scenario === "forbidden" || capabilities?.readOnly ? <StatusPanel tone="error" title="当前身份只读">你可以查看确认历史，但不能创建、修改或确认。</StatusPanel> : null}
    {detailError ? <StatusPanel tone="warning" title="权限事实不完整">{detailError}</StatusPanel> : null}
    {error ? <StatusPanel tone={error.includes("冲突") ? "warning" : "error"} title={error.includes("冲突") ? "并发冲突" : "操作未完成"}>{error} 当前输入没有被清除。</StatusPanel> : null}
    {message ? <StatusPanel tone="success" title="已完成">{message}</StatusPanel> : null}
    {!loading && !resolvedPlanId ? <StatusPanel tone="neutral" title="尚无实现计划">请先在当前版本创建实现计划。</StatusPanel> : null}
    {loading ? <div role="status" className="panel animate-pulse text-muted">正在加载确认历史…</div> : null}
    {showCreateDraft ? <form className="panel space-y-token-md" onSubmit={create}><h2 className="font-semibold">创建确认草稿</h2><p className="text-sm text-secondary">{rounds.length ? "已有确认历史；可为当前有效计划版本创建下一轮确认。" : "系统会自动绑定当前有效的实施计划版本。"}</p>{planVersionId ? <StatusPanel tone="success" title="已自动绑定实施计划">{plan?.name} · 当前有效版本</StatusPanel> : <StatusPanel tone="warning" title="暂不能创建确认">当前实施计划尚未设置有效版本。</StatusPanel>}<label className="block"><span className="field-label">实现范围摘要</span><textarea className="textarea-field min-h-28" value={summary} onChange={(event) => setSummary(event.target.value)} required minLength={20} maxLength={8000} placeholder="说明本轮确认覆盖的实现范围" /></label><label className="block"><span className="field-label">就绪状态（JSON）</span><textarea className="textarea-field min-h-64 font-mono text-xs" value={readinessText} onChange={(event) => setReadinessText(event.target.value)} /></label><Button type="submit" loading={busy} disabled={!canCreateDraft || !planVersionId}>创建确认草稿</Button></form> : null}
    {!loading && rounds.length ? <div className="grid gap-token-lg lg:grid-cols-[16rem_1fr]"><aside className="panel"><h2 className="font-semibold">确认历史</h2><ol className="mt-token-md space-y-token-xs">{rounds.map((round) => <li key={round.id}><button type="button" className={`w-full rounded-token-md p-token-sm text-left ${selected?.id === round.id ? "bg-primary-subtle" : "hover:bg-subtle"}`} onClick={() => setSelected(round)}><strong>第 {round.roundNo} 轮</strong><span className="mt-token-xs block text-xs text-muted">{roundStatus[round.status]}{round.isEffective ? " · 当前适用" : ""}</span></button></li>)}</ol></aside><div className="space-y-token-lg">{selected ? <><article className="panel"><div className="flex flex-wrap justify-between gap-token-md"><div><h2 className="font-semibold">第 {selected.roundNo} 轮确认</h2><p className="mt-token-xs text-sm text-secondary">{roundStatus[selected.status]} · 已绑定实施计划版本</p></div><span className="rounded-full bg-subtle px-token-sm py-token-xs text-xs">{selected.isEffective ? "当前适用" : "历史只读"}</span></div><p className="mt-token-md whitespace-pre-wrap text-sm">{selected.implementationSummary}</p><pre className="mt-token-md overflow-auto rounded-token-md bg-subtle p-token-sm text-xs">{json(selected.readiness)}</pre></article><form className="panel space-y-token-md" onSubmit={update}><h2 className="font-semibold">{readOnly ? "确认历史（只读）" : "编辑确认草稿"}</h2><p className="text-sm text-secondary">来源实施计划版本已由系统绑定，用户无需填写内部 ID。</p><label className="block"><span className="field-label">实现范围摘要</span><textarea className="textarea-field min-h-28" value={summary} onChange={(event) => setSummary(event.target.value)} disabled={readOnly} required minLength={20} maxLength={8000} /></label><label className="block"><span className="field-label">就绪状态（JSON）</span><textarea className="textarea-field min-h-64 font-mono text-xs" value={readinessText} onChange={(event) => setReadinessText(event.target.value)} disabled={readOnly} /></label>{!readOnly && draftDirty ? <StatusPanel tone="warning" title="存在未保存修改">请先点击“保存草稿”，再进行项目负责人最终确认。当前输入会保留。</StatusPanel> : null}{!readOnly && !persistedReadinessStatus.complete ? <StatusPanel tone="warning" title="就绪状态尚未完成">项目负责人最终确认前，请先完成：{persistedReadinessStatus.issues.join("；")}。保存草稿不会确认或清除当前输入。</StatusPanel> : null}<div className="flex flex-wrap gap-token-sm"><Button type="submit" loading={busy} disabled={readOnly}>保存草稿</Button><Button type="button" variant="secondary" loading={busy} onClick={confirm} disabled={!canConfirm || readOnly || !persistedReadinessStatus.complete || draftDirty}>项目负责人最终确认</Button></div></form></> : null}</div></div> : null}
    {selected ? <TestRecordWorkspace round={selected} capabilities={capabilities} projectId={projectId} projectVersionId={projectVersionId} api={api} /> : null}
  </section>;
}
