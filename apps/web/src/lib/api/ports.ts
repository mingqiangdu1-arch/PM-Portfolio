/** UI-facing view models, not handwritten OpenAPI DTOs. Generated schema types
 * will be mapped into this boundary only after Review freezes the contract. */
export type Scenario = "ready" | "loading" | "empty" | "filtered-empty" | "failure" | "forbidden" | "readonly" | "conflict";
export interface UserView { id: string; displayName: string; email: string }
export interface SessionView { user: UserView; expiresAt: string }
export interface AuthCredentials { email: string; password: string }
export interface RegistrationInput extends AuthCredentials { displayName: string }
export type ProjectRole = "owner" | "reviewer" | "implementer" | "tester";
export interface ProjectCapabilities { role: ProjectRole | null; canPlanWrite: boolean; canSetEffective: boolean; canConfirmationCreate: boolean; canConfirmationUpdate: boolean; canConfirm: boolean; canTestRecordWrite: boolean; readOnly: boolean }
export interface ProjectSummaryView { id: string; name: string; goal: string; workingVersionId: string; workingVersionNo: string; projectVersion: number; stage: string; updatedAt: string; roles?: ProjectRole[]; capabilities?: ProjectCapabilities }
export interface ProjectOverviewView extends ProjectSummaryView { viewedVersionId: string; viewedVersionNo: string; isHistory: boolean; canEdit: boolean; blocker: string | null; roles?: ProjectRole[]; capabilities?: ProjectCapabilities }
export interface VersionView { id: string; number: string; source: string | null; reason: string; createdAt: string; isWorking: boolean }
export interface CreateProjectInput { name: string; goal: string; startMode: "new" | "import" }
export type VersionChangeType = "bug_fix" | "optimization" | "scope_change";
export interface DeriveVersionInput {
  sourceVersionId: string;
  sourceIssueId?: string | null;
  changeType?: VersionChangeType;
  reason: string;
  inheritContext: boolean;
  inheritanceChoices?: { requirements: boolean; prd: boolean; implementationPlan: boolean };
  expectedProjectVersion: number;
}
export interface PendingUploadRecovery { uploadId: string; storedFileId: string; checksumSha256: string; completeIdempotencyKey: string; file: File }
export interface FileItemView { id: string; name: string; progress: number; status: "uploading" | "uploaded" | "failed" | "parsing" | "manual-required"; relation: string | null; error?: string; retryFile?: File; pendingUpload?: PendingUploadRecovery }
export interface HealthView { status: string; service: string; environment: string; release: string; traceId: string }
export interface IdentityPort { login(input: AuthCredentials): Promise<SessionView>; register(input: RegistrationInput): Promise<SessionView>; refresh(): Promise<SessionView>; logout(): Promise<void> }
export interface ProjectPort { list(scenario?: Scenario): Promise<ProjectSummaryView[]>; create(input: CreateProjectInput, scenario?: Scenario): Promise<{ projectId: string; workingVersionId: string }>; overview(projectId: string, viewedVersionId?: string): Promise<ProjectOverviewView>; versions(projectId: string): Promise<VersionView[]>; setWorking(projectId: string, versionId: string, expectedProjectVersion: number, scenario?: Scenario): Promise<ProjectOverviewView>; derive(projectId: string, input: DeriveVersionInput, scenario?: Scenario): Promise<VersionView> }
export interface FilePort { list(projectId: string): Promise<FileItemView[]>; upload(projectId: string, file: File, scenario?: Scenario, onProgress?: (progress: number) => void): Promise<FileItemView>; retry(projectId: string, item: FileItemView): Promise<FileItemView>; relate(projectId: string, fileId: string, relation: string): Promise<FileItemView> }
export interface HealthPort { get(): Promise<HealthView> }
export interface PlanItemView { key: string; description: string }
export interface PlanContentView {
  schemaVersion: "implementation_plan.mvp3.v1";
  features: PlanItemView[];
  businessRules: PlanItemView[];
  stateRequirements: PlanItemView[];
  exceptions: PlanItemView[];
  interactions: PlanItemView[];
  dependencies: PlanItemView[];
  acceptanceScope: PlanItemView[];
}
export interface ReadinessView {
  schemaVersion: "implementation_confirmation.readiness.mvp3.v1";
  scopeStatus: "ready" | "not_ready";
  implementationStatus: "ready" | "not_ready";
  configurationStatus: "ready" | "not_ready" | "not_applicable";
  dataChangeStatus: "ready" | "not_ready" | "not_applicable";
  knownBlockers: string[];
}
export interface ImplementationPlanVersionView {
  id: string; implementationPlanId: string; sourceVersionId: string | null; versionNo: string; reviewId: string;
  content: PlanContentView; contentHash: string; changeNote: string; isEffective: boolean; createdBy: string | null; createdAt: string;
}
export type PlanConfirmationState = "confirmed" | "needs_confirmation" | "needs_reconfirmation" | "not_ready";
export interface ImplementationPlanView {
  id: string; projectVersionId: string; sourcePrdVersionId: string; sourceDesignReviewId: string; name: string;
  status: "draft" | "active"; currentVersionId: string | null; effectiveVersionId: string | null; rowVersion: number;
  confirmationState: PlanConfirmationState; versions: ImplementationPlanVersionView[];
}
export interface ConfirmationRoundView {
  id: string; implementationPlanId: string; planVersionId: string; sourceRoundId: string | null; roundNo: number;
  status: "draft" | "confirmed" | "superseded"; confirmStatus: "confirmed" | null; implementationSummary: string;
  readiness: ReadinessView; rowVersion: number; isEffective: boolean; confirmedBy: string | null; confirmedAt: string | null; supersededAt: string | null;
}
export interface CreateImplementationPlanInput { name: string; sourcePrdVersionId: string; sourceDesignReviewId: string }
export interface SaveImplementationPlanVersionInput { expectedVersion: number; content: PlanContentView; changeNote: string }
export interface CreateConfirmationRoundInput { planVersionId: string; implementationSummary: string; readiness: ReadinessView }
export interface UpdateConfirmationRoundDraftInput extends CreateConfirmationRoundInput { expectedVersion: number }
export interface ImplementationPlanPort {
  list(projectVersionId: string): Promise<ImplementationPlanView[]>;
  create(projectVersionId: string, input: CreateImplementationPlanInput): Promise<ImplementationPlanView>;
  get(planId: string): Promise<ImplementationPlanView>;
  saveVersion(planId: string, input: SaveImplementationPlanVersionInput): Promise<{ version: ImplementationPlanVersionView; planRowVersion: number }>;
  setEffective(planVersionId: string, expectedVersion: number): Promise<ImplementationPlanView>;
}
export interface ConfirmationRoundPort {
  list(planId: string): Promise<ConfirmationRoundView[]>;
  create(planId: string, input: CreateConfirmationRoundInput): Promise<ConfirmationRoundView>;
  get(roundId: string): Promise<ConfirmationRoundView>;
  updateDraft(roundId: string, input: UpdateConfirmationRoundDraftInput): Promise<ConfirmationRoundView>;
  confirm(roundId: string, expectedVersion: number): Promise<ConfirmationRoundView>;
}
export type TestRecordResultStatus = "success" | "failed" | "partial";
export type TestRecordStatus = "draft" | "submitted";
export interface TestEnvironmentView { name: string; preconditions: string[] }
export interface TestRecordView {
  id: string; projectId: string; projectVersionId: string; confirmationRoundId: string; title: string; scope: string; environment: TestEnvironmentView;
  steps: string[]; expectedResult: string; actualResult: string; resultStatus: TestRecordResultStatus;
  testerId: string; status: TestRecordStatus; submittedAt: string | null; rowVersion: number;
  noIssueConclusion: boolean; testType: "manual"; createdAt: string; updatedAt: string;
}
export interface CreateTestRecordInput {
  title: string; scope: string; environment: TestEnvironmentView; steps: string[];
  expectedResult: string; actualResult: string; resultStatus: TestRecordResultStatus;
}
export interface UpdateTestRecordInput extends Partial<Omit<CreateTestRecordInput, "title">> { expectedVersion: number }
export interface TestRecordPort {
  list(roundId: string): Promise<TestRecordView[]>;
  create(roundId: string, input: CreateTestRecordInput): Promise<TestRecordView>;
  get(recordId: string): Promise<TestRecordView>;
  update(recordId: string, input: UpdateTestRecordInput): Promise<TestRecordView>;
  submit(recordId: string, expectedVersion: number): Promise<TestRecordView>;
  concludeNoIssue(recordId: string, expectedVersion: number): Promise<TestRecordView>;
}
export type IssueType = "defect" | "feedback" | "data_anomaly" | "optimization";
export type IssuePriority = "low" | "medium" | "high" | "urgent";
export type IssueSeverity = "low" | "medium" | "high" | "critical";
export type IssueStatus = "open_needs_disposition" | "routed_current_fix" | "routed_new_version" | "deferred" | "rejected";
export type IssueDispositionType = "current_version_fix" | "derive_new_version" | "defer" | "reject";
export interface BugDetailView { reproduceSteps: string; expectedResult: string; actualResult: string; environment: Record<string, unknown> | null }
export interface OptimizationDetailView { problemEvidence: string; hypothesis: string; expectedOutcome: string; impactScope: string; needNewVersion: boolean }
export interface IssueDispositionView { id: string; sequenceNo: number; dispositionType: IssueDispositionType; reason: string; targetProjectVersionId: string | null; responsibleUserId: string; decidedBy: string; decidedAt: string }
export interface IssueView {
  id: string; projectVersionId: string; testRecordId: string | null; sourceType: "test_record"; issueType: IssueType;
  title: string; description: string; priority: IssuePriority; severity: IssueSeverity; status: IssueStatus;
  assigneeId: string | null; rowVersion: number; bugDetail: BugDetailView | null;
  optimizationDetail: OptimizationDetailView | null; dispositions: IssueDispositionView[];
  createdAt: string; updatedAt: string;
}
export interface CreateIssueInput {
  testRecordId: string; issueType: IssueType; title: string; description: string; priority: IssuePriority;
  severity: IssueSeverity; assigneeId: string | null; bugDetail: BugDetailView | null;
  optimizationDetail: OptimizationDetailView | null;
}
export interface UpdateIssueInput extends Partial<Omit<CreateIssueInput, "testRecordId" | "issueType">> { expectedVersion: number }
export interface IssuePort {
  list(projectVersionId: string): Promise<IssueView[]>;
  create(projectVersionId: string, input: CreateIssueInput): Promise<IssueView>;
  get(issueId: string): Promise<IssueView>;
  update(issueId: string, input: UpdateIssueInput): Promise<IssueView>;
  dispose(issueId: string, expectedVersion: number, dispositionType: Exclude<IssueDispositionType, "derive_new_version">, reason: string, responsibleUserId: string): Promise<IssueView>;
}
export interface FrontendApi { identity: IdentityPort; projects: ProjectPort; files: FilePort; health: HealthPort; requirements: RequirementPort; prds: PrdPort; ai: AiPort; implementationPlans: ImplementationPlanPort; confirmationRounds: ConfirmationRoundPort; testRecords: TestRecordPort; issues: IssuePort }
export const capabilitiesForRoles = (roles: ProjectRole[] = []): ProjectCapabilities => {
  const role = roles.includes("owner") ? "owner" : roles.includes("implementer") ? "implementer" : roles[0] ?? null;
  return { role, canPlanWrite: role === "owner", canSetEffective: role === "owner", canConfirmationCreate: role === "owner" || role === "implementer", canConfirmationUpdate: role === "owner" || role === "implementer", canConfirm: role === "owner", canTestRecordWrite: roles.includes("owner") || roles.includes("tester"), readOnly: role !== "owner" && role !== "implementer" };
};
export type FrontendErrorCategory = "UNAUTHENTICATED" | "FORBIDDEN" | "CONFLICT" | "RATE_LIMITED" | "STORAGE_UNAVAILABLE" | "CONTRACT_UNAVAILABLE" | "FAILED";
import type { ErrorCode, Mvp2ErrorCode, Mvp3ErrorCode, Sprint2ErrorCode } from "./generated/models";
import type {
  AiResultStatus,
  AiTaskStatus,
  ClarificationMode,
  CompletenessStatus,
  ComplexityBand,
  FinishReason,
  RequirementDimension,
  RequirementPriority,
  RequirementSourceType,
  RequirementStatus,
  VersionConfirmationStatus,
} from "./generated/models";
export class PortError extends Error {
  constructor(
    public readonly category: FrontendErrorCategory,
    message: string,
    public readonly status?: number,
    public readonly traceId?: string,
    public readonly details: unknown[] = [],
    public readonly apiCode?: ErrorCode | Sprint2ErrorCode | Mvp2ErrorCode | Mvp3ErrorCode,
  ) { super(traceId ? `${message} Trace: ${traceId}` : message); this.name = "PortError"; }
}

