"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusPanel } from "@/components/status-panel";
import { frontendApi, frontendApiMode } from "@/lib/api/frontend-api";
import type { AiResultView, AiTaskView, ClarificationModeValue, FrontendApi, RequirementBaselineView, RequirementSummaryView, RequirementView } from "@/lib/api/ports";

const dimensions = [["goal", "目标"], ["users_and_roles", "用户与角色"], ["usage_scenarios", "使用场景"], ["functional_scope", "功能范围"], ["business_rules", "业务规则"], ["exception_cases", "异常情况"], ["permission_requirements", "权限要求"], ["acceptance_criteria", "验收标准"]] as const;
const blankBaseline = (): RequirementBaselineView => ({ assumptions: [], unresolvedItems: [], dimensions: Object.fromEntries(dimensions.map(([key]) => [key, { confirmedFacts: [], sourceRefs: [], deferredItems: [], notApplicableItems: [] }])) as unknown as RequirementBaselineView["dimensions"] });
const copyBaseline = (baseline: RequirementBaselineView): RequirementBaselineView => ({
  assumptions: [...baseline.assumptions],
  unresolvedItems: [...baseline.unresolvedItems],
  dimensions: Object.fromEntries(dimensions.map(([key]) => [key, {
    confirmedFacts: [...baseline.dimensions[key].confirmedFacts],
    sourceRefs: [...baseline.dimensions[key].sourceRefs],
    deferredItems: [...baseline.dimensions[key].deferredItems],
    notApplicableItems: [...baseline.dimensions[key].notApplicableItems],
  }])) as RequirementBaselineView["dimensions"],
});
const versionNumber = (versionNo: string) => Number(versionNo.replace(/\D/g, "")) || 1;
const terminalTaskStatuses = new Set(["ready", "partial_result", "quality_blocked", "cancelled", "failed", "expired", "stale_target"]);

async function settleTask(api: FrontendApi, initial: AiTaskView): Promise<AiTaskView> {
  let current = initial;
  for (let attempt = 0; attempt < 20 && !terminalTaskStatuses.has(current.status); attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 500));
    current = await api.ai.getTask(current.taskId);
  }
  return current;
}

