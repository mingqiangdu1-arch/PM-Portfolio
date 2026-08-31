"use client";
/* eslint-disable react-hooks/set-state-in-effect */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
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
const terminalTaskStatuses = new Set(["ready", "partial_result", "quality_blocked", "cancelled", "failed", "expired", "stale_target"]);
type ClarificationTaskState = Pick<AiTaskView, "taskPublicId" | "taskType" | "status" | "targetSnapshotHash" | "resultRefs">;

function clarificationRecoveryTarget(value: RequirementView): { mode: "standard" | "deep"; roundNo: number } | null {
  const clarification = value.currentVersion?.content.clarification;
  if (!clarification || clarification.finishReason !== null || !["standard", "deep"].includes(clarification.mode)) return null;
  const mode = clarification.mode as "standard" | "deep";
  const completedRound = clarification.rounds.reduce((highest, round) => Math.max(highest, round.roundNo), 0);
  const roundNo = Math.min(completedRound + 1, mode === "standard" ? 3 : 5);
  if (mode === "deep" && roundNo >= 4 && !clarification.continueDeepConfirmed) return null;
  return { mode, roundNo };
}

function isExactRecoveryResult(value: AiResultView, requirement: RequirementView, mode: "standard" | "deep", roundNo: number): boolean {
  return value.taskType === "requirement.clarify"
    && value.status === "ready"
    && value.resultKind === "questions"
    && value.mode === mode
    && value.roundNo === roundNo
    && value.targetSnapshotHash === requirement.currentVersion?.contentHash
    && Boolean(value.content?.questions.length);
}

function advanceRequirement(value: RequirementView, version: NonNullable<RequirementView["currentVersion"]>, aggregateVersion: number): RequirementView {
  return {
    ...value,
    requirement: { ...value.requirement, currentVersionId: version.id, version: aggregateVersion },
    currentVersion: version,
  };
}

async function settleTask(api: FrontendApi, initial: AiTaskView): Promise<AiTaskView> {
  let current = initial;
  for (let attempt = 0; attempt < 20 && !terminalTaskStatuses.has(current.status); attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 500));
    current = await api.ai.getTask(current.taskId);
  }
  return current;
}

