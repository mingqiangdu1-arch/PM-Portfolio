import {
  abortFileUpload,
  completeFileUpload,
  createProject,
  getApiHealth,
  getFile,
  getProject,
  getProjectVersion,
  getSession,
  initFileUpload,
  listProjects,
  listProjectVersions,
  login,
  logout,
  refreshAccessToken,
  register,
  setWorkingProjectVersion,
} from "./generated/client";
import type {
  ApiResponseHealthData,
  AuthTokenData,
  CreateProjectData,
  ErrorCode,
  ErrorResponse,
  FileData,
  FileUploadData,
  ProjectListData,
  ProjectSummary,
  ProjectVersionListData,
  ProjectVersionSummary,
  RefreshTokenData,
  SessionData,
  WorkingVersionChangeData,
} from "./generated/models";
import type {
  FileItemView,
  FrontendApi,
  FrontendErrorCategory,
  PendingUploadRecovery,
  ProjectOverviewView,
  ProjectSummaryView,
  SessionView,
  VersionView,
} from "./ports";
import { PortError } from "./ports";

type GeneratedResponse = { data: unknown; status: number; headers: Headers };
type Envelope<T> = { data: T; trace_id: string; message: string };
type UploadTransferError = PortError & { definitive?: boolean };
const explicitIncompleteCodes: ErrorCode[] = ["UPLOAD_INCOMPLETE", "CHECKSUM_MISMATCH", "FILE_TOO_LARGE", "FILE_TYPE_NOT_ALLOWED"];

let accessToken: string | null = null;
let refreshInFlight: Promise<void> | null = null;
let refreshGeneration: number | null = null;
let logoutInFlight: Promise<void> | null = null;
let logoutSequence = 0;
let authGeneration = 0;
let recoveryDispatchedForGeneration: number | null = null;
const retryKeys = new Map<string, string>();

const requestOptions = (): RequestInit => ({
  credentials: "include",
  headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
});

const commandKey = () => `web-${crypto.randomUUID()}`;
const retryKey = (scope: string) => {
  const existing = retryKeys.get(scope);
  if (existing) return existing;
  const created = commandKey();
  retryKeys.set(scope, created);
  return created;
};

function isEnvelope<T>(value: unknown): value is Envelope<T> {
  return Boolean(value && typeof value === "object" && "data" in value && "trace_id" in value);
}

function categoryFor(status: number, apiCode?: ErrorCode): FrontendErrorCategory {
  if (apiCode === "VERSION_CONFLICT" || apiCode === "IDEMPOTENCY_CONFLICT" || status === 409) return "CONFLICT";
  if (apiCode === "RATE_LIMITED") return "RATE_LIMITED";
  if (apiCode === "STORAGE_UNAVAILABLE" || apiCode === "DEPENDENCY_UNAVAILABLE") return "STORAGE_UNAVAILABLE";
  if (apiCode === "FORBIDDEN" || apiCode === "PERMISSION_CHANGED" || status === 403) return "FORBIDDEN";
  if (apiCode === "AUTH_REQUIRED" || apiCode === "UNAUTHORIZED" || apiCode === "REFRESH_INVALID" || apiCode === "TOKEN_REUSE_DETECTED" || status === 401) return "UNAUTHENTICATED";
  return "FAILED";
}

function unwrap<T>(response: GeneratedResponse): Envelope<T> {
  if (response.status >= 200 && response.status < 300 && isEnvelope<T>(response.data)) return response.data;
  const error = response.data as Partial<ErrorResponse> | undefined;
  const apiCode = error?.code;
  throw new PortError(categoryFor(response.status, apiCode), error?.message ?? `请求失败（HTTP ${response.status}）。`, response.status, error?.trace_id, error?.details ?? [], apiCode);
}

const isPortError = (value: unknown): value is PortError => value instanceof PortError;
const needsRefresh = (error: unknown) => isPortError(error) && error.category === "UNAUTHENTICATED";

function triggerSessionRecovery() {
  if (typeof window === "undefined") return;
  if (recoveryDispatchedForGeneration === authGeneration) return;
  recoveryDispatchedForGeneration = authGeneration;
  const returnTo = `${window.location.pathname}${window.location.search}`;
  window.dispatchEvent(new CustomEvent("aipdv:session-recovery", { detail: { returnTo } }));
}