export type RequirementDimensionKey = RequirementDimension;
export type ClarificationModeValue = ClarificationMode;
export type RequirementStatusValue = RequirementStatus;
export type RequirementPriorityValue = RequirementPriority;
export type RequirementSourceTypeValue = RequirementSourceType;
export type VersionConfirmationStatusValue = VersionConfirmationStatus;

export interface SourceRefView {
  sourceId: string;
  sourceVersionId: string | null;
  sourceType: string;
  label: string;
  contentHash: string;
}

export interface RequirementDimensionStatusView {
  status: CompletenessStatus;
  missingItems: string[];
  reasons: string[];
  sourceRefs: SourceRefView[];
}

export interface RequirementBaselineDimensionView {
  confirmedFacts: string[];
  sourceRefs: SourceRefView[];
  deferredItems: string[];
  notApplicableItems: string[];
}

export type RequirementBaselineDimensionsView = Record<RequirementDimensionKey, RequirementBaselineDimensionView>;

export interface RequirementBaselineView {
  dimensions: RequirementBaselineDimensionsView;
  assumptions: string[];
  unresolvedItems: string[];
}

export interface ClarificationQuestionView {
  questionId: string;
  dimension: RequirementDimensionKey;
  questionText: string;
  reason: string;
  sourceRefs: SourceRefView[];
}

