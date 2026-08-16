import {
  abortFileUpload,
  completeFileUpload,
  confirmRequirementVersion,
  createProject,
  createAiTask,
  createRequirement,
  formalizeAiResult,
  getAiResult,
  getAiTask,
  getApiHealth,
  getFile,
  getProject,
  getProjectVersion,
  getSession,
  initFileUpload,
  listProjects,
  listProjectVersions,
  listRequirements,
  login,
  logout,
  refreshAccessToken,
  register,
  setWorkingProjectVersion,
  setRequirementClarificationMode,
  submitRequirementClarificationAnswers,
  reviseRequirementVersion,
  getRequirement,
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
  RequirementData,
  RequirementListData,
  RequirementSummary,
  RequirementVersion,
  AiTaskSummary,
  AiResult,
  AiResultAssessment,
  AiResultContentQuestionsItem,
  ClarificationAnswerData,
  ClarificationAssessment,
  ClarificationQuestion,
  ConfirmRequirementData,
  FormalizeAiResultData,
  RequirementBaseline,
  RequirementContent,
  SourceRef,
  ReviseRequirementVersionRequest,
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
  AiPort,
  AiResultView,
  AiTaskView,
  ClarificationQuestionView,
  CreateAiTaskInput,
  CreateRequirementInput,
  FormalizeAiResultInput,
  ConfirmRequirementVersionInput,
  RequirementAssessmentView,
  RequirementBaselineView,
  RequirementContentView,
  RequirementDimensionKey,
  RequirementPort,
  RequirementSummaryView,
  RequirementVersionView,
  RequirementView,
  ReviseRequirementVersionInput,
  SetClarificationModeInput,
  SourceRefView,
  SubmitClarificationAnswersInput,
} from "./ports";
import { PortError } from "./ports";
import { createClientId } from "../client-id";

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

const commandKey = () => `web-${createClientId()}`;
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

const mapSourceRef = (source: SourceRef): SourceRefView => ({
  sourceId: source.source_id,
  sourceVersionId: source.source_version_id,
  sourceType: source.source_type,
  label: source.label,
  contentHash: source.content_hash,
});

const dimensionKeys: RequirementDimensionKey[] = ["goal", "users_and_roles", "usage_scenarios", "functional_scope", "business_rules", "exception_cases", "permission_requirements", "acceptance_criteria"];

function mapBaseline(baseline: RequirementBaseline): RequirementBaselineView {
  const dimensions = Object.fromEntries(dimensionKeys.map((key) => {
    const value = baseline.dimensions[key];
    return [key, {
      confirmedFacts: value.confirmed_facts,
      sourceRefs: value.source_refs.map(mapSourceRef),
      deferredItems: value.deferred_items,
      notApplicableItems: value.not_applicable_items,
    }];
  })) as RequirementBaselineView["dimensions"];
  return { dimensions, assumptions: baseline.assumptions, unresolvedItems: baseline.unresolved_items };
}

const mapQuestion = (question: ClarificationQuestion): ClarificationQuestionView => ({
  questionId: question.question_id,
  dimension: question.dimension,
  questionText: question.question_text,
  reason: question.reason,
  sourceRefs: question.source_refs.map(mapSourceRef),
});

function mapAssessment(assessment: ClarificationAssessment | null): RequirementAssessmentView | null {
  if (!assessment) return null;
  const dimension = (key: RequirementDimensionKey): RequirementAssessmentView["dimensions"][RequirementDimensionKey] => {
    const value = assessment.dimensions[key];
    return { status: value.status, missingItems: value.missing_items, reasons: [], sourceRefs: value.source_refs.map(mapSourceRef) };
  };
  const dimensions: RequirementAssessmentView["dimensions"] = {
    goal: dimension("goal"),
    users_and_roles: dimension("users_and_roles"),
    usage_scenarios: dimension("usage_scenarios"),
    functional_scope: dimension("functional_scope"),
    business_rules: dimension("business_rules"),
    exception_cases: dimension("exception_cases"),
    permission_requirements: dimension("permission_requirements"),
    acceptance_criteria: dimension("acceptance_criteria"),
  };
  return {
    aiResultId: assessment.ai_result_id,
    assessmentVersion: assessment.assessment_version,
    complexityBand: assessment.complexity_band,
    reasons: [assessment.complexity_reason],
    missingItems: assessment.missing_dimensions,
    dimensions,
    missingDimensions: assessment.missing_dimensions,
    recommendedMode: assessment.recommended_mode,
    sourceRefs: assessment.source_refs.map(mapSourceRef),
  };
}