function advanceAuthGeneration() {
  authGeneration += 1;
  recoveryDispatchedForGeneration = null;
  return authGeneration;
}

function clearAccessTokenFor(generation: number) {
  if (authGeneration === generation) accessToken = null;
}

async function rotateAccessToken(generation = authGeneration): Promise<void> {
  if (generation !== authGeneration || logoutInFlight) {
    throw new PortError("UNAUTHENTICATED", "会话已结束，请重新登录。");
  }
  if (!refreshInFlight || refreshGeneration !== generation) {
    const inFlight = (async () => {
      try {
        const refreshed = unwrap<RefreshTokenData>(await refreshAccessToken({}, { credentials: "include" }));
        if (authGeneration === generation) accessToken = refreshed.data.access_token;
      } catch (error) {
        if (authGeneration === generation) {
          accessToken = null;
          triggerSessionRecovery();
        }
        throw error;
      } finally {
        if (refreshGeneration === generation) {
          refreshInFlight = null;
          refreshGeneration = null;
        }
      }
    })();
    refreshInFlight = inFlight;
    refreshGeneration = generation;
  }
  return refreshInFlight;
}

async function protectedRequest<T>(execute: () => Promise<GeneratedResponse>): Promise<Envelope<T>> {
  const generation = authGeneration;
  try {
    return unwrap<T>(await execute());
  } catch (error) {
    if (!needsRefresh(error)) throw error;
    if (generation !== authGeneration || logoutInFlight) throw error;
    try {
      await rotateAccessToken(generation);
    } catch (refreshError) {
      if (isPortError(refreshError)) throw refreshError;
      throw new PortError("UNAUTHENTICATED", "会话恢复失败，请重新登录。");
    }
    try {
      return unwrap<T>(await execute());
    } catch (retryError) {
      if (needsRefresh(retryError)) {
        clearAccessTokenFor(generation);
        if (authGeneration === generation) triggerSessionRecovery();
      }
      throw retryError;
    }
  }
}

const mapSession = (data: AuthTokenData): SessionView => ({
  user: { id: data.user.id, displayName: data.user.display_name, email: data.user.email },
  expiresAt: new Date(Date.now() + data.expires_in * 1000).toISOString(),
});

const mapStoredSession = (data: SessionData): SessionView => ({
  user: { id: data.user.id, displayName: data.user.display_name, email: data.user.email },
  expiresAt: data.expires_at,
});

const mapProject = (data: ProjectSummary): ProjectSummaryView => ({
  id: data.id,
  name: data.name,
  goal: data.description ?? "",
  workingVersionId: data.working_version_id,
  workingVersionNo: data.working_version_no,
  projectVersion: data.version,
  stage: data.last_module ?? "项目初始化",
  updatedAt: data.updated_at,
});

const mapVersion = (data: ProjectVersionSummary): VersionView => ({
  id: data.id,
  number: data.version_no,
  source: data.parent_version_id ?? null,
  reason: data.creation_reason,
  createdAt: data.created_at,
  isWorking: data.is_working,
});

const mapFile = (data: FileData): FileItemView => ({
  id: data.file.current_version_id ?? data.file.id,
  name: data.file.logical_name,
  progress: 100,
  status: data.current_version?.storage_status === "available" ? "uploaded" : "manual-required",
  relation: null,
});

async function projectOverview(projectId: string, viewedVersionId?: string): Promise<ProjectOverviewView> {
  const project = await protectedRequest<ProjectSummary>(() => getProject(projectId, requestOptions()));
  const selectedId = viewedVersionId ?? project.data.working_version_id;
  const version = await protectedRequest<ProjectVersionSummary>(() => getProjectVersion(selectedId, requestOptions()));
  const summary = mapProject(project.data);
  return {
    ...summary,
    viewedVersionId: version.data.id,
    viewedVersionNo: version.data.version_no,
    isHistory: !version.data.is_working,
    canEdit: version.data.is_working,
    blocker: null,
  };
}

