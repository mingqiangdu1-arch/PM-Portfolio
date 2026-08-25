"use client";

import { FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { StatusPanel } from "@/components/status-panel";
import type { FrontendApi, IssuePriority, IssueSeverity, IssueType, IssueView, ProjectCapabilities, TestRecordView } from "@/lib/api/ports";

type Form = {
  issueType: IssueType; title: string; description: string; priority: IssuePriority; severity: IssueSeverity;
  reproduceSteps: string; expectedResult: string; actualResult: string; problemEvidence: string;
  hypothesis: string; expectedOutcome: string; impactScope: string; needNewVersion: boolean;
};
const blank: Form = { issueType: "defect", title: "", description: "", priority: "medium", severity: "medium", reproduceSteps: "", expectedResult: "", actualResult: "", problemEvidence: "", hypothesis: "", expectedOutcome: "", impactScope: "", needNewVersion: false };
const errorText = (reason: unknown) => reason instanceof Error ? reason.message : "Issue 操作未完成，输入已保留。";

export function IssueWorkspace({ projectId, projectVersionId, record, capabilities, api, onIssuePresenceChange }: { projectId?: string; projectVersionId: string; record: TestRecordView; capabilities: ProjectCapabilities | null; api: FrontendApi; onIssuePresenceChange?: (present: boolean) => void }) {
  const [issues, setIssues] = useState<IssueView[]>([]);
  const [selected, setSelected] = useState<IssueView | null>(null);
  const [form, setForm] = useState<Form>(blank);
  const [creating, setCreating] = useState(false);
  const [reason, setReason] = useState("");
  const [responsibleUserId, setResponsibleUserId] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const canEdit = capabilities?.canTestRecordWrite === true;
  const canDispose = capabilities?.canConfirm === true;

  function populate(issue: IssueView) {
    setSelected(issue); setCreating(false);
    setForm({ issueType: issue.issueType, title: issue.title, description: issue.description, priority: issue.priority, severity: issue.severity, reproduceSteps: issue.bugDetail?.reproduceSteps ?? "", expectedResult: issue.bugDetail?.expectedResult ?? "", actualResult: issue.bugDetail?.actualResult ?? "", problemEvidence: issue.optimizationDetail?.problemEvidence ?? "", hypothesis: issue.optimizationDetail?.hypothesis ?? "", expectedOutcome: issue.optimizationDetail?.expectedOutcome ?? "", impactScope: issue.optimizationDetail?.impactScope ?? "", needNewVersion: issue.optimizationDetail?.needNewVersion ?? false });
  }
  async function load() {
    setLoading(true); setError("");
    try {
      const next = (await api.issues.list(projectVersionId)).filter((item) => item.testRecordId === record.id);
      setIssues(next); onIssuePresenceChange?.(next.length > 0);
      if (selected) { const refreshed = next.find((item) => item.id === selected.id); if (refreshed) populate(refreshed); }
    } catch (reasonValue) { setError(errorText(reasonValue)); }
    finally { setLoading(false); }
  }
  // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
  useEffect(() => { void load(); }, [projectVersionId, record.id, api]);

  function details(value: Form) {
    return {
      bugDetail: value.issueType === "defect" ? { reproduceSteps: value.reproduceSteps.trim(), expectedResult: value.expectedResult.trim(), actualResult: value.actualResult.trim(), environment: null } : null,
      optimizationDetail: value.issueType === "optimization" ? { problemEvidence: value.problemEvidence.trim(), hypothesis: value.hypothesis.trim(), expectedOutcome: value.expectedOutcome.trim(), impactScope: value.impactScope.trim(), needNewVersion: value.needNewVersion } : null,
    };
  }
  async function create(event: FormEvent) {
    event.preventDefault(); if (!canEdit) return; setBusy(true); setError(""); setMessage("");
    try {
      const issue = await api.issues.create(projectVersionId, { testRecordId: record.id, issueType: form.issueType, title: form.title.trim(), description: form.description.trim(), priority: form.priority, severity: form.severity, assigneeId: null, ...details(form) });
      setIssues((current) => [issue, ...current]); populate(issue); onIssuePresenceChange?.(true); setMessage("Issue 已持久化，等待人工处置。");
    } catch (reasonValue) { setError(errorText(reasonValue)); } finally { setBusy(false); }
  }
  async function save(event: FormEvent) {
    event.preventDefault(); if (!selected || selected.status !== "open_needs_disposition" || !canEdit) return; setBusy(true); setError(""); setMessage("");
    try {
      const issue = await api.issues.update(selected.id, { expectedVersion: selected.rowVersion, title: form.title.trim(), description: form.description.trim(), priority: form.priority, severity: form.severity, ...details(form) });
      setIssues((current) => current.map((item) => item.id === issue.id ? issue : item)); populate(issue); setMessage("Issue 修改已保存。");
    } catch (reasonValue) { setError(errorText(reasonValue)); } finally { setBusy(false); }
  }
  async function dispose(kind: "current_version_fix" | "defer" | "reject") {
    if (!selected || !canDispose || !reason.trim() || !responsibleUserId.trim()) return; setBusy(true); setError(""); setMessage("");
    try {
      const issue = await api.issues.dispose(selected.id, selected.rowVersion, kind, reason.trim(), responsibleUserId.trim());
      setIssues((current) => current.map((item) => item.id === issue.id ? issue : item)); populate(issue);
      setMessage(kind === "current_version_fix" ? "已路由到当前版本修正；请创建新的 Confirmation Round。" : "Issue 处置已记录。");
    } catch (reasonValue) { setError(errorText(reasonValue)); } finally { setBusy(false); }
  }
  async function derive() {
    if (!selected || !projectId || !canDispose || !reason.trim()) return; setBusy(true); setError(""); setMessage("");
    try {
      const project = await api.projects.overview(projectId, projectVersionId);
      const changeType = selected.issueType === "defect" ? "bug_fix" : selected.issueType === "optimization" ? "optimization" : "scope_change";
      const version = await api.projects.derive(projectId, { sourceVersionId: projectVersionId, sourceIssueId: selected.id, changeType, reason: reason.trim(), inheritContext: true, inheritanceChoices: { requirements: true, prd: true, implementationPlan: false }, expectedProjectVersion: project.projectVersion });
      await load(); setMessage(`已派生 ${version.number}；新版本未自动切换为 working version。`);
    } catch (reasonValue) { setError(errorText(reasonValue)); } finally { setBusy(false); }
  }

  const fields = <>
    <label className="block"><span className="field-label">Title</span><input className="input-field" value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} required maxLength={200} /></label>
    <label className="block"><span className="field-label">Description</span><textarea className="textarea-field min-h-24" value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} required /></label>
    <div className="grid gap-token-sm md:grid-cols-2"><label><span className="field-label">Priority</span><select className="input-field" value={form.priority} onChange={(event) => setForm((current) => ({ ...current, priority: event.target.value as IssuePriority }))}><option value="low">low</option><option value="medium">medium</option><option value="high">high</option><option value="urgent">urgent</option></select></label><label><span className="field-label">Severity</span><select className="input-field" value={form.severity} onChange={(event) => setForm((current) => ({ ...current, severity: event.target.value as IssueSeverity }))}><option value="low">low</option><option value="medium">medium</option><option value="high">high</option><option value="critical">critical</option></select></label></div>
    {form.issueType === "defect" ? <div className="grid gap-token-sm"><label><span className="field-label">Reproduce steps</span><textarea className="textarea-field" value={form.reproduceSteps} onChange={(event) => setForm((current) => ({ ...current, reproduceSteps: event.target.value }))} required /></label><label><span className="field-label">Expected result</span><textarea className="textarea-field" value={form.expectedResult} onChange={(event) => setForm((current) => ({ ...current, expectedResult: event.target.value }))} required /></label><label><span className="field-label">Actual result</span><textarea className="textarea-field" value={form.actualResult} onChange={(event) => setForm((current) => ({ ...current, actualResult: event.target.value }))} required /></label></div> : null}
    {form.issueType === "optimization" ? <div className="grid gap-token-sm"><label><span className="field-label">Problem evidence</span><textarea className="textarea-field" value={form.problemEvidence} onChange={(event) => setForm((current) => ({ ...current, problemEvidence: event.target.value }))} required /></label><label><span className="field-label">Hypothesis</span><textarea className="textarea-field" value={form.hypothesis} onChange={(event) => setForm((current) => ({ ...current, hypothesis: event.target.value }))} required /></label><label><span className="field-label">Expected outcome</span><textarea className="textarea-field" value={form.expectedOutcome} onChange={(event) => setForm((current) => ({ ...current, expectedOutcome: event.target.value }))} required /></label><label><span className="field-label">Impact scope</span><textarea className="textarea-field" value={form.impactScope} onChange={(event) => setForm((current) => ({ ...current, impactScope: event.target.value }))} required /></label><label className="flex items-center gap-token-xs"><input type="checkbox" checked={form.needNewVersion} onChange={(event) => setForm((current) => ({ ...current, needNewVersion: event.target.checked }))} />需要派生新版本</label></div> : null}
  </>;

  return <section className="space-y-token-md border-t border-subtle pt-token-md" aria-label="Issue workspace">
    <div className="flex flex-wrap items-center justify-between gap-token-sm"><div><p className="text-sm font-medium text-ai">MVP5 · Validation Feedback</p><h3 className="font-semibold">Issue 分类与处置</h3></div>{canEdit && !record.noIssueConclusion ? <Button type="button" variant="secondary" onClick={() => { setCreating(true); setSelected(null); setForm(blank); }}>创建 Issue</Button> : null}</div>
    {loading ? <div role="status" className="text-sm text-muted">正在加载 Issue…</div> : null}{error ? <StatusPanel tone="error" title="Issue 操作未完成">{error}</StatusPanel> : null}{message ? <StatusPanel tone="success" title="已完成">{message}</StatusPanel> : null}
    {issues.length ? <div className="grid gap-token-sm md:grid-cols-2">{issues.map((issue) => <button type="button" key={issue.id} className={`rounded-token-md border p-token-sm text-left ${selected?.id === issue.id ? "border-primary bg-primary-subtle" : "border-subtle"}`} onClick={() => populate(issue)}><strong>{issue.title}</strong><span className="mt-token-xs block text-xs text-muted">{issue.issueType} · {issue.status} · row {issue.rowVersion}</span></button>)}</div> : !loading ? <StatusPanel tone="neutral" title="尚无 Issue">可以明确确认无 Issue，或创建受治理的反馈记录。</StatusPanel> : null}
    {creating ? <form className="space-y-token-sm" onSubmit={create}><label><span className="field-label">Issue type</span><select className="input-field" value={form.issueType} onChange={(event) => setForm({ ...blank, issueType: event.target.value as IssueType })}><option value="defect">defect</option><option value="feedback">feedback</option><option value="data_anomaly">data_anomaly</option><option value="optimization">optimization</option></select></label>{fields}<Button type="submit" loading={busy}>保存 Issue</Button></form> : null}
    {selected ? <form className="space-y-token-sm" onSubmit={save}><div className="flex justify-between gap-token-sm"><strong>Issue #{selected.id}</strong><span className="text-xs text-muted">{selected.status}</span></div><label><span className="field-label">Issue type（创建后不可修改）</span><input className="input-field" value={selected.issueType} disabled /></label>{fields}{selected.status === "open_needs_disposition" && canEdit ? <Button type="submit" loading={busy}>保存修改</Button> : null}{selected.status === "open_needs_disposition" && canDispose ? <div className="space-y-token-sm rounded-token-md bg-subtle p-token-sm"><h4 className="font-medium">Owner 最终处置</h4><label><span className="field-label">Reason</span><textarea className="textarea-field" value={reason} onChange={(event) => setReason(event.target.value)} required /></label><label><span className="field-label">Responsible user ID</span><input className="input-field" value={responsibleUserId} onChange={(event) => setResponsibleUserId(event.target.value)} required /></label><div className="flex flex-wrap gap-token-xs"><Button type="button" variant="secondary" onClick={() => void dispose("current_version_fix")} disabled={busy}>当前版本修正</Button><Button type="button" variant="secondary" onClick={() => void derive()} disabled={busy || !projectId}>派生新版本</Button><Button type="button" variant="secondary" onClick={() => void dispose("defer")} disabled={busy}>暂缓</Button><Button type="button" variant="secondary" onClick={() => void dispose("reject")} disabled={busy}>拒绝</Button></div></div> : null}</form> : null}
  </section>;
}
