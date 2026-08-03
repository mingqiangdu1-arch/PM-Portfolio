/** UI-facing view models, not handwritten OpenAPI DTOs. Generated schema types
 * will be mapped into this boundary only after Review freezes the contract. */
export type Scenario = "ready" | "loading" | "empty" | "filtered-empty" | "failure" | "forbidden" | "readonly" | "conflict";
export interface UserView { id: string; displayName: string; email: string }
export interface SessionView { user: UserView; expiresAt: string }
export interface AuthCredentials { email: string; password: string }
export interface RegistrationInput extends AuthCredentials { displayName: string }
export interface ProjectSummaryView { id: string; name: string; goal: string; workingVersionId: string; workingVersionNo: string; projectVersion: number; stage: string; updatedAt: string }
export interface ProjectOverviewView extends ProjectSummaryView { viewedVersionId: string; viewedVersionNo: string; isHistory: boolean; canEdit: boolean; blocker: string | null }
export interface VersionView { id: string; number: string; source: string | null; reason: string; createdAt: string; isWorking: boolean }
export interface CreateProjectInput { name: string; goal: string; startMode: "new" | "import" }
export interface DeriveVersionInput { sourceVersionId: string; reason: string; inheritContext: boolean; expectedProjectVersion: number }
export interface PendingUploadRecovery { uploadId: string; storedFileId: string; checksumSha256: string; completeIdempotencyKey: string; file: File }
export interface FileItemView { id: string; name: string; progress: number; status: "uploading" | "uploaded" | "failed" | "parsing" | "manual-required"; relation: string | null; error?: string; retryFile?: File; pendingUpload?: PendingUploadRecovery }
export interface HealthView { status: string; service: string; environment: string; release: string; traceId: string }
export interface IdentityPort { login(input: AuthCredentials): Promise<SessionView>; register(input: RegistrationInput): Promise<SessionView>; refresh(): Promise<SessionView>; logout(): Promise<void> }
export interface ProjectPort { list(scenario?: Scenario): Promise<ProjectSummaryView[]>; create(input: CreateProjectInput, scenario?: Scenario): Promise<{ projectId: string; workingVersionId: string }>; overview(projectId: string, viewedVersionId?: string): Promise<ProjectOverviewView>; versions(projectId: string): Promise<VersionView[]>; setWorking(projectId: string, versionId: string, expectedProjectVersion: number, scenario?: Scenario): Promise<ProjectOverviewView>; derive(projectId: string, input: DeriveVersionInput, scenario?: Scenario): Promise<VersionView> }
export interface FilePort { list(projectId: string): Promise<FileItemView[]>; upload(projectId: string, file: File, scenario?: Scenario, onProgress?: (progress: number) => void): Promise<FileItemView>; retry(projectId: string, item: FileItemView): Promise<FileItemView>; relate(projectId: string, fileId: string, relation: string): Promise<FileItemView> }
export interface HealthPort { get(): Promise<HealthView> }
export interface FrontendApi { identity: IdentityPort; projects: ProjectPort; files: FilePort; health: HealthPort }
export type FrontendErrorCategory = "UNAUTHENTICATED" | "FORBIDDEN" | "CONFLICT" | "RATE_LIMITED" | "STORAGE_UNAVAILABLE" | "CONTRACT_UNAVAILABLE" | "FAILED";
import type { ErrorCode } from "./generated/models";
export class PortError extends Error {
  constructor(
    public readonly category: FrontendErrorCategory,
    message: string,
    public readonly status?: number,
    public readonly traceId?: string,
    public readonly details: unknown[] = [],
    public readonly apiCode?: ErrorCode,
  ) { super(traceId ? `${message} Trace: ${traceId}` : message); this.name = "PortError"; }
}