async function sha256(file: File): Promise<string> {
  const bytes = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function uploadTransferError(message: string, status?: number, definitive?: boolean): UploadTransferError {
  const error = new PortError("STORAGE_UNAVAILABLE", message, status) as UploadTransferError;
  error.definitive = definitive;
  return error;
}

function putObject(upload: FileUploadData, file: File, onProgress?: (progress: number) => void): Promise<string | null> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open(upload.http_method, upload.upload_url);
    Object.entries(upload.required_headers).forEach(([name, value]) => request.setRequestHeader(name, value));
    request.upload.onprogress = (event) => { if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100)); };
    request.onload = () => request.status >= 200 && request.status < 300
      ? resolve(request.getResponseHeader("ETag"))
      : reject(uploadTransferError(`对象存储上传失败（HTTP ${request.status}）。`, request.status, true));
    request.onerror = () => reject(uploadTransferError("对象存储连接中断，无法确认对象是否已写入。"));
    request.send(file);
  });
}

function failedUpload(recovery: PendingUploadRecovery, error: unknown, progress = 0, retainRecovery = true): FileItemView {
  return {
    id: recovery.uploadId,
    name: recovery.file.name,
    progress,
    status: "failed",
    relation: null,
    error: error instanceof Error ? error.message : "上传未完成。",
    retryFile: recovery.file,
    pendingUpload: retainRecovery ? recovery : undefined,
  };
}

async function abortKnownIncomplete(recovery: PendingUploadRecovery) {
  await protectedRequest(() => abortFileUpload(recovery.uploadId, { reason: "upload completion explicitly failed" }, { "Idempotency-Key": commandKey() }, requestOptions())).catch(() => undefined);
}

async function reconcileCompletion(recovery: PendingUploadRecovery, etag?: string | null): Promise<FileItemView> {
  const complete = () => protectedRequest<FileData>(() => completeFileUpload(recovery.uploadId, {
    checksum_sha256: recovery.checksumSha256,
    etag,
  }, { "Idempotency-Key": recovery.completeIdempotencyKey }, requestOptions()));

  try {
    return mapFile((await complete()).data);
  } catch (firstError) {
    if (isPortError(firstError)) {
      if (explicitIncompleteCodes.includes(firstError.apiCode as ErrorCode)) {
        await abortKnownIncomplete(recovery);
        return failedUpload(recovery, firstError, 0, false);
      }
      return failedUpload(recovery, firstError);
    }
    try {
      return mapFile((await complete()).data);
    } catch (secondError) {
      try {
        const current = await protectedRequest<FileData>(() => getFile(recovery.storedFileId, requestOptions()));
        if (current.data.current_version?.storage_status === "available") return mapFile(current.data);
      } catch {
        // The completion outcome is still ambiguous; retain the same recovery tuple for a user-initiated retry.
      }
      return failedUpload(recovery, secondError);
    }
  }
}

async function uploadFile(projectId: string, file: File, _scenario?: unknown, onProgress?: (progress: number) => void): Promise<FileItemView> {
  const checksum = await sha256(file);
  const initialized = await protectedRequest<FileUploadData>(() => initFileUpload({
    checksum_sha256: checksum,
    extension: file.name.includes(".") ? file.name.split(".").pop() ?? null : null,
    logical_name: file.name,
    mime_type: file.type || "application/octet-stream",
    project_id: projectId,
    size_bytes: file.size,
  }, { "Idempotency-Key": commandKey() }, requestOptions()));
  const recovery: PendingUploadRecovery = {
    uploadId: initialized.data.upload_id,
    storedFileId: initialized.data.stored_file_id,
    checksumSha256: checksum,
    completeIdempotencyKey: commandKey(),
    file,
  };
  try {
    const etag = await putObject(initialized.data, file, onProgress);
    return reconcileCompletion(recovery, etag);
  } catch (error) {
    if ((error as UploadTransferError).definitive) {
      await abortKnownIncomplete(recovery);
      return failedUpload(recovery, error, 0, false);
    }
    return failedUpload(recovery, error);
  }
}

