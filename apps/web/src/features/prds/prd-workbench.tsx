"use client";

import { FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusPanel } from "@/components/status-panel";
import { frontendApi } from "@/lib/api/frontend-api";
import type { DesignReviewView, FrontendApi, PrdContentView, PrdVersionView, PrdView } from "@/lib/api/ports";
import { PortError } from "@/lib/api/ports";

type ArrayField = "inScope" | "outOfScope" | "coreWorkflow" | "keyRules" | "exceptionsAndBoundaries" | "acceptanceCriteria";

const arrayFields: Array<{ key: ArrayField; label: string }> = [
  { key: "inScope", label: "范围内" },
  { key: "outOfScope", label: "范围外" },
  { key: "coreWorkflow", label: "核心工作流" },
  { key: "keyRules", label: "关键规则" },
  { key: "exceptionsAndBoundaries", label: "异常与边界" },
  { key: "acceptanceCriteria", label: "验收标准" },
];

const blankContent = (): PrdContentView => ({
  schemaVersion: "prd.mvp2.v1",
  background: "",
  goal: "",
  primaryUser: "",
  inScope: [],
  outOfScope: [],
  coreWorkflow: [],
  keyRules: [],
  exceptionsAndBoundaries: [],
  acceptanceCriteria: [],
});

const lines = (value: string) => value.split("\n").map((item) => item.trim()).filter(Boolean);
const errorCopy = (reason: unknown) => {
  if (reason instanceof PortError) {
    const code = reason.apiCode;
    if (["VERSION_CONFLICT", "INVALID_STATE", "IDEMPOTENCY_CONFLICT", "VALIDATION_ERROR", "FORBIDDEN", "NOT_FOUND"].includes(code ?? "")) return `${code}：${reason.message}`;
    return reason.message;
  }
  return reason instanceof Error ? reason.message : "操作未完成，请保留当前输入后重试。";
};

type InitialLoad =
  | { kind: "empty"; sourceVersionId: string | null; sourceBlocker: string; name: string }
  | { kind: "existing"; prd: PrdView; version: PrdVersionView | null; content: PrdContentView };

async function loadInitialPrdWorkbench(api: FrontendApi, projectVersionId: string): Promise<InitialLoad> {
  const existing = await api.prds.list(projectVersionId);
  if (existing.length > 1) throw new PortError("FAILED", "当前 project-version 返回多个 PRD，冻结接口未提供选择规则。");
  if (!existing.length) {
    const requirements = await api.requirements.list(projectVersionId);
    const candidates = requirements.filter((item) => item.effectiveVersionId);
    if (candidates.length === 1) return { kind: "empty", sourceVersionId: candidates[0].effectiveVersionId, sourceBlocker: "", name: `${candidates[0].title} PRD` };
    return {
      kind: "empty",
      sourceVersionId: null,
      sourceBlocker: candidates.length === 0 ? "当前项目版本没有 confirmed Requirement / Baseline Version，不能创建 PRD。" : "当前项目版本存在多个 confirmed Requirement / Baseline Version，冻结接口未提供唯一选择规则，不能创建 PRD。",
      name: "",
    };
  }
  const prd = await api.prds.get(existing[0].id);
  if (!prd.currentVersionId) return { kind: "existing", prd, version: null, content: blankContent() };
  const version = await api.prds.getVersion(prd.currentVersionId);
  return { kind: "existing", prd, version, content: version.content };
}

