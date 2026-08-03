import type { CreateProjectInput, DeriveVersionInput, FrontendApi, ProjectOverviewView, ProjectSummaryView, Scenario, SessionView, VersionView } from "./ports";
import { PortError } from "./ports";

export const MOCK_ADAPTER_NOTICE = "Sprint 1 first-wave mock: replace only after the frozen OpenAPI client is generated.";
const projects: ProjectSummaryView[] = [
  { id: "atlas", name: "Atlas 产品验证", goal: "验证核心需求并形成可审计版本", workingVersionId: "atlas-v2", workingVersionNo: "V2", projectVersion: 2, stage: "需求澄清", updatedAt: "2026-07-29T09:30:00Z" },
  { id: "nova", name: "Nova 工作台", goal: "整理项目上下文", workingVersionId: "nova-v1", workingVersionNo: "V1", projectVersion: 1, stage: "项目初始化", updatedAt: "2026-07-28T10:00:00Z" },
];
const versions: VersionView[] = [
  { id: "atlas-v2", number: "V2", source: "atlas-v1", reason: "补充目标用户约束", createdAt: "2026-07-29T09:30:00Z", isWorking: true },
  { id: "atlas-v1", number: "V1", source: null, reason: "创建项目", createdAt: "2026-07-28T09:00:00Z", isWorking: false },
];
const session: SessionView = { user: { id: "user-1", displayName: "林岚", email: "linlan@example.com" }, expiresAt: "2026-07-29T18:00:00Z" };
const wait = async () => Promise.resolve();
const fail = (scenario?: Scenario) => { if (scenario === "forbidden") throw new PortError("FORBIDDEN", "你没有执行此操作的权限。"); if (scenario === "conflict") throw new PortError("CONFLICT", "工作版本已被其他成员更新，请加载最新状态。"); if (scenario === "failure") throw new PortError("FAILED", "请求未完成，请保留当前内容后重试。"); };
const overview = (projectId: string, viewedVersionId = "atlas-v2"): ProjectOverviewView => { const version = versions.find((item) => item.id === viewedVersionId) ?? versions[0]; return { ...projects[0], id: projectId, viewedVersionId: version.id, viewedVersionNo: version.number, isHistory: !version.isWorking, canEdit: version.isWorking, blocker: "目标用户证据尚待补充" }; };

export const mockApi: FrontendApi = {
  identity: { async login(input) { await wait(); if (!input.email || !input.password || input.email.includes("fail")) throw new PortError("FAILED", "邮箱或密码不正确。"); return session; }, async register(input) { await wait(); if (!input.displayName || !input.email || input.password.length < 12) throw new PortError("FAILED", "请完整填写信息，密码至少 12 位。"); return session; }, async refresh() { await wait(); return session; }, async logout() { await wait(); } },
  projects: { async list(scenario) { await wait(); fail(scenario); return scenario === "empty" || scenario === "filtered-empty" ? [] : projects; }, async create(input: CreateProjectInput, scenario) { await wait(); fail(scenario); if (!input.name || !input.goal) throw new PortError("FAILED", "请填写项目名称与目标。"); return { projectId: "new-project", workingVersionId: "new-project-v1" }; }, async overview(projectId, viewedVersionId) { await wait(); return overview(projectId, viewedVersionId); }, async versions() { await wait(); return versions; }, async setWorking(projectId, versionId, _expected, scenario) { await wait(); fail(scenario); return { ...overview(projectId, versionId), workingVersionId: versionId, workingVersionNo: versions.find((v) => v.id === versionId)?.number ?? "V1", isHistory: false, canEdit: true }; }, async derive(_projectId, input: DeriveVersionInput, scenario) { await wait(); fail(scenario); if (!input.reason.trim()) throw new PortError("FAILED", "必须记录派生原因。"); return { id: "atlas-v3", number: "V3", source: input.sourceVersionId, reason: input.reason, createdAt: "2026-07-29T10:00:00Z", isWorking: false }; } },
  files: { async list() { await wait(); return []; }, async upload(_projectId, file, scenario) { await wait(); if (scenario === "failure") return { id: `failed-${file.name}`, name: file.name, progress: 62, status: "failed", relation: null, error: "存储暂不可用，文件尚未完成入库。" }; return { id: `file-${file.name}`, name: file.name, progress: 100, status: "uploaded", relation: null }; }, async retry(_projectId, item) { await wait(); return { ...item, progress: 100, status: "uploaded", error: undefined }; }, async relate(_projectId, fileId, relation) { await wait(); return { id: fileId, name: fileId.replace(/^file-/, ""), progress: 100, status: "uploaded", relation }; } },
  health: { async get() { await wait(); return { status: "healthy", service: "mock-api", environment: "local", release: "mock", traceId: "mock-trace" }; } },
};
