"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { StatusPanel } from "@/components/status-panel";
import { frontendApi } from "@/lib/api/frontend-api";
import type { ConfirmationRoundView, FrontendApi, ProjectCapabilities, TestRecordResultStatus, TestRecordView } from "@/lib/api/ports";

type DraftForm = {
  title: string;
  scope: string;
  environmentName: string;
  preconditions: string;
  steps: string;
  expectedResult: string;
  actualResult: string;
  resultStatus: TestRecordResultStatus;
};

const blank: DraftForm = { title: "", scope: "", environmentName: "", preconditions: "", steps: "", expectedResult: "", actualResult: "", resultStatus: "success" };
const toLines = (value: string) => value.split("\n").map((item) => item.trim()).filter(Boolean);
const fromRecord = (record: TestRecordView): DraftForm => ({ title: record.title, scope: record.scope, environmentName: record.environment.name, preconditions: record.environment.preconditions.join("\n"), steps: record.steps.join("\n"), expectedResult: record.expectedResult, actualResult: record.actualResult, resultStatus: record.resultStatus });

function errorText(reason: unknown) {
  if (reason instanceof Error) return reason.message;
  return "Test Record 操作未完成，请保留当前输入后重试。";
}

export function TestRecordWorkspace({ round, capabilities, api = frontendApi }: { round: ConfirmationRoundView; capabilities: ProjectCapabilities | null; api?: FrontendApi }) {
  const sourceValid = round.status === "confirmed" && round.isEffective;
  const canWrite = sourceValid && capabilities?.canTestRecordWrite === true;
  const [records, setRecords] = useState<TestRecordView[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState<DraftForm>(blank);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [openingId, setOpeningId] = useState<string | null>(null);
  const openSequence = useRef(0);

  const selected = useMemo(() => records.find((record) => record.id === selectedId) ?? null, [records, selectedId]);
  const editable = Boolean(selected && selected.status === "draft" && canWrite);

  async function loadRecords() {
    if (!api.testRecords) { setRecords([]); setSelectedId(null); return; }
    setLoading(true); setError("");
    try {
      const next = await api.testRecords.list(round.id);
      setRecords(next);
      setSelectedId((current) => next.some((record) => record.id === current) ? current : next.find((record) => record.status === "draft")?.id ?? next[0]?.id ?? null);
    } catch (reason) { setError(errorText(reason)); } finally { setLoading(false); }
  }

  // This list is the persisted source for reopen/read; it intentionally reloads on round changes.
  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { void loadRecords(); }, [round.id, round.status, round.isEffective, api]);
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { setForm(selected ? fromRecord(selected) : blank); }, [selected]);

  function updateField<K extends keyof DraftForm>(key: K, value: DraftForm[K]) { setForm((current) => ({ ...current, [key]: value })); }

  async function reopen(recordId: string) {
    if (openingId === recordId) return;
    const sequence = ++openSequence.current;
    setOpeningId(recordId); setError(""); setMessage("");
    try {
      const record = await api.testRecords.get(recordId);
      if (sequence !== openSequence.current) return;
      setRecords((current) => current.map((item) => item.id === record.id ? record : item));
      setSelectedId(record.id);
      setMessage("已重新读取持久化 Test Record。");
    } catch (reason) {
      if (sequence === openSequence.current) setError(errorText(reason));
    } finally {
      if (sequence === openSequence.current) setOpeningId(null);
    }
  }

  async function create(event: FormEvent) {
    event.preventDefault(); if (!canWrite) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const record = await api.testRecords.create(round.id, { title: form.title.trim(), scope: form.scope.trim(), environment: { name: form.environmentName.trim(), preconditions: toLines(form.preconditions) }, steps: toLines(form.steps), expectedResult: form.expectedResult.trim(), actualResult: form.actualResult.trim(), resultStatus: form.resultStatus });
      setRecords((current) => [...current, record]); setSelectedId(record.id); setMessage("Test Record 草稿已创建。");
    } catch (reason) { setError(errorText(reason)); } finally { setBusy(false); }
  }

  async function save(event: FormEvent) {
    event.preventDefault(); if (!selected || !editable) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const record = await api.testRecords.update(selected.id, { expectedVersion: selected.rowVersion, scope: form.scope.trim(), environment: { name: form.environmentName.trim(), preconditions: toLines(form.preconditions) }, steps: toLines(form.steps), expectedResult: form.expectedResult.trim(), actualResult: form.actualResult.trim(), resultStatus: form.resultStatus });
      setRecords((current) => current.map((item) => item.id === record.id ? record : item)); setMessage("Test Record 草稿已保存。");
    } catch (reason) { setError(errorText(reason)); }
    finally { setBusy(false); }
  }

  async function submit() {
    if (!selected || !editable) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const record = await api.testRecords.submit(selected.id, selected.rowVersion);
      setRecords((current) => current.map((item) => item.id === record.id ? record : item)); setSelectedId(record.id); setMessage("Test Record 已提交并冻结为只读。");
    } catch (reason) { setError(errorText(reason)); }
    finally { setBusy(false); }
  }

  const fields = (readOnly: boolean) => <>
    <label className="block"><span className="field-label">Scope</span><textarea className="textarea-field min-h-20" value={form.scope} onChange={(event) => updateField("scope", event.target.value)} disabled={readOnly} /></label>
    <label className="block"><span className="field-label">Environment name</span><input className="input-field" value={form.environmentName} onChange={(event) => updateField("environmentName", event.target.value)} disabled={readOnly} /></label>
    <label className="block"><span className="field-label">Environment preconditions（每行一项）</span><textarea className="textarea-field min-h-20" value={form.preconditions} onChange={(event) => updateField("preconditions", event.target.value)} disabled={readOnly} /></label>
    <label className="block"><span className="field-label">Steps（每行一步）</span><textarea className="textarea-field min-h-28" value={form.steps} onChange={(event) => updateField("steps", event.target.value)} disabled={readOnly} /></label>
    <label className="block"><span className="field-label">Expected result</span><textarea className="textarea-field min-h-20" value={form.expectedResult} onChange={(event) => updateField("expectedResult", event.target.value)} disabled={readOnly} /></label>
    <label className="block"><span className="field-label">Actual result</span><textarea className="textarea-field min-h-20" value={form.actualResult} onChange={(event) => updateField("actualResult", event.target.value)} disabled={readOnly} /></label>
    <label className="block"><span className="field-label">Result status</span><select className="input-field" value={form.resultStatus} onChange={(event) => updateField("resultStatus", event.target.value as TestRecordResultStatus)} disabled={readOnly}><option value="success">通过</option><option value="failed">未通过</option><option value="partial">部分完成</option></select></label>
  </>;

  return <section className="panel space-y-token-md" aria-label="Test Record workspace">
    <div className="flex flex-wrap items-start justify-between gap-token-md"><div><p className="text-sm font-medium text-ai">MVP4 · Test Record</p><h2 className="mt-token-xs text-xl font-semibold">测试验证记录</h2><p className="mt-token-xs text-sm text-secondary">绑定 Round {round.roundNo} · 持久化记录可重新打开核对。</p></div>{!canWrite && sourceValid ? <span className="rounded-full bg-subtle px-token-sm py-token-xs text-xs">当前身份只读</span> : null}</div>
    {!sourceValid ? <StatusPanel tone="neutral" title="历史确认轮次（只读）">当前 Round 已不再是 confirmed/effective source；仍可读取已保存的 Test Record，但不能创建、保存或提交。</StatusPanel> : null}
    {error ? <StatusPanel tone={error.includes("冲突") || error.includes("版本") ? "warning" : "error"} title="操作未完成">{error} 当前输入没有被清除。</StatusPanel> : null}
    {message ? <StatusPanel tone="success" title="已完成">{message}</StatusPanel> : null}
    {loading ? <div role="status" className="panel animate-pulse text-muted">正在加载 Test Record…</div> : null}
    {!loading && records.length === 0 ? <StatusPanel tone="neutral" title="尚无 Test Record">当前确认轮次还没有测试记录。</StatusPanel> : null}
    {records.length ? <div className="space-y-token-sm"><h3 className="font-semibold">已有记录</h3><div className="grid gap-token-sm md:grid-cols-2">{records.map((record) => <button type="button" key={record.id} className={`rounded-token-md border p-token-sm text-left ${selected?.id === record.id ? "border-primary bg-primary-subtle" : "border-subtle hover:bg-subtle"}`} onClick={() => void reopen(record.id)} disabled={openingId === record.id}><span className="font-medium">{record.title}</span><span className="mt-token-xs block text-xs text-muted">{openingId === record.id ? "正在重新读取…" : `${record.status} · ${record.resultStatus} · row ${record.rowVersion}`}</span></button>)}</div></div> : null}
    {canWrite && !selected ? <form className="space-y-token-md border-t border-subtle pt-token-md" onSubmit={create}><h3 className="font-semibold">创建 Test Record 草稿</h3><label className="block"><span className="field-label">Title</span><input className="input-field" value={form.title} onChange={(event) => updateField("title", event.target.value)} minLength={1} maxLength={200} disabled={busy} required /></label>{fields(false)}<Button type="submit" loading={busy}>创建草稿</Button></form> : null}
    {selected ? <form className="space-y-token-md border-t border-subtle pt-token-md" onSubmit={save}><div className="flex flex-wrap items-center justify-between gap-token-sm"><h3 className="font-semibold">{selected.status === "submitted" ? "已提交记录（只读）" : "编辑 Test Record 草稿"}</h3><span className="text-xs text-muted">{selected.status} · submitted_at {selected.submittedAt ?? "—"}</span></div><label className="block"><span className="field-label">Title（创建后不可修改）</span><input className="input-field" value={form.title} disabled /></label>{fields(!editable)}<div className="flex flex-wrap gap-token-sm">{editable ? <><Button type="submit" loading={busy}>保存草稿</Button><Button type="button" variant="secondary" loading={busy} onClick={submit}>提交并冻结</Button></> : null}</div></form> : null}
    {canWrite ? <Button type="button" variant="secondary" disabled={busy} onClick={() => { setSelectedId(null); setForm(blank); setError(""); setMessage(""); }}>新建另一条记录</Button> : null}
  </section>;
}