export interface ClarificationAnswerView { questionId: string; answer: string }
export interface ClarificationRoundView {
  roundNo: number;
  aiTaskId: string;
  aiResultId: string;
  questions: ClarificationQuestionView[];
  answers: ClarificationAnswerView[];
}

export interface RequirementClarificationView {
  mode: ClarificationModeValue;
  continueDeepConfirmed: boolean;
  assessmentRef: { objectType: string; objectId: string; objectVersionId: string | null } | null;
  assessmentSummary: string | null;
  assessment: RequirementAssessmentView | null;
  rounds: ClarificationRoundView[];
  finishReason: FinishReason | null;
}

export interface RequirementAssessmentView {
  aiResultId: string;
  assessmentVersion: string;
  complexityBand: ComplexityBand;
  reasons: string[];
  missingItems: string[];
  dimensions: Record<RequirementDimensionKey, RequirementDimensionStatusView>;
  missingDimensions: RequirementDimensionKey[];
  recommendedMode: ClarificationModeValue;
  sourceRefs: SourceRefView[];
}

export interface RequirementContentView {
  rawInput: string;
  rawInputRef: SourceRefView;
  clarification: RequirementClarificationView;
  baseline: RequirementBaselineView;
}

export interface RequirementSummaryView {
  id: string;
  title: string;
  projectVersionId: string;
  status: RequirementStatusValue;
  sourceType: RequirementSourceTypeValue;
  priority: RequirementPriorityValue;
  currentVersionId: string | null;
  effectiveVersionId: string | null;
  version: number;
  updatedAt: string;
}