function mapContent(content: RequirementContent): RequirementContentView {
  const clarification = content.clarification;
  return {
    rawInput: content.raw_input,
    rawInputRef: mapSourceRef(content.raw_input_ref),
    clarification: {
      mode: clarification.mode,
      continueDeepConfirmed: clarification.continue_deep_confirmed ?? false,
      assessmentRef: clarification.assessment_ref ? { objectType: clarification.assessment_ref.object_type, objectId: clarification.assessment_ref.object_id, objectVersionId: clarification.assessment_ref.object_version_id } : null,
      assessmentSummary: clarification.assessment_summary,
      assessment: mapAssessment(clarification.assessment),
      rounds: clarification.rounds.map((round) => ({ roundNo: round.round_no, aiTaskId: round.ai_task_id, aiResultId: round.ai_result_id, questions: round.questions.map(mapQuestion), answers: round.answers.map((answer) => ({ questionId: answer.question_id, answer: answer.answer })) })),
      finishReason: clarification.finish_reason,
    },
    baseline: mapBaseline(content.baseline),
  };
}

const serializeSourceRef = (source: SourceRefView): SourceRef => ({
  source_id: source.sourceId,
  source_version_id: source.sourceVersionId,
  source_type: source.sourceType,
  label: source.label,
  content_hash: source.contentHash,
});

const serializeQuestion = (question: ClarificationQuestionView): ClarificationQuestion => ({
  question_id: question.questionId,
  dimension: question.dimension,
  question_text: question.questionText,
  reason: question.reason,
  source_refs: question.sourceRefs.map(serializeSourceRef),
});

function serializeAssessment(assessment: RequirementAssessmentView): ClarificationAssessment {
  const dimension = (key: RequirementDimensionKey) => ({
    status: assessment.dimensions[key].status,
    missing_items: assessment.dimensions[key].missingItems,
    source_refs: assessment.dimensions[key].sourceRefs.map(serializeSourceRef),
  });
  const dimensions: ClarificationAssessment["dimensions"] = {
    goal: dimension("goal"),
    users_and_roles: dimension("users_and_roles"),
    usage_scenarios: dimension("usage_scenarios"),
    functional_scope: dimension("functional_scope"),
    business_rules: dimension("business_rules"),
    exception_cases: dimension("exception_cases"),
    permission_requirements: dimension("permission_requirements"),
    acceptance_criteria: dimension("acceptance_criteria"),
  };
  return {
    ai_result_id: assessment.aiResultId,
    assessment_version: assessment.assessmentVersion,
    complexity_band: assessment.complexityBand,
    complexity_reason: assessment.reasons.join("；") || "已完成结构化完整性评估",
    dimensions,
    missing_dimensions: assessment.missingDimensions,
    recommended_mode: assessment.recommendedMode,
    source_refs: assessment.sourceRefs.map(serializeSourceRef),
  };
}

function serializeBaseline(baseline: RequirementBaselineView): RequirementBaseline {
  const dimensions = Object.fromEntries(dimensionKeys.map((key) => [key, {
    confirmed_facts: baseline.dimensions[key].confirmedFacts,
    source_refs: baseline.dimensions[key].sourceRefs.map(serializeSourceRef),
    deferred_items: baseline.dimensions[key].deferredItems,
    not_applicable_items: baseline.dimensions[key].notApplicableItems,
  }])) as RequirementBaseline["dimensions"];
  return { dimensions, assumptions: baseline.assumptions, unresolved_items: baseline.unresolvedItems };
}