export const realApi: FrontendApi = {
  identity: {
    async login(input) {
      if (logoutInFlight) await logoutInFlight.catch(() => undefined);
      const priorRefresh = refreshInFlight;
      const generation = advanceAuthGeneration();
      accessToken = null;
      await priorRefresh?.catch(() => undefined);
      const result = unwrap<AuthTokenData>(await login({ email: input.email, password: input.password }, { credentials: "include" }));
      if (authGeneration === generation) accessToken = result.data.access_token;
      return mapSession(result.data);
    },
    async register(input) {
      if (logoutInFlight) await logoutInFlight.catch(() => undefined);
      const priorRefresh = refreshInFlight;
      const generation = advanceAuthGeneration();
      accessToken = null;
      await priorRefresh?.catch(() => undefined);
      const result = unwrap<AuthTokenData>(await register({ display_name: input.displayName, email: input.email, password: input.password }, { credentials: "include" }));
      if (authGeneration === generation) accessToken = result.data.access_token;
      return mapSession(result.data);
    },
    async refresh() {
      const generation = authGeneration;
      await rotateAccessToken(generation);
      try {
        const session = unwrap<SessionData>(await getSession(requestOptions()));
        return mapStoredSession(session.data);
      } catch (error) {
        clearAccessTokenFor(generation);
        if (authGeneration === generation) triggerSessionRecovery();
        throw error;
      }
    },
    async logout() {
      if (logoutInFlight) return logoutInFlight;
      const priorRefresh = refreshInFlight;
      advanceAuthGeneration();
      const sequence = ++logoutSequence;
      accessToken = null;
      const inFlight = (async () => {
        try {
          await priorRefresh?.catch(() => undefined);
          unwrap(await logout({}, requestOptions()));
        } finally {
          if (logoutSequence === sequence) logoutInFlight = null;
        }
      })();
      logoutInFlight = inFlight;
      return inFlight;
    },
  },
  projects: {
    async list() {
      const result = await protectedRequest<ProjectListData>(() => listProjects(undefined, requestOptions()));
      return result.data.items.map(mapProject);
    },
    async create(input) {
      const scope = `create-project:${JSON.stringify(input)}`;
      const result = await protectedRequest<CreateProjectData>(() => createProject({ name: input.name, description: input.goal, start_mode: input.startMode }, { "Idempotency-Key": retryKey(scope) }, requestOptions()));
      retryKeys.delete(scope);
      return { projectId: result.data.project.id, workingVersionId: result.data.working_version_id };
    },
    overview: projectOverview,
    async versions(projectId) {
      const result = await protectedRequest<ProjectVersionListData>(() => listProjectVersions(projectId, undefined, requestOptions()));
      return result.data.items.map(mapVersion);
    },
    async setWorking(projectId, versionId, expectedProjectVersion) {
      const scope = `set-working:${projectId}:${versionId}:${expectedProjectVersion}`;
      const result = await protectedRequest<WorkingVersionChangeData>(() => setWorkingProjectVersion(projectId, versionId, {
        expected_project_version: expectedProjectVersion,
        reason: "用户在版本详情页确认设置工作版本",
      }, { "Idempotency-Key": retryKey(scope) }, requestOptions()));
      retryKeys.delete(scope);
      return projectOverview(projectId, result.data.current.id);
    },
    async derive() {
      throw new PortError("CONTRACT_UNAVAILABLE", "派生版本的 change_type 与 inheritance_choices 允许值尚未冻结，真实模式已阻止提交。");
    },
  },
  files: {
    async list() { return []; },
    upload: uploadFile,
    async retry(projectId, item) {
      if (item.pendingUpload) return reconcileCompletion(item.pendingUpload);
      if (!item.retryFile) throw new PortError("FAILED", "原始文件句柄已失效，请重新选择文件。");
      return uploadFile(projectId, item.retryFile);
    },
    async relate() {
      throw new PortError("CONTRACT_UNAVAILABLE", "文件关联对象类型与关系类型允许值尚未冻结，真实模式已阻止提交。");
    },
  },
  health: {
    async get() {
      const response = await getApiHealth({ credentials: "include" });
      const result = unwrap<ApiResponseHealthData["data"]>(response);
      return { ...result.data, traceId: result.trace_id };
    },
  },
};

export function __resetRealAdapterForTests() {
  accessToken = null;
  refreshInFlight = null;
  refreshGeneration = null;
  logoutInFlight = null;
  logoutSequence = 0;
  authGeneration = 0;
  recoveryDispatchedForGeneration = null;
  retryKeys.clear();
}