export interface RequirementVersionView {
  id: string;
  requirementId: string;
  versionNo: string;
  contentHash: string;
  contentFormat: string;
  content: RequirementContentView;
  confirmationStatus: VersionConfirmationStatusValue;
  isEffective: boolean;
  sourceVersionId: string | null;
  createdFromAiResultId: string | null;
  unresolvedCount: number;
  riskAcceptances: RiskAcceptanceView[];
}

export interface RiskAcceptanceView { missingItemCode: string; impact: "low" | "medium"; reason: string }
export interface RequirementView {
  requirement: RequirementSummaryView;
  currentVersion: RequirementVersionView | null;
  effectiveVersion: RequirementVersionView | null;
  canEdit: boolean;
  allowedActions: string[];
}

export interface CreateRequirementInput { title: string; rawInput: string; sourceRefs?: SourceRefView[] }
export interface SetClarificationModeInput { expectedVersion: number; mode: ClarificationModeValue; reason?: string | null }
export interface SubmitClarificationAnswersInput {
  expectedVersion: number;
  roundNo: number;
  answers: ClarificationAnswerView[];
  continueDeepConfirmed: boolean;
  finishNow: boolean;
}
export interface ReviseRequirementVersionInput {
  expectedVersion: number;
  content?: RequirementContentView;
  title?: string;
  riskAcceptances?: RiskAcceptanceView[];
}
export interface ConfirmRequirementVersionInput { expectedVersion: number; riskAcceptances?: RiskAcceptanceView[] }