function serializeContent(content: RequirementContentView): RequirementContent {
  return {
    raw_input: content.rawInput,
    raw_input_ref: serializeSourceRef(content.rawInputRef),
    clarification: {
      mode: content.clarification.mode,
      continue_deep_confirmed: content.clarification.continueDeepConfirmed,
      assessment_ref: content.clarification.assessmentRef ? {
        object_type: content.clarification.assessmentRef.objectType,
        object_id: content.clarification.assessmentRef.objectId,
        object_version_id: content.clarification.assessmentRef.objectVersionId,
      } : null,
      assessment_summary: content.clarification.assessmentSummary,
      assessment: content.clarification.assessment ? serializeAssessment(content.clarification.assessment) : null,
      rounds: content.clarification.rounds.map((round) => ({
        round_no: round.roundNo,
        ai_task_id: round.aiTaskId,
        ai_result_id: round.aiResultId,
        questions: round.questions.map(serializeQuestion),
        answers: round.answers.map((answer) => ({ question_id: answer.questionId, answer: answer.answer })),
      })),
      finish_reason: content.clarification.finishReason,
    },
    baseline: serializeBaseline(content.baseline),
  };
}

const mapRequirementVersion = (data: RequirementVersion): RequirementVersionView => ({
  id: data.id,
  requirementId: data.requirement_id,
  versionNo: data.version_no,
  contentHash: data.content_hash,
  contentFormat: data.content_format,
  content: mapContent(data.content_json),
  confirmationStatus: data.confirmation_status,
  isEffective: data.is_effective,
  sourceVersionId: data.source_version_id,
  createdFromAiResultId: data.created_from_ai_result_id,
  unresolvedCount: data.unresolved_count,
  riskAcceptances: data.risk_acceptances.map((risk) => ({ missingItemCode: risk.missing_item_code, impact: risk.impact, reason: risk.reason })),
});

const mapRequirementSummary = (data: RequirementSummary): RequirementSummaryView => ({
  id: data.id,
  title: data.title,
  projectVersionId: data.project_version_id,
  status: data.status,
  sourceType: data.source_type,
  priority: data.priority,
  currentVersionId: data.current_version_id,
  effectiveVersionId: data.effective_version_id,
  version: data.version,
  updatedAt: data.updated_at,
});

const mapRequirementData = (data: RequirementData): RequirementView => ({
  requirement: mapRequirementSummary(data.requirement),
  currentVersion: data.current_version ? mapRequirementVersion(data.current_version) : null,
  effectiveVersion: data.effective_version ? mapRequirementVersion(data.effective_version) : null,
  canEdit: data.permissions.allowed_actions.some((action) => ["edit", "revise", "confirm", "set_clarification_mode"].includes(action)),
  allowedActions: data.permissions.allowed_actions,
});

function mapTask(data: AiTaskSummary): AiTaskView {
  return {
    taskId: data.task_id,
    taskPublicId: data.task_public_id,
    taskType: data.task_type,
    status: data.status,
    targetSnapshotHash: data.target_snapshot_hash,
    pollUrl: data.poll_url,
    eventsUrl: data.events_url,
    missingItems: data.missing_items,
    createdByUserId: data.created_by_user_id,
    queuedAt: data.queued_at,
    resultRefs: data.result_refs.map((reference) => ({ resultId: reference.result_id, status: reference.status, targetSnapshotHash: reference.target_snapshot_hash })),
  };
}

function mapAiAssessment(assessment: AiResultAssessment | null, data: AiResult): RequirementAssessmentView | null {
  if (!assessment) return null;
  const dimension = (key: RequirementDimensionKey) => {
    const value = assessment.dimension_completeness[key];
    return { status: value.status, missingItems: value.missing_items, reasons: value.reasons, sourceRefs: value.source_refs.map(mapSourceRef) };
  };
  const dimensions: RequirementAssessmentView["dimensions"] = {
    goal: dimension("goal"),
    users_and_roles: dimension("users_and_roles"),
    usage_scenarios: dimension("usage_scenarios"),
    functional_scope: dimension("functional_scope"),
    business_rules: dimension("business_rules"),
    exception_cases: dimension("exception_cases"),
    permission_requirements: dimension("permission_requirements"),
    acceptance_criteria: dimension("acceptance_criteria"),
  };
  return {
    aiResultId: data.id,
    assessmentVersion: data.schema_version,
    complexityBand: assessment.complexity_band,
    reasons: assessment.reasons,
    missingItems: assessment.missing_items,
    dimensions,
    missingDimensions: dimensionKeys.filter((key) => assessment.dimension_completeness[key].status === "missing"),
    recommendedMode: assessment.recommended_mode,
    sourceRefs: assessment.source_refs.map(mapSourceRef),
  };
}