export function RequirementWorkspace({ projectVersionId, projectId, requirementId, api = frontendApi }: { projectVersionId: string; projectId?: string; requirementId?: string; api?: FrontendApi }) {
  const [requirement, setRequirement] = useState<RequirementView | null>(null);
  const [title, setTitle] = useState(""); const [rawInput, setRawInput] = useState("");
  const [mode, setMode] = useState<ClarificationModeValue>("auto"); const [task, setTask] = useState<ClarificationTaskState | null>(null); const [result, setResult] = useState<AiResultView | null>(null);
  const [baseline, setBaseline] = useState<RequirementBaselineView>(blankBaseline()); const [candidateBaseline, setCandidateBaseline] = useState<RequirementBaselineView | null>(null); const [answers, setAnswers] = useState<Record<string, string>>({}); const [deepContinueConfirmed, setDeepContinueConfirmed] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [notice, setNotice] = useState("");
  const [recoveryState, setRecoveryState] = useState<"loading" | "ready" | "empty" | "multiple" | "failure">("loading");
  const [recoveryError, setRecoveryError] = useState("");
  const [resultRecoveryState, setResultRecoveryState] = useState<"idle" | "loading" | "ready" | "not-found" | "error">("idle");
  const [resultRecoveryError, setResultRecoveryError] = useState("");
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
    setBusy(true); setError(""); setNotice(""); setRecoveryError(""); setResultRecoveryError(""); setRequirement(null); setRequirementOptions([]); setTask(null); setResult(null); setAnswers({}); setCandidateBaseline(null); setResultRecoveryState("idle"); setRecoveryState("loading");
    try {
      let resolvedRequirementId = requirementId ?? selectedRequirementId;
      if (!resolvedRequirementId) {
        const requirements = await api.requirements.list(projectVersionId);
        if (requirements.length === 0) { setRecoveryState("empty"); return; }
        if (requirements.length > 1) { setRequirementOptions(requirements); setRecoveryState("multiple"); return; }
        resolvedRequirementId = requirements[0].id;
      }
      const loaded = await api.requirements.get(resolvedRequirementId);
      applyRequirement(loaded);
      const target = clarificationRecoveryTarget(loaded);
      if (!target || !loaded.currentVersion) {
        setResultRecoveryState("not-found");
        return;
      }
      setResultRecoveryState("loading");
      try {
        const recovered = await api.ai.findClarificationResult(loaded.currentVersion.id, target.mode, target.roundNo);
        if (!recovered) {
          setResultRecoveryState("not-found");
          return;
        }
        if (!isExactRecoveryResult(recovered, loaded, target.mode, target.roundNo)) {
          throw new Error("已读取的 AI 澄清结果与当前需求版本不一致。");
        }
        setTask({
          taskPublicId: recovered.taskPublicId,
          taskType: recovered.taskType,
          status: "ready",
          targetSnapshotHash: recovered.targetSnapshotHash,
          resultRefs: [{ resultId: recovered.id, status: recovered.status, targetSnapshotHash: recovered.targetSnapshotHash }],
        });
        setResult(recovered);
        setMode(recovered.mode);
        setAnswers({});
        setResultRecoveryState("ready");
        setNotice("已恢复当前版本的 AI 澄清问题，请重新填写回答。");
      } catch (reason) {
        setResultRecoveryError(reason instanceof Error ? reason.message : "AI 澄清结果读取失败。");
        setResultRecoveryState("error");
      }
    } catch (reason) {
      setRecoveryError(reason instanceof Error ? reason.message : "需求读取失败。");
      setRecoveryState("failure");
    } finally { setBusy(false); }
  }, [api, applyRequirement, projectVersionId, requirementId]);

  useEffect(() => { void loadRequirement(); }, [loadRequirement]);

  async function createRequirement() { setBusy(true); setError(""); try { const value = await api.requirements.create(projectVersionId, { title, rawInput }); applyRequirement(value); setNotice("需求草稿已保存，可以开始预检。"); } catch (reason) { setError(reason instanceof Error ? reason.message : "需求保存失败。"); } finally { setBusy(false); } }
  async function startClarification() {
    if (!requirement || !currentVersion) return;
    setBusy(true); setError(""); setResult(null);
    try {
      const reason = mode === "skip" ? "用户明确选择跳过澄清并进入人工审核" : mode === "deep" ? "需要覆盖更多边界" : null;
      const expectedVersion = requirement.requirement.version;
      const version = await api.requirements.setClarificationMode(currentVersion.id, { expectedVersion, mode, reason });
      setRequirement((old) => old ? advanceRequirement(old, version, expectedVersion + 1) : old);
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
        setNotice(nextResult.resultKind === "assessment" ? "AI 预检已就绪，请明确选择下一步模式。" : nextResult.resultKind === "questions" ? "澄清问题已就绪，请回答后继续。" : "需求基线候选已就绪，请核对质量与来源后采用。");
      } else {
        setNotice("AI 暂不可用，已保留原始输入与人工需求基线路径。");
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "澄清任务创建失败。"); } finally { setBusy(false); }
  }
  async function submitAnswers(finishNow: boolean) { if (!requirement || !currentVersion) return; setBusy(true); setError(""); try { const expectedVersion = requirement.requirement.version; const next = await api.requirements.submitClarificationAnswers(currentVersion.id, { expectedVersion, roundNo: result?.roundNo ?? 1, answers: (result?.content?.questions ?? []).map((question) => ({ questionId: question.questionId, answer: answers[question.questionId] ?? "" })), continueDeepConfirmed: mode !== "deep" || (result?.roundNo ?? 1) < 4 || deepContinueConfirmed, finishNow }); setRequirement((old) => old ? advanceRequirement(old, next.version, expectedVersion + 1) : old); if (finishNow) setBaseline(next.version.content.baseline); setNotice("回答已保存；后续 AI Task 可单独创建。" ); } catch (reason) { setError(reason instanceof Error ? reason.message : "回答保存失败。"); } finally { setBusy(false); } }
  async function confirmBaseline() { if (!requirement || !currentVersion) return; setBusy(true); setError(""); try { const expectedVersion = requirement.requirement.version; const revised = await api.requirements.revise(currentVersion.id, { expectedVersion, content: { ...currentVersion.content, baseline } }); const revisedAggregateVersion = expectedVersion + 1; setRequirement((old) => old ? advanceRequirement(old, revised, revisedAggregateVersion) : old); const confirmed = await api.requirements.confirm(revised.id, { expectedVersion: revisedAggregateVersion }); setRequirement((old) => old ? { ...advanceRequirement(old, confirmed.version, revisedAggregateVersion + 1), requirement: { ...old.requirement, status: "effective", currentVersionId: confirmed.version.id, effectiveVersionId: confirmed.version.id, version: revisedAggregateVersion + 1 }, effectiveVersion: confirmed.version } : old); setNotice(`需求基线已确认（${confirmed.gateResult}）。`); } catch (reason) { setError(reason instanceof Error ? reason.message : "需求基线确认失败。"); } finally { setBusy(false); } }
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
        expectedVersion: requirement.requirement.version,
        targetSnapshotHash: result.targetSnapshotHash,
        ...(modifiedAdopt ? { adoption: "modified_adopt" as const, modificationIntensity: "minor" as const, modifiedContent: { baseline: editedCandidate } } : {}),
      });
      const refreshed = await api.requirements.get(requirement.requirement.id);
      setRequirement(refreshed);
      if (refreshed.currentVersion) setBaseline(refreshed.currentVersion.content.baseline);
      setNotice(`需求基线已采用，形成待确认版本 ${formalized.versionNo}。`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "需求基线采用失败。"); } finally { setBusy(false); }
  }
  async function confirmAdoptedBaseline() {
    if (!requirement || !currentVersion || currentVersion.isEffective || !currentVersion.createdFromAiResultId) return;
    setBusy(true); setError("");
    try {
      await api.requirements.confirm(currentVersion.id, { expectedVersion: requirement.requirement.version });
      const refreshed = await api.requirements.get(requirement.requirement.id);
      setRequirement(refreshed);
      if (refreshed.currentVersion) setBaseline(refreshed.currentVersion.content.baseline);
      setNotice("需求基线已确认并设为当前基线。");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "需求基线确认失败。"); } finally { setBusy(false); }
  }

  const questions = result?.content?.questions ?? [];
  const assessment = result?.resultKind === "assessment" ? result.content?.assessment : null;
  const baselineCandidate = result?.resultKind === "baseline" ? result.content?.baseline : null;
  const editableCandidateBaseline = candidateBaseline ?? baselineCandidate;
  const candidateHasUnresolvedItems = Boolean(editableCandidateBaseline?.unresolvedItems.length);
  const isModifiedCandidate = Boolean(baselineCandidate?.unresolvedItems.length && editableCandidateBaseline && editableCandidateBaseline.unresolvedItems.length === 0);
  const isAiCandidateAdopted = Boolean(currentVersion?.createdFromAiResultId);
  const isEffectiveVersion = Boolean(requirement?.effectiveVersion && requirement.requirement.effectiveVersionId === requirement.effectiveVersion.id && requirement.effectiveVersion.confirmationStatus === "confirmed" && requirement.effectiveVersion.isEffective);
  const isRequirementComplete = Boolean(requirement?.requirement.status === "effective" && isEffectiveVersion);
  const isAiSourcedEffectiveBaseline = Boolean(requirement?.effectiveVersion?.createdFromAiResultId);
  const adoptedDraft = Boolean(isAiCandidateAdopted && currentVersion && !currentVersion.isEffective);
  const canFormalize = Boolean(baselineCandidate && !isAiCandidateAdopted && !candidateHasUnresolvedItems && result?.status === "ready" && !result.quality.majorError && result.quality.formatStatus === "passed" && result.quality.traceabilityStatus === "passed" && result.quality.safetyStatus === "passed");
  const aiFailed = Boolean(task && ["blocked", "partial_result", "quality_blocked", "cancelled", "failed", "expired", "stale_target"].includes(task.status)) || ["failed", "partial_result", "quality_blocked", "stale_target", "expired"].includes(result?.status ?? "");
  return <section aria-labelledby="requirement-title" className="space-y-token-lg">
    <div className="flex flex-wrap items-start justify-between gap-token-md"><div><p className="text-sm font-medium text-ai">需求 · 澄清与确认</p><h1 id="requirement-title" className="mt-token-xs text-3xl font-semibold">需求澄清与需求基线</h1><p className="mt-token-xs text-secondary">当前运行模式：<strong>{frontendApiMode === "real" ? "真实服务" : "演示数据"}</strong></p></div><span className="rounded-token-md bg-subtle px-token-sm py-token-xs text-xs text-muted">澄清方式：{mode}</span></div>
    {error ? <StatusPanel tone="error" title="操作未完成">{error}</StatusPanel> : null}{notice ? <StatusPanel tone="success" title="状态更新">{notice}</StatusPanel> : null}
    {recoveryState === "loading" ? <div role="status" className="panel animate-pulse text-muted">正在读取当前查看版本的需求…</div> : null}
    {recoveryState === "failure" ? <StatusPanel tone="error" title="需求读取失败" action={<Button variant="secondary" onClick={() => void loadRequirement()}>重新读取当前查看版本</Button>}>{recoveryError}</StatusPanel> : null}
    {resultRecoveryState === "error" ? <StatusPanel tone="error" title="AI 澄清结果读取失败" action={<Button variant="secondary" onClick={() => void loadRequirement(requirement?.requirement.id)}>重新读取已有结果</Button>}>{resultRecoveryError}</StatusPanel> : null}
    {recoveryState === "multiple" ? <article className="panel space-y-token-md"><h2 className="font-semibold">选择需求</h2><p className="text-sm text-secondary">当前查看版本包含多个需求，请选择要继续的对象。</p><div className="space-y-token-sm">{requirementOptions.map((candidate) => <Button key={candidate.id} variant="secondary" className="w-full justify-start" onClick={() => void loadRequirement(candidate.id)}>{candidate.title}</Button>)}</div></article> : null}
    {recoveryState === "empty" ? <article className="panel space-y-token-md"><h2 className="font-semibold">1. 手工输入需求</h2><label className="field-label" htmlFor="requirement-title-input">标题</label><Input id="requirement-title-input" value={title} onChange={(event) => setTitle(event.target.value)} /><label className="field-label" htmlFor="requirement-raw-input">原始需求</label><textarea id="requirement-raw-input" className="textarea-field min-h-36" value={rawInput} onChange={(event) => setRawInput(event.target.value)} /><Button onClick={createRequirement} loading={busy} disabled={!title.trim() || !rawInput.trim()}>保存需求草稿</Button></article> : null}
    {requirement ? <>
      <article className="panel"><div className="flex flex-wrap items-center justify-between gap-token-md"><div><h2 className="font-semibold">{requirement.requirement.title}</h2><p className="mt-token-xs text-sm text-secondary">版本 {currentVersion?.versionNo ?? "—"} · {{ draft: "草稿", confirmed: "已确认" }[currentVersion?.confirmationStatus ?? "draft"]}{currentVersion?.isEffective ? " · 当前需求基线" : ""}</p></div>{resultRecoveryState === "ready" ? <span className="rounded-token-md bg-subtle px-token-sm py-token-xs text-xs text-muted">已恢复第 {result?.roundNo} 轮澄清结果</span> : resultRecoveryState === "error" || resultRecoveryState === "loading" ? <span className="text-xs text-muted">{resultRecoveryState === "loading" ? "正在恢复已有澄清结果…" : "已有结果读取待重试"}</span> : <div className="flex flex-wrap gap-token-sm"><select aria-label="澄清模式" className="select-field w-auto" value={mode} onChange={(event) => setMode(event.target.value as ClarificationModeValue)}><option value="auto">自动 · 先预检</option><option value="standard">标准 · 最多 3 轮</option><option value="deep">深度 · 最多 5 轮</option><option value="skip">跳过 · 直接形成候选</option></select><Button onClick={startClarification} loading={busy}>{assessment ? "按所选模式继续" : "开始预检 / 澄清"}</Button></div>}</div><div className="mt-token-md rounded-token-md bg-subtle p-token-sm"><p className="text-xs font-medium text-muted">原始输入（保留）</p><p className="mt-token-xs whitespace-pre-wrap text-sm">{currentVersion?.content.rawInput}</p></div></article>
      <article className="panel"><div className="flex flex-wrap items-center justify-between gap-token-sm"><h2 className="font-semibold">2. 八类预检</h2>{assessment ? <span className="text-xs text-muted">复杂度 {assessment.complexityBand} · 建议 {assessment.recommendedMode}</span> : null}</div>{assessment?.reasons.length ? <p className="mt-token-sm text-sm text-secondary">{assessment.reasons.join("；")}</p> : null}<div className="mt-token-md grid gap-token-sm sm:grid-cols-2 lg:grid-cols-4">{dimensions.map(([key, label]) => { const item = assessment?.dimensions[key]; return <div key={key} className="rounded-token-md border border-default p-token-sm"><p className="text-sm font-medium">{label}</p><p className="mt-token-xs text-xs text-muted">{item?.status ?? "待检查"}</p>{item?.missingItems.length ? <p className="mt-token-xs text-xs text-warning">缺少：{item.missingItems.join("、")}</p> : null}{item?.reasons.length ? <p className="mt-token-xs text-xs text-secondary">{item.reasons.join("；")}</p> : null}{item?.sourceRefs.length ? <p className="mt-token-xs text-xs text-muted">来源 {item.sourceRefs.length} 条</p> : null}</div>; })}</div></article>
      {isRequirementComplete ? <StatusPanel tone="success" title="需求阶段已完成"><p>需求基线已确认，版本 {requirement.effectiveVersion?.versionNo ?? "—"} 已设为当前基线。</p><p className="mt-token-xs text-sm text-secondary">{isAiSourcedEffectiveBaseline ? "来源：采用 AI 候选。" : "来源：人工确认需求基线。"} 当前需求阶段已满足进入 PRD 的业务条件。</p>{projectId ? <Link className="mt-token-md inline-flex" href={`/projects/${projectId}/versions/${projectVersionId}/prd`}><Button>进入 PRD</Button></Link> : null}</StatusPanel> : null}
      {aiFailed && !isRequirementComplete ? <StatusPanel tone="warning" title="AI 暂不可用">候选结果未正式化。你仍可以直接编辑人工需求基线并确认。</StatusPanel> : null}
      {questions.length ? <article className="panel space-y-token-md"><h2 className="font-semibold">3. 第 {result?.roundNo ?? 1} 轮问题（{questions.length}/3）</h2>{questions.map((question) => <div key={question.questionId}><label className="field-label" htmlFor={question.questionId}>{question.questionText}</label><textarea id={question.questionId} className="textarea-field min-h-24" value={answers[question.questionId] ?? ""} onChange={(event) => setAnswers((old) => ({ ...old, [question.questionId]: event.target.value }))} /></div>)}{mode === "deep" && (result?.roundNo ?? 1) >= 4 ? <label className="flex items-center gap-token-sm text-sm"><input type="checkbox" checked={deepContinueConfirmed} onChange={(event) => setDeepContinueConfirmed(event.target.checked)} />我确认继续深度澄清第 {result?.roundNo} 轮</label> : null}<div className="flex flex-wrap gap-token-sm"><Button variant="secondary" onClick={() => submitAnswers(false)} loading={busy} disabled={mode === "deep" && (result?.roundNo ?? 1) >= 4 && !deepContinueConfirmed}>保存回答</Button><Button onClick={() => submitAnswers(true)} loading={busy} disabled={mode === "deep" && (result?.roundNo ?? 1) >= 4 && !deepContinueConfirmed}>结束并审核需求基线</Button></div></article> : null}
      {baselineCandidate && !isAiCandidateAdopted && !isRequirementComplete ? <article className="panel space-y-token-md"><div className="flex flex-wrap items-center justify-between gap-token-sm"><h2 className="font-semibold">4. 需求基线候选审核</h2><span className="text-xs text-muted">质量 {result?.quality.requiredItemsMet}/{result?.quality.requiredItemsTotal}</span></div><p className="text-sm text-secondary">AI 能力来源：{result?.capabilitySummary.truthLabel === "REAL_PROVIDER" ? "真实模型" : result?.capabilitySummary.truthLabel === "FORMAL_MOCK" ? "正式模拟" : "不可用"}</p><p className="text-sm text-secondary">格式 {result?.quality.formatStatus} · 可追溯性 {result?.quality.traceabilityStatus} · 安全 {result?.quality.safetyStatus}</p><div className="grid gap-token-sm sm:grid-cols-2">{dimensions.map(([key, label]) => <div key={key} className="rounded-token-md border border-default p-token-sm"><p className="text-sm font-medium">{label}</p><p className="mt-token-xs text-sm">{baselineCandidate.dimensions[key].confirmedFacts.join("；") || "无已确认事实"}</p><p className="mt-token-xs text-xs text-muted">来源 {baselineCandidate.dimensions[key].sourceRefs.length} 条</p></div>)}</div>{editableCandidateBaseline?.unresolvedItems.length ? <StatusPanel tone="warning" title="未决项阻断直接采用"><ul className="space-y-token-sm">{editableCandidateBaseline.unresolvedItems.map((item, index) => <li key={`${item}-${index}`} className="flex flex-wrap items-center justify-between gap-token-sm"><span>{item}</span><Button variant="secondary" onClick={() => setCandidateBaseline((current) => { const candidate = current ?? baselineCandidate; return candidate ? { ...candidate, unresolvedItems: candidate.unresolvedItems.filter((_, currentIndex) => currentIndex !== index) } : current; })}>标记已处理：{item}</Button></li>)}</ul></StatusPanel> : isModifiedCandidate ? <StatusPanel tone="success" title="未决项已显式处理">仅候选副本中的未决项已移除；可修改后采用。</StatusPanel> : null}{result?.quality.blockerCodes.length ? <StatusPanel tone="warning" title="候选暂不可采用">{result.quality.blockerCodes.join("、")}</StatusPanel> : null}<Button onClick={formalizeBaseline} loading={busy} disabled={!canFormalize}>{isModifiedCandidate ? "修改后采用并形成新版本" : "采用需求基线并形成新版本"}</Button></article> : null}
      {adoptedDraft ? <article className="panel space-y-token-md"><h2 className="font-semibold">4. 需求基线已采用，待确认</h2><p className="text-sm text-secondary">版本 {currentVersion?.versionNo} · 草稿 · 尚未设为当前需求基线</p><Button onClick={confirmAdoptedBaseline} loading={busy}>确认并设为当前需求基线</Button></article> : null}
      <article className="panel space-y-token-md"><h2 className="font-semibold">{baselineCandidate ? "5" : "4"}. 人工需求基线编辑与确认</h2><p className="text-sm text-secondary">AI 失败、质量阻断或过期时仍可人工继续；人工确认与 AI 候选采用是两条明确路径。</p>{dimensions.map(([key, label]) => <div key={key}><label className="field-label" htmlFor={`baseline-${key}`}>{label}</label><textarea id={`baseline-${key}`} className="textarea-field min-h-20" value={baseline.dimensions[key].confirmedFacts.join("\n")} onChange={(event) => setBaseline((old) => ({ ...old, dimensions: { ...old.dimensions, [key]: { ...old.dimensions[key], confirmedFacts: event.target.value.split("\n").filter(Boolean) } } }))} /></div>)}<Button onClick={confirmBaseline} loading={busy} disabled={!currentVersion}>人工确认需求基线</Button></article>
    </> : null}
  </section>;
}
