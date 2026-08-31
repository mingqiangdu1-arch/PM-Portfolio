"use client";
import { ChangeEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { StatusPanel } from "@/components/status-panel";
import { frontendApi } from "@/lib/api/frontend-api";
import { PortError, type FileItemView, type Scenario } from "@/lib/api/ports";

const statusText: Record<FileItemView["status"], string> = { uploading: "上传中", uploaded: "已上传", failed: "上传失败", parsing: "解析中", "manual-required": "需人工确认" };

const MAX_UPLOAD_SIZE = 52_428_800;

function uploadErrorCopy(reason: unknown): string {
  if (reason instanceof PortError) {
    if (reason.apiCode === "FILE_TOO_LARGE") return "文件超过 50 MB 上限，请选择较小的文件。";
    if (reason.apiCode === "VALIDATION_ERROR") return "文件信息不符合上传要求，请重新选择。";
    if (reason.apiCode === "FORBIDDEN") return "当前身份没有上传项目资料的权限。";
  }
  return "项目资料上传未完成，请稍后重试。";
}

function validateFile(file: File): string | null {
  if (file.size < 1) return "文件内容为空，无法上传。";
  if (file.size > MAX_UPLOAD_SIZE) return "文件超过 50 MB 上限，请选择较小的文件。";
  return null;
}

export function FilePanel({ projectId, scenario = "ready" }: { projectId: string; scenario?: Scenario }) {
  const [items, setItems] = useState<FileItemView[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [reloadCount, setReloadCount] = useState(0);
  const [busyById, setBusyById] = useState<Record<string, boolean>>({});
  const readOnly = scenario === "readonly" || scenario === "forbidden";

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadError("");
    void frontendApi.files.list(projectId)
      .then((next) => {
        if (!active) return;
        setItems((current) => {
          const recoveredIds = new Set(next.map((item) => item.id));
          const localOnly = current.filter((item) => !recoveredIds.has(item.id) && Boolean(item.retryFile || item.pendingUpload || item.status === "uploading"));
          return [...next, ...localOnly];
        });
      })
      .catch(() => { if (active) setLoadError("项目资料读取失败，请稍后重试。"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [projectId, reloadCount]);

  async function select(event: ChangeEvent<HTMLInputElement>) {
    const chosen = Array.from(event.target.files ?? []);
    for (const [index, file] of chosen.entries()) {
      const pending: FileItemView = {
        id: `pending-${file.name}-${file.lastModified}-${index}`,
        name: file.name,
        progress: 12,
        status: "uploading",
        relation: null,
        retryFile: file,
      };
      const validationError = validateFile(file);
      if (validationError) {
        setItems((current) => [...current, { ...pending, progress: 0, status: "failed", retryFile: undefined, error: validationError }]);
        continue;
      }
      setItems((current) => [...current, pending]);
      const result = await frontendApi.files.upload(
        projectId,
        file,
        scenario,
        (progress) => setItems((current) => current.map((item) => item.id === pending.id ? { ...item, progress } : item)),
      ).catch((reason: unknown) => ({ ...pending, progress: 0, status: "failed" as const, retryFile: file, error: uploadErrorCopy(reason) }));
      const normalizedResult = result.status === "failed" && !result.retryFile ? { ...result, retryFile: file } : result;
      setItems((current) => current.map((item) => item.id === pending.id ? normalizedResult : item));
    }
    event.target.value = "";
  }

  async function retry(item: FileItemView) {
    if (busyById[item.id]) return;
    setBusyById((current) => ({ ...current, [item.id]: true }));
    try {
      const result = await frontendApi.files.retry(projectId, item);
      setItems((current) => current.map((entry) => entry.id === item.id ? { ...result, retryFile: result.retryFile ?? item.retryFile, pendingUpload: result.pendingUpload ?? item.pendingUpload } : entry));
    } catch (reason: unknown) {
      setItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, status: "failed", progress: 0, retryFile: entry.retryFile ?? item.retryFile, pendingUpload: entry.pendingUpload ?? item.pendingUpload, error: uploadErrorCopy(reason) } : entry));
    } finally {
      setBusyById((current) => { const next = { ...current }; delete next[item.id]; return next; });
    }
  }

  return <section>
    <p className="text-sm font-medium text-ai">项目资料</p>
    <h1 className="mt-token-xs text-3xl font-semibold">项目资料与关联</h1>
    <p className="mt-token-xs text-secondary">每个文件独立上传、恢复与关联；存储完成前不显示成功。</p>
    <div className="mt-token-xl space-y-token-md">
      {readOnly ? <StatusPanel tone="warning" title={scenario === "forbidden" ? "无上传权限" : "只读模式"}>现有资料与关联仍可查看，上传和修改关联已禁用。</StatusPanel> : null}
      {loadError ? <StatusPanel tone="error" title="项目资料读取失败" action={<Button variant="secondary" onClick={() => setReloadCount((count) => count + 1)}>重新读取</Button>}>{loadError}</StatusPanel> : null}
      <div className="panel">
        <label className="field-label" htmlFor="file-upload">选择资料</label>
        <input id="file-upload" type="file" multiple onChange={select} disabled={readOnly || loading} className="block w-full max-w-full text-sm" />
        <p className="field-help">单个文件最大 50 MB；空文件和超限文件会显示明确提示。</p>
      </div>
      {loading ? <div role="status" className="panel animate-pulse text-muted">正在读取项目资料…</div> : null}
      {!loading && items.length === 0 ? <StatusPanel title="尚未上传资料">上传后，每个文件会分别显示进度、解析状态和对象关联。</StatusPanel> : null}
      {items.length ? <ul className="space-y-token-md">{items.map((item) => <li key={item.id} className="panel">
        <div className="flex flex-wrap items-start justify-between gap-token-md">
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{item.name}</p>
            <p className={`mt-token-xs text-sm ${item.status === "failed" ? "text-error" : "text-secondary"}`}>{statusText[item.status]} · {item.progress}%</p>
            <div className="mt-token-sm h-2 overflow-hidden rounded-full bg-subtle" aria-label={`上传进度 ${item.progress}%`} role="progressbar" aria-valuenow={item.progress} aria-valuemin={0} aria-valuemax={100}><div className={`h-full ${item.status === "failed" ? "bg-error" : "bg-brand-primary"}`} style={{ width: `${item.progress}%` }} /></div>
            {item.error ? <p role="alert" className="mt-token-sm text-sm text-error">{item.error}</p> : null}
          </div>
          {item.status === "failed" && (item.pendingUpload || item.retryFile) ? <Button variant="secondary" disabled={Boolean(busyById[item.id])} onClick={() => { void retry(item); }}>{busyById[item.id] ? "重试中…" : "重试此文件"}</Button> : null}
        </div>
        {item.status === "uploaded" ? <p className="mt-token-md text-sm text-secondary">文件已安全保存；重新进入项目后仍会从服务端恢复。</p> : null}
      </li>)}</ul> : null}
    </div>
  </section>;
}