export interface RequirementPort {
  list(projectVersionId: string): Promise<RequirementSummaryView[]>;
  get(requirementId: string): Promise<RequirementView>;
  create(projectVersionId: string, input: CreateRequirementInput): Promise<RequirementView>;
  setClarificationMode(versionId: string, input: SetClarificationModeInput): Promise<RequirementVersionView>;
  submitClarificationAnswers(versionId: string, input: SubmitClarificationAnswersInput): Promise<{ version: RequirementVersionView; baselineCandidateRef: string | null }>;
  revise(versionId: string, input: ReviseRequirementVersionInput): Promise<RequirementVersionView>;
  confirm(versionId: string, input: ConfirmRequirementVersionInput): Promise<{ version: RequirementVersionView; gateResult: "passed" | "passed_with_risk" }>;
}

export type PrdStatusValue = "draft" | "in_review" | "changes_requested" | "confirmed";
export type DesignReviewStatusValue = "open" | "changes_requested" | "passed";
export type ReviewDecisionValue = "changes_requested" | "pass";

export interface PrdContentView {
  schemaVersion: "prd.mvp2.v1";
  background: string;
  goal: string;
  primaryUser: string;
  inScope: string[];
  outOfScope: string[];
  coreWorkflow: string[];
  keyRules: string[];
  exceptionsAndBoundaries: string[];
  acceptanceCriteria: string[];
}

export interface PrdView {
  id: string;
  projectVersionId: string;
  sourceRequirementVersionId: string;
  name: string;
  status: PrdStatusValue;
  rowVersion: number;
  currentVersionId: string | null;
}

export interface PrdVersionView {
  id: string;
  prdId: string;
  versionNo: string;
  contentHash: string;
  content: PrdContentView;
  sourceVersionId: string | null;
  isEffective: boolean;
}