export function RequirementWorkspace({ projectVersionId, requirementId, api = frontendApi }: { projectVersionId: string; requirementId?: string; api?: FrontendApi }) {
  const [requirement, setRequirement] = useState<RequirementView | null>(null);
  const [title, setTitle] = useState(""); const [rawInput, setRawInput] = useState("");
  const [mode, setMode] = useState<ClarificationModeValue>("auto"); const [task, setTask] = useState<AiTaskView | null>(null); const [result, setResult] = useState<AiResultView | null>(null);
  const [baseline, setBaseline] = useState<RequirementBaselineView>(blankBaseline()); const [candidateBaseline, setCandidateBaseline] = useState<RequirementBaselineView | null>(null); const [answers, setAnswers] = useState<Record<string, string>>({}); const [deepContinueConfirmed, setDeepContinueConfirmed] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [notice, setNotice] = useState("");
  const [recoveryState, setRecoveryState] = useState<"loading" | "ready" | "empty" | "multiple" | "failure">("loading");
  const [recoveryError, setRecoveryError] = useState("");
  const [requirementOptions, setRequirementOptions] = useState<RequirementSummaryView[]>([]);
  const currentVersion = requirement?.currentVersion;

  const applyRequirement = useCallback((value: RequirementView) => {
    setRequirement(value);
    setTitle(value.requirement.title);
    setRawInput(value.currentVersion?.content.rawInput ?? "");
    if (value.currentVersion) {
      setMode(value.currentVersion.content.clarification.mode);
      setBaseline(value.currentVersion.content.baseline);
    }
    setRecoveryState("ready");
  }, []);

  const loadRequirement = useCallback(async (selectedRequirementId?: string) => {
    setBusy(true); setError(""); setRecoveryError(""); setRequirement(null); setRequirementOptions([]); setRecoveryState("loading");
    try {
      let resolvedRequirementId = requirementId ?? selectedRequirementId;
      if (!resolvedRequirementId) {
        const requirements = await api.requirements.list(projectVersionId);
        if (requirements.length === 0) { setRecoveryState("empty"); return; }
        if (requirements.length > 1) { setRequirementOptions(requirements); setRecoveryState("multiple"); return; }
        resolvedRequirementId = requirements[0].id;
      }
      applyRequirement(await api.requirements.get(resolvedRequirementId));
    } catch (reason) {
      setRecoveryError(reason instanceof Error ? reason.message : "需求读取失败。");
      setRecoveryState("failure");
    } finally { setBusy(false); }
  }, [api, applyRequirement, projectVersionId, requirementId]);

  useEffect(() => { void loadRequirement(); }, [loadRequirement]);

  async function createRequirement() { setBusy(true); setError(""); try { const value = await api.requirements.create(projectVersionId, { title, rawInput }); applyRequirement(value); setNotice("需求草稿已保存，可以开始预检。"); } catch (reason) { setError(reason instanceof Error ? reason.message : "需求保存失败。"); } finally { setBusy(false); } }
  async function startClarification() {
    if (!currentVersion) return;
    setBusy(true); setError(""); setResult(null);
    try {
      const reason = mode === "skip" ? "用户明确选择跳过澄清并进入人工审核" : mode === "deep" ? "需要覆盖更多边界" : null;
      const version = await api.requirements.setClarificationMode(currentVersion.id, { expectedVersion: versionNumber(currentVersion.versionNo), mode, reason });
      setRequirement((old) => old ? { ...old, currentVersion: version } : old);
      const createdTask = await api.ai.createTask({ requirementId: version.requirementId, versionId: version.id, sourceRefIds: [version.content.rawInputRef.sourceId] });
      const settledTask = await settleTask(api, createdTask);
      setTask(settledTask);
      const durableResult = settledTask.resultRefs.find((reference) => reference.status === "ready");
      if (settledTask.status === "ready" && durableResult) {
        const nextResult = await api.ai.getResult(durableResult.resultId);
        setResult(nextResult);
        if (nextResult.resultKind === "baseline" && nextResult.content?.baseline) {
          const nextCandidate = copyBaseline(nextResult.content.baseline);
          setCandidateBaseline(nextCandidate);
          setBaseline(nextCandidate);
        }
        setNotice(nextResult.resultKind === "assessment" ? "AI 预检已就绪，请明确选择下一步模式。" : nextResult.resultKind === "questions" ? "澄清问题已就绪，请回答后继续。" : "Baseline 候选已就绪，请核对质量与来源后采用。");
      } else {
        setNotice("AI 暂不可用，已保留原始输入与人工 Baseline 路径。");
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "澄清任务创建失败。"); } finally { setBusy(false); }
  }
  async function submitAnswers(finishNow: boolean) { if (!currentVersion) return; setBusy(true); setError(""); try { const next = await api.requirements.submitClarificationAnswers(currentVersion.id, { expectedVersion: Number(currentVersion.versionNo.replace(/\D/g, "")) || 1, roundNo: result?.roundNo ?? 1, answers: (result?.content?.questions ?? []).map((question) => ({ questionId: question.questionId, answer: answers[question.questionId] ?? "" })), continueDeepConfirmed: mode !== "deep" || (result?.roundNo ?? 1) < 4 || deepContinueConfirmed, finishNow }); setRequirement((old) => old ? { ...old, currentVersion: next.version } : old); if (finishNow) setBaseline(next.version.content.baseline); setNotice("回答已保存；后续 AI Task 可单独创建。" ); } catch (reason) { setError(reason instanceof Error ? reason.message : "回答保存失败。"); } finally { setBusy(false); } }
  async function confirmBaseline() { if (!currentVersion) return; setBusy(true); setError(""); try { const revised = await api.requirements.revise(currentVersion.id, { expectedVersion: Number(currentVersion.versionNo.replace(/\D/g, "")) || 1, content: { ...currentVersion.content, baseline } }); const confirmed = await api.requirements.confirm(revised.id, { expectedVersion: Number(revised.versionNo.replace(/\D/g, "")) || 1 }); setRequirement((old) => old ? { ...old, currentVersion: confirmed.version, effectiveVersion: confirmed.version } : old); setNotice(`Baseline 已确认（${confirmed.gateResult}）。`); } catch (reason) { setError(reason instanceof Error ? reason.message : "Baseline 确认失败。"); } finally { setBusy(false); } }
  async function formalizeBaseline() {
    if (!requirement || !currentVersion || !result || result.resultKind !== "baseline" || result.status !== "ready" || !result.content?.baseline) return;
    const immutableCandidate = result.content.baseline;
    const editedCandidate = candidateBaseline ?? immutableCandidate;
    const modifiedAdopt = immutableCandidate.unresolvedItems.length > 0;
    if (editedCandidate.unresolvedItems.length > 0) return;
    setBusy(true); setError("");
    try {
      const formalized = await api.ai.formalizeBaseline(result.id, {
        requirementId: currentVersion.requirementId,
        expectedVersion: versionNumber(currentVersion.versionNo),
        targetSnapshotHash: result.targetSnapshotHash,
        ...(modifiedAdopt ? { adoption: "modified_adopt" as const, modificationIntensity: "minor" as const, modifiedContent: { baseline: editedCandidate } } : {}),
      });
      const refreshed = await api.requirements.get(requirement.requirement.id);
      setRequirement(refreshed);
      if (refreshed.currentVersion) setBaseline(refreshed.currentVersion.content.baseline);
      setNotice(`Baseline 已采用，形成待确认版本 ${formalized.versionNo}。`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Baseline 采用失败。"); } finally { setBusy(false); }
  }
  async function confirmAdoptedBaseline() {
    if (!requirement || !currentVersion || currentVersion.isEffective || !currentVersion.createdFromAiResultId) return;
    setBusy(true); setError("");
    try {
      await api.requirements.confirm(currentVersion.id, { expectedVersion: versionNumber(currentVersion.versionNo) });
      const refreshed = await api.requirements.get(requirement.requirement.id);
      setRequirement(refreshed);
      if (refreshed.currentVersion) setBaseline(refreshed.currentVersion.content.baseline);
      setNotice("Baseline 已确认并设为当前 Baseline。");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Baseline 确认失败。"); } finally { setBusy(false); }
  }

  const questions = result?.content?.questions ?? [];
  const assessment = result?.resultKind === "assessment" ? result.content?.assessment : null;
  const baselineCandidate = result?.resultKind === "baseline" ? result.content?.baseline : null;
  const editableCandidateBaseline = candidateBaseline ?? baselineCandidate;
  const candidateHasUnresolvedItems = Boolean(editableCandidateBaseline?.unresolvedItems.length);
  const isModifiedCandidate = Boolean(baselineCandidate?.unresolvedItems.length && editableCandidateBaseline && editableCandidateBaseline.unresolvedItems.length === 0);
  const baselineAdopted = Boolean(currentVersion?.createdFromAiResultId);
  const adoptedDraft = Boolean(baselineAdopted && currentVersion && !currentVersion.isEffective);
  const canFormalize = Boolean(baselineCandidate && !baselineAdopted && !candidateHasUnresolvedItems && result?.status === "ready" && !result.quality.majorError && result.quality.formatStatus === "passed" && result.quality.traceabilityStatus === "passed" && result.quality.safetyStatus === "passed");
  const aiFailed = Boolean(task && ["blocked", "partial_result", "quality_blocked", "cancelled", "failed", "expired", "stale_target"].includes(task.status)) || ["failed", "partial_result", "quality_blocked", "stale_target", "expired"].includes(result?.status ?? "");
  return <section aria-labelledby="requirement-title" className="space-y-token-lg">
    <div className="flex flex-wrap items-start justify-between gap-token-md"><div><p className="text-sm font-medium text-ai">Requirement · 首批纵向切片</p><h1 id="requirement-title" className="mt-token-xs text-3xl font-semibold">需求澄清与 Baseline</h1><p className="mt-token-xs text-secondary">当前 API 模式：<strong>{frontendApiMode === "real" ? "REAL" : "FORMAL_MOCK"}</strong></p></div><span className="rounded-token-md bg-subtle px-token-sm py-token-xs text-xs text-muted">模式：{mode}</span></div>
    {error ? <StatusPanel tone="error" title="操作未完成">{error}</StatusPanel> : null}{notice ? <StatusPanel tone="success" title="状态更新">{notice}</StatusPanel> : null}
    {recoveryState === "loading" ? <div role="status" className="panel animate-pulse text-muted">正在读取当前查看版本的 Requirement…</div> : null}
    {recoveryState === "failure" ? <StatusPanel tone="error" title="Requirement 读取失败" action={<Button variant="secondary" onClick={() => void loadRequirement()}>重新读取当前查看版本</Button>}>{recoveryError}</StatusPanel> : null}
    {recoveryState === "multiple" ? <article className="panel space-y-token-md"><h2 className="font-semibold">选择 Requirement</h2><p className="text-sm text-secondary">当前查看版本包含多个 Requirement，请选择要继续的对象。</p><div className="space-y-token-sm">{requirementOptions.map((candidate) => <Button key={candidate.id} variant="secondary" className="w-full justify-start" onClick={() => void loadRequirement(candidate.id)}>{candidate.title}</Button>)}</div></article> : null}
    {recoveryState === "empty" ? <article className="panel space-y-token-md"><h2 className="font-semibold">1. 手工输入 Requirement</h2><label className="field-label" htmlFor="requirement-title-input">标题</label><Input id="requirement-title-input" value={title} onChange={(event) => setTitle(event.target.value)} /><label className="field-label" htmlFor="requirement-raw-input">原始需求</label><textarea id="requirement-raw-input" className="textarea-field min-h-36" value={rawInput} onChange={(event) => setRawInput(event.target.value)} /><Button onClick={createRequirement} loading={busy} disabled={!title.trim() || !rawInput.trim()}>保存需求草稿</Button></article> : null}
    {requirement ? <>
      <article className="panel"><div className="flex flex-wrap items-center justify-between gap-token-md"><div><h2 className="font-semibold">{requirement.requirement.title}</h2><p className="mt-token-xs text-sm text-secondary">版本 {currentVersion?.versionNo ?? "—"} · {currentVersion?.confirmationStatus ?? "draft"}{currentVersion?.isEffective ? " · 当前 Baseline" : ""}</p></div><div className="flex flex-wrap gap-token-sm"><select aria-label="澄清模式" className="select-field w-auto" value={mode} onChange={(event) => setMode(event.target.value as ClarificationModeValue)}><option value="auto">auto · 先预检</option><option value="standard">standard · 最多 3 轮</option><option value="deep">deep · 最多 5 轮</option><option value="skip">skip · 直接形成候选</option></select><Button onClick={startClarification} loading={busy}>{assessment ? "按所选模式继续" : "开始预检 / 澄清"}</Button></div></div><div className="mt-token-md rounded-token-md bg-subtle p-token-sm"><p className="text-xs font-medium text-muted">原始输入（保留）</p><p className="mt-token-xs whitespace-pre-wrap text-sm">{currentVersion?.content.rawInput}</p></div></article>
      <article className="panel"><div className="flex flex-wrap items-center justify-between gap-token-sm"><h2 className="font-semibold">2. 八类预检</h2>{assessment ? <span className="text-xs text-muted">复杂度 {assessment.complexityBand} · 建议 {assessment.recommendedMode}</span> : null}</div>{assessment?.reasons.length ? <p className="mt-token-sm text-sm text-secondary">{assessment.reasons.join("；")}</p> : null}<div className="mt-token-md grid gap-token-sm sm:grid-cols-2 lg:grid-cols-4">{dimensions.map(([key, label]) => { const item = assessment?.dimensions[key]; return <div key={key} className="rounded-token-md border border-default p-token-sm"><p className="text-sm font-medium">{label}</p><p className="mt-token-xs text-xs text-muted">{item?.status ?? "待检查"}</p>{item?.missingItems.length ? <p className="mt-token-xs text-xs text-warning">缺少：{item.missingItems.join("、")}</p> : null}{item?.reasons.length ? <p className="mt-token-xs text-xs text-secondary">{item.reasons.join("；")}</p> : null}{item?.sourceRefs.length ? <p className="mt-token-xs text-xs text-muted">来源 {item.sourceRefs.length} 条</p> : null}</div>; })}</div></article>
      {aiFailed ? <StatusPanel tone="warning" title="AI 暂不可用">候选结果未正式化。你仍可以直接编辑人工 Baseline 并确认。</StatusPanel> : null}
      {questions.length ? <article className="panel space-y-token-md"><h2 className="font-semibold">3. 第 {result?.roundNo ?? 1} 轮问题（{questions.length}/3）</h2>{questions.map((question) => <div key={question.questionId}><label className="field-label" htmlFor={question.questionId}>{question.questionText}</label><textarea id={question.questionId} className="textarea-field min-h-24" value={answers[question.questionId] ?? ""} onChange={(event) => setAnswers((old) => ({ ...old, [question.questionId]: event.target.value }))} /></div>)}{mode === "deep" && (result?.roundNo ?? 1) >= 4 ? <label className="flex items-center gap-token-sm text-sm"><input type="checkbox" checked={deepContinueConfirmed} onChange={(event) => setDeepContinueConfirmed(event.target.checked)} />我确认继续深度澄清第 {result?.roundNo} 轮</label> : null}<div className="flex flex-wrap gap-token-sm"><Button variant="secondary" onClick={() => submitAnswers(false)} loading={busy} disabled={mode === "deep" && (result?.roundNo ?? 1) >= 4 && !deepContinueConfirmed}>保存回答</Button><Button onClick={() => submitAnswers(true)} loading={busy} disabled={mode === "deep" && (result?.roundNo ?? 1) >= 4 && !deepContinueConfirmed}>结束并审核 Baseline</Button></div></article> : null}
      {baselineCandidate && !baselineAdopted ? <article className="panel space-y-token-md"><div className="flex flex-wrap items-center justify-between gap-token-sm"><h2 className="font-semibold">4. Baseline 候选审核</h2><span className="text-xs text-muted">质量 {result?.quality.requiredItemsMet}/{result?.quality.requiredItemsTotal}</span></div><p className="text-sm text-secondary">Provider truth: {result?.capabilitySummary.truthLabel ?? "unavailable"}</p><p className="text-sm text-secondary">格式 {result?.quality.formatStatus} · 可追溯性 {result?.quality.traceabilityStatus} · 安全 {result?.quality.safetyStatus}</p><div className="grid gap-token-sm sm:grid-cols-2">{dimensions.map(([key, label]) => <div key={key} className="rounded-token-md border border-default p-token-sm"><p className="text-sm font-medium">{label}</p><p className="mt-token-xs text-sm">{baselineCandidate.dimensions[key].confirmedFacts.join("；") || "无已确认事实"}</p><p className="mt-token-xs text-xs text-muted">来源 {baselineCandidate.dimensions[key].sourceRefs.length} 条</p></div>)}</div>{editableCandidateBaseline?.unresolvedItems.length ? <StatusPanel tone="warning" title="未决项阻断直接采用"><ul className="space-y-token-sm">{editableCandidateBaseline.unresolvedItems.map((item, index) => <li key={`${item}-${index}`} className="flex flex-wrap items-center justify-between gap-token-sm"><span>{item}</span><Button variant="secondary" onClick={() => setCandidateBaseline((current) => { const candidate = current ?? baselineCandidate; return candidate ? { ...candidate, unresolvedItems: candidate.unresolvedItems.filter((_, currentIndex) => currentIndex !== index) } : current; })}>标记已处理：{item}</Button></li>)}</ul></StatusPanel> : isModifiedCandidate ? <StatusPanel tone="success" title="未决项已显式处理">仅候选副本中的未决项已移除；可修改后采用。</StatusPanel> : null}{result?.quality.blockerCodes.length ? <StatusPanel tone="warning" title="候选暂不可采用">{result.quality.blockerCodes.join("、")}</StatusPanel> : null}<Button onClick={formalizeBaseline} loading={busy} disabled={!canFormalize}>{isModifiedCandidate ? "修改后采用并形成新版本" : "采用 Baseline 并形成新版本"}</Button></article> : null}
      {adoptedDraft ? <article className="panel space-y-token-md"><h2 className="font-semibold">4. Baseline 已采用，待确认</h2><p className="text-sm text-secondary">版本 {currentVersion?.versionNo} · draft · 尚未设为当前 Baseline</p><Button onClick={confirmAdoptedBaseline} loading={busy}>确认并设为当前 Baseline</Button></article> : null}
      {baselineAdopted && currentVersion?.isEffective ? <StatusPanel tone="success" title="Baseline 已确认">版本 {currentVersion.versionNo} 已设为当前 Baseline。</StatusPanel> : null}
      <article className="panel space-y-token-md"><h2 className="font-semibold">{baselineCandidate ? "5" : "4"}. 人工 Baseline 编辑与确认</h2><p className="text-sm text-secondary">AI 失败、质量阻断或过期时仍可人工继续；人工确认与 AI 候选采用是两条明确路径。</p>{dimensions.map(([key, label]) => <div key={key}><label className="field-label" htmlFor={`baseline-${key}`}>{label}</label><textarea id={`baseline-${key}`} className="textarea-field min-h-20" value={baseline.dimensions[key].confirmedFacts.join("\n")} onChange={(event) => setBaseline((old) => ({ ...old, dimensions: { ...old.dimensions, [key]: { ...old.dimensions[key], confirmedFacts: event.target.value.split("\n").filter(Boolean) } } }))} /></div>)}<Button onClick={confirmBaseline} loading={busy} disabled={!currentVersion}>人工确认 Baseline</Button></article>
    </> : null}
  </section>;
}