function isAiQuestionArray(value: unknown): value is AiResultContentQuestionsItem[] {
  return Array.isArray(value) && value.every((question) => Boolean(
    question && typeof question === "object" && "question_id" in question && "source_refs" in question,
  ));
}

function mapAiQuestion(question: AiResultContentQuestionsItem): ClarificationQuestionView {
  return {
    questionId: question.question_id,
    dimension: question.dimension,
    questionText: question.question_text,
    reason: question.reason,
    sourceRefs: question.source_refs.map(mapSourceRef),
  };
}

function mapCapabilitySummary(summary: AiResult["capability_summary"]): AiResultView["capabilitySummary"] {
  return {
    truthLabel: summary.truth_label === "FORMAL_MOCK" ? "FORMAL_MOCK" : null,
    providerCode: typeof summary.provider_code === "string" ? summary.provider_code : null,
    modelCode: typeof summary.model_code === "string" ? summary.model_code : null,
  };
}

function mapResult(data: AiResult): AiResultView {
  const content = data.content_json;
  const questions = content && isAiQuestionArray(content.questions)
    ? content.questions.map(mapAiQuestion)
    : [];
  return {
    id: data.id,
    taskPublicId: data.task_public_id,
    taskType: data.task_type,
    targetSnapshotHash: data.target_snapshot_hash,
    mode: data.mode,
    roundNo: data.round_no,
    resultKind: data.result_kind,
    status: data.status,
    content: content ? { assessment: mapAiAssessment(content.assessment, data), questions, baseline: content.baseline ? mapBaseline(content.baseline) : null } : null,
    convergence: { shouldFinish: data.convergence.should_finish, finishReason: data.convergence.finish_reason, nextRoundNo: data.convergence.next_round_no },
    quality: { formatStatus: data.quality_summary.format_status, traceabilityStatus: data.quality_summary.traceability_status, safetyStatus: data.quality_summary.safety_status, requiredItemsMet: data.quality_summary.required_items_met, requiredItemsTotal: data.quality_summary.required_items_total, majorError: data.quality_summary.major_error, blockerCodes: data.quality_summary.blocker_codes },
    capabilitySummary: mapCapabilitySummary(data.capability_summary),
  };
}

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
  requirements: {
    async list(projectVersionId: string) {
      const result = await protectedRequest<RequirementListData>(() => listRequirements(projectVersionId, undefined, requestOptions()));
      return result.data.items.map(mapRequirementSummary);
    },
    async get(requirementId: string) {
      const result = await protectedRequest<RequirementData>(() => getRequirement(requirementId, requestOptions()));
      return mapRequirementData(result.data);
    },
    async create(projectVersionId: string, input: CreateRequirementInput) {
      const result = await protectedRequest<RequirementData>(() => createRequirement(projectVersionId, {
        title: input.title,
        raw_input: input.rawInput,
        source_refs: (input.sourceRefs ?? []).map((source) => ({ source_id: source.sourceId, source_version_id: source.sourceVersionId, source_type: source.sourceType, label: source.label, content_hash: source.contentHash })),
      }, { "Idempotency-Key": commandKey() }, requestOptions()));
      return mapRequirementData(result.data);
    },
    async setClarificationMode(versionId: string, input: SetClarificationModeInput) {
      const result = await protectedRequest<RequirementVersion>(() => setRequirementClarificationMode(versionId, { expected_version: input.expectedVersion, mode: input.mode, reason: input.reason ?? null }, { "Idempotency-Key": commandKey() }, requestOptions()));
      return mapRequirementVersion(result.data);
    },
    async submitClarificationAnswers(versionId: string, input: SubmitClarificationAnswersInput) {
      const result = await protectedRequest<ClarificationAnswerData>(() => submitRequirementClarificationAnswers(versionId, {
        expected_version: input.expectedVersion,
        round_no: input.roundNo,
        answers: input.answers.map((answer) => ({ question_id: answer.questionId, answer: answer.answer })),
        continue_deep_confirmed: input.continueDeepConfirmed,
        finish_now: input.finishNow,
      }, { "Idempotency-Key": commandKey() }, requestOptions()));
      return { version: mapRequirementVersion(result.data.requirement_version), baselineCandidateRef: result.data.baseline_candidate_ref?.object_id ?? null };
    },
    async revise(versionId: string, input: ReviseRequirementVersionInput) {
      const body: ReviseRequirementVersionRequest = {
        expected_version: input.expectedVersion,
        title: input.title,
        content_json: input.content ? serializeContent(input.content) : undefined,
        risk_acceptances: input.riskAcceptances?.map((risk) => ({ missing_item_code: risk.missingItemCode, impact: risk.impact, reason: risk.reason })),
      };
      const result = await protectedRequest<RequirementVersion>(() => reviseRequirementVersion(versionId, body, requestOptions()));
      return mapRequirementVersion(result.data);
    },
    async confirm(versionId: string, input: ConfirmRequirementVersionInput) {
      const result = await protectedRequest<ConfirmRequirementData>(() => confirmRequirementVersion(versionId, { expected_version: input.expectedVersion, risk_acceptances: (input.riskAcceptances ?? []).map((risk) => ({ missing_item_code: risk.missingItemCode, impact: risk.impact, reason: risk.reason })) }, { "Idempotency-Key": commandKey() }, requestOptions()));
      return { version: mapRequirementVersion(result.data.effective_version), gateResult: result.data.gate_result };
    },
  } satisfies RequirementPort,
  ai: {
    async createTask(input: CreateAiTaskInput) {
      const result = await protectedRequest<AiTaskSummary>(() => createAiTask({
        task_type: "requirement.clarify",
        target: { object_type: "requirement", object_id: input.requirementId, object_version_id: input.versionId },
        source_ref_ids: input.sourceRefIds,
        user_instruction: input.userInstruction ?? null,
        risk_acceptances: input.riskAcceptances?.map((risk) => ({ missing_item_code: risk.missingItemCode, impact: risk.impact, reason: risk.reason })),
      }, { "Idempotency-Key": commandKey() }, requestOptions()));
      return mapTask(result.data);
    },
    async getTask(taskId: string) {
      const result = await protectedRequest<AiTaskSummary>(() => getAiTask(taskId, requestOptions()));
      return mapTask(result.data);
    },
    async getResult(resultId: string) {
      const result = await protectedRequest<AiResult>(() => getAiResult(resultId, requestOptions()));
      return mapResult(result.data);
    },
    async formalizeBaseline(resultId: string, input: FormalizeAiResultInput) {
      const modifiedContent = input.adoption === "modified_adopt" && input.modificationIntensity === "minor" ? input.modifiedContent : undefined;
      const command = modifiedContent ? {
        adoption: "modified_adopt" as const,
        modification_intensity: "minor" as const,
        modified_content_json: { baseline: serializeBaseline(modifiedContent.baseline) },
        expected_version: input.expectedVersion,
        target_object_id: input.requirementId,
        target_object_type: "requirement" as const,
        target_snapshot_hash: input.targetSnapshotHash,
      } : {
        adoption: "adopt" as const,
        modification_intensity: "none" as const,
        modified_content_json: null,
        expected_version: input.expectedVersion,
        target_object_id: input.requirementId,
        target_object_type: "requirement" as const,
        target_snapshot_hash: input.targetSnapshotHash,
      };
      const result = await protectedRequest<FormalizeAiResultData>(() => formalizeAiResult(resultId, command, { "Idempotency-Key": commandKey() }, requestOptions()));
      const version = result.data.artifact_version_ref;
      if (!version) throw new PortError("FAILED", "Baseline 正式化未返回 Requirement Version。");
      return { id: version.id, versionNo: version.version_no, status: version.status, contentHash: version.content_hash, createdAt: version.created_at };
    },
  } satisfies AiPort,
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