export interface DesignReviewView {
  id: string;
  projectVersionId: string;
  roundNo: number;
  rowVersion: number;
  status: DesignReviewStatusValue;
  summary: string | null;
  prdId: string;
  prdVersionId: string;
  contentHash: string;
}

export interface CreatePrdInput { name: string; sourceRequirementVersionId: string }
export interface SavePrdVersionInput { expectedVersion: number; changeNote: string; content: PrdContentView }
export interface SubmitPrdReviewInput { prdId: string; prdVersionId: string; contentHash: string; expectedVersion: number }
export interface DecidePrdReviewInput { decision: ReviewDecisionValue; expectedVersion: number; summary?: string }

export interface PrdPort {
  list(projectVersionId: string): Promise<PrdView[]>;
  create(projectVersionId: string, input: CreatePrdInput): Promise<PrdView>;
  get(prdId: string): Promise<PrdView>;
  getVersion(versionId: string): Promise<PrdVersionView>;
  saveVersion(prdId: string, input: SavePrdVersionInput): Promise<PrdVersionView>;
  submitReview(projectVersionId: string, input: SubmitPrdReviewInput): Promise<DesignReviewView>;
  getReview(reviewId: string): Promise<DesignReviewView>;
  decideReview(reviewId: string, input: DecidePrdReviewInput): Promise<DesignReviewView>;
}

export interface AiTaskView {
  taskId: string;
  taskPublicId: string;
  taskType: "requirement.clarify";
  status: AiTaskStatus;
  targetSnapshotHash: string;
  pollUrl: string;
  eventsUrl: string;
  missingItems: string[];
  createdByUserId: string;
  queuedAt: string;
  resultRefs: AiTaskResultRefView[];
}
export interface AiTaskResultRefView { resultId: string; status: AiResultStatus; targetSnapshotHash: string }
export interface AiResultQualityView { formatStatus: string; traceabilityStatus: string; safetyStatus: string; requiredItemsMet: number; requiredItemsTotal: number; majorError: boolean; blockerCodes: string[] }
export interface AiResultConvergenceView { shouldFinish: boolean; finishReason: FinishReason | null; nextRoundNo: number | null }
export interface AiResultCapabilitySummaryView {
  truthLabel: "FORMAL_MOCK" | "REAL_PROVIDER" | null;
  providerCode: string | null;
  modelCode: string | null;
}
export interface AiResultView {
  id: string;
  taskPublicId: string;
  taskType: "requirement.clarify";
  targetSnapshotHash: string;
  mode: ClarificationModeValue;
  roundNo: number;
  resultKind: "assessment" | "questions" | "baseline";
  status: AiResultStatus;
  content: {
    assessment: RequirementAssessmentView | null;
    questions: ClarificationQuestionView[];
    baseline: RequirementBaselineView | null;
  } | null;
  convergence: AiResultConvergenceView;
  quality: AiResultQualityView;
  capabilitySummary: AiResultCapabilitySummaryView;
}
export interface CreateAiTaskInput { requirementId: string; versionId: string; sourceRefIds: string[]; userInstruction?: string | null; riskAcceptances?: RiskAcceptanceView[] }
export interface FormalizeAiResultInput {
  requirementId: string;
  expectedVersion: number;
  targetSnapshotHash: string;
  adoption?: "modified_adopt";
  modificationIntensity?: "minor";
  modifiedContent?: { baseline: RequirementBaselineView };
}
export interface FormalizedVersionView { id: string; versionNo: string; status: string; contentHash: string; createdAt: string }
export interface AiPort {
  createTask(input: CreateAiTaskInput): Promise<AiTaskView>;
  getTask(taskId: string): Promise<AiTaskView>;
  getResult(resultId: string): Promise<AiResultView>;
  formalizeBaseline(resultId: string, input: FormalizeAiResultInput): Promise<FormalizedVersionView>;
}

export type PortApiCode = ErrorCode | Sprint2ErrorCode;