export function PrdWorkbench({ projectVersionId, api = frontendApi }: { projectVersionId: string; api?: FrontendApi }) {
  const [prd, setPrd] = useState<PrdView | null>(null);
  const [version, setVersion] = useState<PrdVersionView | null>(null);
  const [review, setReview] = useState<DesignReviewView | null>(null);
  const [content, setContent] = useState<PrdContentView>(blankContent);
  const [name, setName] = useState("");
  const [sourceVersionId, setSourceVersionId] = useState<string | null>(null);
  const [sourceBlocker, setSourceBlocker] = useState("");
  const [changeNote, setChangeNote] = useState("");
  const [decisionSummary, setDecisionSummary] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    void loadInitialPrdWorkbench(api, projectVersionId)
      .then((initial) => {
        if (!active) return;
        setError("");
        setReview(null);
        if (initial.kind === "empty") {
          setPrd(null);
          setVersion(null);
          setContent(blankContent());
          setSourceVersionId(initial.sourceVersionId);
          setSourceBlocker(initial.sourceBlocker);
          setName(initial.name);
        } else {
          setPrd(initial.prd);
          setVersion(initial.version);
          setContent(initial.content);
          setSourceVersionId(initial.prd.sourceRequirementVersionId);
          setSourceBlocker("");
        }
        setLoading(false);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(errorCopy(reason));
        setLoading(false);
      });
    return () => { active = false; };
  }, [api, projectVersionId]);

  const isReadOnly = prd?.status === "confirmed" || prd?.status === "in_review";
  const canEdit = Boolean(prd && !isReadOnly);

  const create = async (event: FormEvent) => {
    event.preventDefault();
    if (!sourceVersionId) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const created = await api.prds.create(projectVersionId, { name: name.trim(), sourceRequirementVersionId: sourceVersionId });
      setPrd(created);
      setContent(blankContent());
      setMessage("PRD identity 已创建。请填写固定结构并显式保存首个不可变版本。");
    } catch (reason) { setError(errorCopy(reason)); } finally { setBusy(false); }
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!prd) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const saved = await api.prds.saveVersion(prd.id, { expectedVersion: prd.rowVersion, changeNote: changeNote.trim(), content });
      const aggregate = await api.prds.get(prd.id);
      setVersion(saved); setPrd(aggregate); setChangeNote("");
      setMessage(`已显式保存不可变 PRD Version ${saved.versionNo}。`);
    } catch (reason) { setError(errorCopy(reason)); } finally { setBusy(false); }
  };

  const submit = async () => {
    if (!prd || !version) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const submitted = await api.prds.submitReview(projectVersionId, { prdId: prd.id, prdVersionId: version.id, contentHash: version.contentHash, expectedVersion: prd.rowVersion });
      const aggregate = await api.prds.get(prd.id);
      setReview(submitted); setPrd(aggregate); setMessage(`Design Review Round ${submitted.roundNo} 已提交。`);
    } catch (reason) { setError(errorCopy(reason)); } finally { setBusy(false); }
  };

  const decide = async (decision: "changes_requested" | "pass") => {
    if (!review || !prd) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const decided = await api.prds.decideReview(review.id, { decision, expectedVersion: review.rowVersion, summary: decision === "changes_requested" ? decisionSummary.trim() : undefined });
      const aggregate = await api.prds.get(prd.id);
      setReview(decided); setPrd(aggregate); setDecisionSummary("");
      setMessage(decision === "pass" ? "Design Review 已通过；PRD 已 confirmed 并变为只读。" : "Design Review 已要求修改；请编辑后显式保存新 Version，再次提交。");
    } catch (reason) { setError(errorCopy(reason)); } finally { setBusy(false); }
  };

  const update = <K extends keyof PrdContentView>(key: K, value: PrdContentView[K]) => setContent((current) => ({ ...current, [key]: value }));

  if (loading) return <section><p className="text-sm font-medium text-ai">PC-04 · MVP2</p><h1 className="mt-token-xs text-3xl font-semibold">Structured PRD Workbench</h1><div role="status" className="panel mt-token-xl animate-pulse text-muted">正在读取 PRD 与 confirmed Requirement Baseline…</div></section>;

  return <section aria-labelledby="prd-workbench-title">
    <p className="text-sm font-medium text-ai">PC-04 · MVP2</p>
    <h1 id="prd-workbench-title" className="mt-token-xs text-3xl font-semibold">Structured PRD Workbench</h1>
    <p className="mt-token-xs text-secondary">固定 schema：prd.mvp2.v1。保存始终创建新版本，不会覆盖历史。</p>
    <div className="mt-token-xl space-y-token-md">
      {error ? <StatusPanel tone="error" title="PRD 操作未完成">{error}</StatusPanel> : null}
      {message ? <StatusPanel tone="success" title="操作完成">{message}</StatusPanel> : null}
      {!prd ? <form className="panel" onSubmit={create}>
        <h2 className="font-semibold">从 confirmed Requirement / Baseline 创建 PRD</h2>
        {sourceBlocker ? <StatusPanel tone="warning" title="无法唯一确定来源 Version">{sourceBlocker}</StatusPanel> : <p className="mt-token-sm text-sm text-secondary">来源 Requirement Version：{sourceVersionId}</p>}
        <label className="mt-token-md block"><span className="field-label">PRD 名称</span><Input value={name} onChange={(event) => setName(event.target.value)} disabled={!sourceVersionId || busy} required /></label>
        <Button className="mt-token-md" type="submit" loading={busy} disabled={!sourceVersionId || !name.trim()}>创建 PRD identity</Button>
      </form> : <>
        <article className="panel"><h2 className="font-semibold">当前 PRD</h2><dl className="mt-token-sm grid gap-token-sm text-sm sm:grid-cols-2"><div><dt className="text-muted">名称</dt><dd>{prd.name}</dd></div><div><dt className="text-muted">状态</dt><dd>{prd.status}</dd></div><div><dt className="text-muted">row_version</dt><dd>{prd.rowVersion}</dd></div><div><dt className="text-muted">当前版本</dt><dd>{version?.versionNo ?? "尚未保存"}</dd></div></dl>{prd.status === "confirmed" ? <div className="mt-token-md"><StatusPanel tone="success" title="PRD 已 confirmed">当前 PRD 已通过 Design Review；结构化编辑器已只读。</StatusPanel></div> : null}</article>
        {review ? <article className="panel"><h2 className="font-semibold">Design Review · Round {review.roundNo}</h2><p className="mt-token-xs text-sm text-secondary">状态：{review.status} · row_version：{review.rowVersion}</p>{review.status === "changes_requested" ? <StatusPanel tone="warning" title="要求修改">{review.summary}</StatusPanel> : null}{review.status === "open" ? <div className="mt-token-md space-y-token-sm"><label className="block"><span className="field-label">changes_requested summary</span><textarea aria-label="changes_requested summary" className="textarea-field min-h-24" value={decisionSummary} onChange={(event) => setDecisionSummary(event.target.value)} disabled={busy} /></label><div className="flex flex-wrap gap-token-sm"><Button type="button" variant="secondary" loading={busy} disabled={!decisionSummary.trim()} onClick={() => void decide("changes_requested")}>要求修改</Button><Button type="button" loading={busy} onClick={() => void decide("pass")}>通过 Review</Button></div></div> : null}</article> : null}
        <form className="space-y-token-md" onSubmit={save}>
          <article className="panel"><h2 className="font-semibold">固定 PRD 结构</h2><p className="mt-token-xs text-sm text-secondary">schema_version：prd.mvp2.v1</p>
            <div className="mt-token-md grid gap-token-md lg:grid-cols-2">
              <label><span className="field-label">背景</span><textarea aria-label="背景" className="textarea-field min-h-24" value={content.background} onChange={(event) => update("background", event.target.value)} disabled={isReadOnly || busy} required /></label>
              <label><span className="field-label">目标</span><textarea aria-label="目标" className="textarea-field min-h-24" value={content.goal} onChange={(event) => update("goal", event.target.value)} disabled={isReadOnly || busy} required /></label>
              <label className="lg:col-span-2"><span className="field-label">主要用户</span><Input value={content.primaryUser} onChange={(event) => update("primaryUser", event.target.value)} disabled={isReadOnly || busy} required /></label>
              {arrayFields.map((field) => <label key={field.key}><span className="field-label">{field.label}</span><textarea aria-label={field.label} className="textarea-field min-h-24" value={content[field.key].join("\n")} onChange={(event) => update(field.key, lines(event.target.value))} disabled={isReadOnly || busy} required /></label>)}
            </div>
          </article>
          {!isReadOnly ? <article className="panel"><h2 className="font-semibold">显式保存新 PRD Version</h2><label className="mt-token-md block"><span className="field-label">变更说明</span><Input value={changeNote} onChange={(event) => setChangeNote(event.target.value)} disabled={busy} required /></label><Button className="mt-token-md" type="submit" loading={busy} disabled={!changeNote.trim()}>显式保存新版本</Button></article> : null}
        </form>
        {canEdit && version ? <article className="panel"><h2 className="font-semibold">提交 Design Review</h2><p className="mt-token-xs text-sm text-secondary">提交固定为当前 PRD Version {version.versionNo}。</p><Button className="mt-token-md" type="button" loading={busy} disabled={busy || Boolean(review?.status === "open")} onClick={() => void submit()}>提交 Review</Button></article> : null}
      </>}
    </div>
  </section>;
}
