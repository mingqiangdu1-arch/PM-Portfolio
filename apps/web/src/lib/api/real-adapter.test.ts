import { beforeEach, describe, expect, it, vi } from "vitest";

const client = vi.hoisted(() => ({
  abortFileUpload: vi.fn(),
  completeFileUpload: vi.fn(),
  confirmRequirementVersion: vi.fn(),
  createAiTask: vi.fn(),
  createProject: vi.fn(),
  createRequirement: vi.fn(),
  formalizeAiResult: vi.fn(),
  getAiResult: vi.fn(),
  getAiTask: vi.fn(),
  getApiHealth: vi.fn(),
  getFile: vi.fn(),
  getProject: vi.fn(),
  getProjectVersion: vi.fn(),
  getSession: vi.fn(),
  initFileUpload: vi.fn(),
  listProjects: vi.fn(),
  listProjectVersions: vi.fn(),
  listRequirements: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  refreshAccessToken: vi.fn(),
  register: vi.fn(),
  setWorkingProjectVersion: vi.fn(),
  setRequirementClarificationMode: vi.fn(),
  submitRequirementClarificationAnswers: vi.fn(),
  reviseRequirementVersion: vi.fn(),
  getRequirement: vi.fn(),
  listProjectVersionPrds: vi.fn(),
  createProjectVersionPrd: vi.fn(),
  getPrd: vi.fn(),
  getPrdVersion: vi.fn(),
  createPrdVersion: vi.fn(),
  submitPrdDesignReview: vi.fn(),
  getDesignReview: vi.fn(),
  decideDesignReview: vi.fn(),
  listProjectVersionImplementationPlans: vi.fn(),
  createProjectVersionImplementationPlan: vi.fn(),
  getImplementationPlan: vi.fn(),
  createImplementationPlanVersion: vi.fn(),
  setEffectiveImplementationPlanVersion: vi.fn(),
  listImplementationPlanConfirmationRounds: vi.fn(),
  createImplementationPlanConfirmationRound: vi.fn(),
  getConfirmationRound: vi.fn(),
  updateConfirmationRoundDraft: vi.fn(),
  confirmConfirmationRound: vi.fn(),
  listConfirmationRoundTestRecords: vi.fn(),
  createConfirmationRoundTestRecord: vi.fn(),
  getTestRecord: vi.fn(),
  updateTestRecordDraft: vi.fn(),
  submitTestRecord: vi.fn(),
}));

vi.mock("./generated/client", () => client);

import { __resetRealAdapterForTests, realApi } from "./real-adapter";
import { PortError } from "./ports";
import type { RequirementBaselineView } from "./ports";

const success = <T,>(data: T) => ({ status: 200, data: { code: "OK", message: "ok", trace_id: "trace-ok", data }, headers: new Headers() }) as never;
const failure = (code: string, status: number, details: unknown[] = [{ field: "x", message: "bad" }]) => ({ status, data: { code, message: `error:${code}`, trace_id: "trace-error", details }, headers: new Headers() }) as never;
const refreshed = () => success({ access_token: "rotated-token", expires_in: 900, token_type: "Bearer" });
const emptyProjects = () => success({ items: [], has_more: false, next_cursor: null });
const emptyVersions = () => success({ items: [], has_more: false, next_cursor: null });
const session = () => success({ session_id: "session-1", expires_at: "2026-08-03T01:00:00Z", system_roles: [], user: { id: "user-1", display_name: "User", email: "user@example.com", status: "active", system_roles: [] } });
const authToken = (access_token: string) => success({ access_token, expires_in: 900, token_type: "Bearer", user: { id: "user-1", display_name: "User", email: "user@example.com", status: "active", system_roles: [] } });
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (reason?: unknown) => void; const promise = new Promise<T>((resolvePromise, rejectPromise) => { resolve = resolvePromise; reject = rejectPromise; }); return { promise, resolve, reject }; }

class SuccessfulUploadRequest {
  status = 200;
  upload: { onprogress?: (event: ProgressEvent<EventTarget>) => void } = {};
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  open = vi.fn();
  setRequestHeader = vi.fn();
  getResponseHeader = vi.fn(() => "etag-1");
  send = vi.fn(() => this.onload?.());
}

describe("realApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    __resetRealAdapterForTests();
    vi.stubGlobal("XMLHttpRequest", SuccessfulUploadRequest);
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "test-key"), subtle: { digest: vi.fn(async () => new Uint8Array(32).buffer) } });
  });

  it("maps all frozen PRD and Design Review operations through the generated client", async () => {
    const prd = { id: "prd-1", project_version_id: "pv-1", source_requirement_version_id: "req-v2", name: "核心 PRD", status: "draft", row_version: 3, current_version_id: "prd-v1" };
    const version = { id: "prd-v1", prd_id: "prd-1", version_no: "V1", content_hash: "a".repeat(64), content_json: { schema_version: "prd.mvp2.v1", background: "背景", goal: "目标", primary_user: "负责人", in_scope: ["范围内"], out_of_scope: ["范围外"], core_workflow: ["步骤"], key_rules: ["规则"], exceptions_and_boundaries: ["边界"], acceptance_criteria: ["验收"] }, source_version_id: null, is_effective: true };
    const review = { id: "review-1", project_version_id: "pv-1", round_no: 1, row_version: 2, status: "open", summary: null, scope: { prd_id: "prd-1", prd_version_id: "prd-v1", content_hash: "a".repeat(64) } };
    client.listProjectVersionPrds.mockResolvedValue(success({ items: [prd], has_more: false }));
    client.createProjectVersionPrd.mockResolvedValue(success({ prd }));
    client.getPrd.mockResolvedValue(success({ prd }));
    client.getPrdVersion.mockResolvedValue(success({ prd_version: version }));
    client.createPrdVersion.mockResolvedValue(success({ prd_version: version }));
    client.submitPrdDesignReview.mockResolvedValue(success({ design_review: review }));
    client.getDesignReview.mockResolvedValue(success({ design_review: review }));
    client.decideDesignReview.mockResolvedValue(success({ design_review: { ...review, status: "passed", row_version: 3 } }));

    await expect(realApi.prds.list("pv-1")).resolves.toMatchObject([{ id: "prd-1", rowVersion: 3 }]);
    await expect(realApi.prds.create("pv-1", { name: "核心 PRD", sourceRequirementVersionId: "req-v2" })).resolves.toMatchObject({ sourceRequirementVersionId: "req-v2" });
    await expect(realApi.prds.get("prd-1")).resolves.toMatchObject({ currentVersionId: "prd-v1" });
    await expect(realApi.prds.getVersion("prd-v1")).resolves.toMatchObject({ content: { schemaVersion: "prd.mvp2.v1", primaryUser: "负责人" } });
    await expect(realApi.prds.saveVersion("prd-1", { expectedVersion: 3, changeNote: "首次保存", content: { schemaVersion: "prd.mvp2.v1", background: "背景", goal: "目标", primaryUser: "负责人", inScope: ["范围内"], outOfScope: ["范围外"], coreWorkflow: ["步骤"], keyRules: ["规则"], exceptionsAndBoundaries: ["边界"], acceptanceCriteria: ["验收"] } })).resolves.toMatchObject({ versionNo: "V1" });
    await expect(realApi.prds.submitReview("pv-1", { prdId: "prd-1", prdVersionId: "prd-v1", contentHash: "a".repeat(64), expectedVersion: 3 })).resolves.toMatchObject({ status: "open" });
    await expect(realApi.prds.getReview("review-1")).resolves.toMatchObject({ roundNo: 1 });
    await expect(realApi.prds.decideReview("review-1", { decision: "pass", expectedVersion: 2 })).resolves.toMatchObject({ status: "passed" });

    expect(client.createProjectVersionPrd).toHaveBeenCalledWith("pv-1", { name: "核心 PRD", source_requirement_version_id: "req-v2" }, expect.objectContaining({ "Idempotency-Key": expect.stringMatching(/^web-/) }), expect.any(Object));
    expect(client.createPrdVersion.mock.calls[0][1]).toMatchObject({ expected_version: 3, change_note: "首次保存", content_json: { schema_version: "prd.mvp2.v1", primary_user: "负责人" } });
    expect(client.submitPrdDesignReview.mock.calls[0][1]).toEqual({ prd_id: "prd-1", prd_version_id: "prd-v1", content_hash: "a".repeat(64), expected_version: 3 });
    expect(client.decideDesignReview.mock.calls[0][1]).toEqual({ decision: "pass", expected_version: 2 });
  });

  it("materializes all MVP3 operations with the frozen command header boundary", async () => {
    const content = { schema_version: "implementation_plan.mvp3.v1", features: [{ key: "feature", description: "A feature" }], business_rules: [], state_requirements: [], exceptions: [], interactions: [], dependencies: [], acceptance_scope: [{ key: "acceptance", description: "An acceptance rule" }] };
    const readiness = { schema_version: "implementation_confirmation.readiness.mvp3.v1", scope_status: "ready", implementation_status: "ready", configuration_status: "not_applicable", data_change_status: "not_applicable", known_blockers: [] };
    const version = { id: "plan-version-1", implementation_plan_id: "plan-1", source_version_id: null, version_no: "V1", review_id: "review-1", content_json: content, content_hash: "a".repeat(64), change_note: "first", is_effective: true, created_by: "user-1", created_at: "2026-08-24T00:00:00Z" };
    const plan = { id: "plan-1", project_version_id: "pv-1", source_prd_version_id: "prd-version-1", source_design_review_id: "review-1", name: "Plan", status: "active", current_version_id: "plan-version-1", effective_version_id: "plan-version-1", row_version: 3, confirmation_state: "needs_confirmation", versions: [version] };
    const round = { id: "round-1", implementation_plan_id: "plan-1", plan_version_id: "plan-version-1", source_round_id: null, round_no: 1, status: "draft", confirm_status: null, implementation_summary: "A human implementation scope summary", readiness_json: readiness, row_version: 1, is_effective: false, confirmed_by: null, confirmed_at: null, superseded_at: null };
    const planSummary = { ...plan } as Omit<typeof plan, "versions">;
    delete (planSummary as { versions?: unknown }).versions;
    client.listProjectVersionImplementationPlans.mockResolvedValue(success({ items: [planSummary] }));
    client.createProjectVersionImplementationPlan.mockResolvedValue(success({ implementation_plan: plan }));
    client.getImplementationPlan.mockResolvedValue(success({ implementation_plan: plan }));
    client.createImplementationPlanVersion.mockResolvedValue(success({ implementation_plan_version: version, plan_row_version: 3 }));
    client.setEffectiveImplementationPlanVersion.mockResolvedValue(success({ implementation_plan: plan }));
    client.listImplementationPlanConfirmationRounds.mockResolvedValue(success({ items: [round] }));
    client.createImplementationPlanConfirmationRound.mockResolvedValue(success({ confirmation_round: round }));
    client.getConfirmationRound.mockResolvedValue(success({ confirmation_round: round }));
    client.updateConfirmationRoundDraft.mockResolvedValue(success({ confirmation_round: round }));
    client.confirmConfirmationRound.mockResolvedValue(success({ confirmation_round: { ...round, status: "confirmed", confirm_status: "confirmed" } }));

    await expect(realApi.implementationPlans.list("pv-1")).resolves.toMatchObject([{ id: "plan-1", sourcePrdVersionId: "prd-version-1", sourceDesignReviewId: "review-1", currentVersionId: "plan-version-1", effectiveVersionId: "plan-version-1", versions: [] }]);
    await expect(realApi.implementationPlans.create("pv-1", { name: "Plan", sourcePrdVersionId: "prd-version-1", sourceDesignReviewId: "review-1" })).resolves.toMatchObject({ id: "plan-1", confirmationState: "needs_confirmation" });
    await expect(realApi.implementationPlans.get("plan-1")).resolves.toMatchObject({ versions: [{ id: "plan-version-1", sourceVersionId: null, content: { schemaVersion: "implementation_plan.mvp3.v1", features: [{ key: "feature" }] } }] });
    await expect(realApi.implementationPlans.saveVersion("plan-1", { expectedVersion: 2, changeNote: "first", content: { schemaVersion: "implementation_plan.mvp3.v1", features: [{ key: "feature", description: "A feature" }], businessRules: [], stateRequirements: [], exceptions: [], interactions: [], dependencies: [], acceptanceScope: [{ key: "acceptance", description: "An acceptance rule" }] } })).resolves.toMatchObject({ version: { id: "plan-version-1", versionNo: "V1", sourceVersionId: null, content: { acceptanceScope: [{ key: "acceptance" }] } }, planRowVersion: 3 });
    await expect(realApi.implementationPlans.setEffective("plan-version-1", 3)).resolves.toMatchObject({ effectiveVersionId: "plan-version-1", confirmationState: "needs_confirmation" });
    await expect(realApi.confirmationRounds.list("plan-1")).resolves.toMatchObject([{ id: "round-1", roundNo: 1, readiness: { scopeStatus: "ready", knownBlockers: [] } }]);
    await expect(realApi.confirmationRounds.create("plan-1", { planVersionId: "plan-version-1", implementationSummary: "A human implementation scope summary", readiness: { schemaVersion: "implementation_confirmation.readiness.mvp3.v1", scopeStatus: "ready", implementationStatus: "ready", configurationStatus: "not_applicable", dataChangeStatus: "not_applicable", knownBlockers: [] } })).resolves.toMatchObject({ id: "round-1", planVersionId: "plan-version-1", implementationSummary: "A human implementation scope summary" });
    await expect(realApi.confirmationRounds.get("round-1")).resolves.toMatchObject({ id: "round-1", readiness: { implementationStatus: "ready" } });
    await expect(realApi.confirmationRounds.updateDraft("round-1", { expectedVersion: 1, planVersionId: "plan-version-1", implementationSummary: "A human implementation scope summary", readiness: { schemaVersion: "implementation_confirmation.readiness.mvp3.v1", scopeStatus: "ready", implementationStatus: "ready", configurationStatus: "not_applicable", dataChangeStatus: "not_applicable", knownBlockers: [] } })).resolves.toMatchObject({ status: "draft", rowVersion: 1 });
    await expect(realApi.confirmationRounds.confirm("round-1", 1)).resolves.toMatchObject({ status: "confirmed", confirmStatus: "confirmed" });

    for (const command of [client.createProjectVersionImplementationPlan, client.createImplementationPlanVersion, client.setEffectiveImplementationPlanVersion, client.createImplementationPlanConfirmationRound, client.confirmConfirmationRound]) {
      expect(command.mock.calls.at(-1)?.[2]).toEqual(expect.objectContaining({ "Idempotency-Key": expect.stringMatching(/^web-/) }));
    }
    expect(client.updateConfirmationRoundDraft.mock.calls[0]?.[2]).toEqual(expect.not.objectContaining({ "Idempotency-Key": expect.anything() }));
  });

  it("reuses the same Idempotency-Key for retryable failures in all five MVP3 command families", async () => {
    const content = { schemaVersion: "implementation_plan.mvp3.v1" as const, features: [{ key: "feature", description: "A feature" }], businessRules: [], stateRequirements: [], exceptions: [], interactions: [], dependencies: [], acceptanceScope: [{ key: "acceptance", description: "An acceptance rule" }] };
    const readiness = { schemaVersion: "implementation_confirmation.readiness.mvp3.v1" as const, scopeStatus: "ready" as const, implementationStatus: "ready" as const, configurationStatus: "not_applicable" as const, dataChangeStatus: "not_applicable" as const, knownBlockers: [] };
    const wireContent = { schema_version: content.schemaVersion, features: content.features, business_rules: [], state_requirements: [], exceptions: [], interactions: [], dependencies: [], acceptance_scope: content.acceptanceScope };
    const wireReadiness = { schema_version: readiness.schemaVersion, scope_status: readiness.scopeStatus, implementation_status: readiness.implementationStatus, configuration_status: readiness.configurationStatus, data_change_status: readiness.dataChangeStatus, known_blockers: [] };
    const plan = { id: "plan-1", project_version_id: "pv-1", source_prd_version_id: "prd-version-1", source_design_review_id: "review-1", name: "Plan", status: "active", current_version_id: "version-1", effective_version_id: "version-1", row_version: 2, confirmation_state: "needs_confirmation", versions: [] };
    const version = { id: "version-1", implementation_plan_id: "plan-1", source_version_id: null, version_no: "V1", review_id: "review-1", content_json: wireContent, content_hash: "a".repeat(64), change_note: "first", is_effective: true, created_by: "user-1", created_at: "2026-08-24T00:00:00Z" };
    const round = { id: "round-1", implementation_plan_id: "plan-1", plan_version_id: "version-1", source_round_id: null, round_no: 1, status: "confirmed", confirm_status: "confirmed", implementation_summary: "A human implementation scope summary", readiness_json: wireReadiness, row_version: 2, is_effective: true, confirmed_by: "user-1", confirmed_at: "2026-08-24T00:00:00Z", superseded_at: null };
    client.createProjectVersionImplementationPlan.mockResolvedValueOnce(failure("DEPENDENCY_UNAVAILABLE", 503)).mockResolvedValueOnce(success({ implementation_plan: plan }));
    client.createImplementationPlanVersion.mockResolvedValueOnce(failure("DEPENDENCY_UNAVAILABLE", 503)).mockResolvedValueOnce(success({ implementation_plan_version: version, plan_row_version: 2 }));
    client.setEffectiveImplementationPlanVersion.mockResolvedValueOnce(failure("DEPENDENCY_UNAVAILABLE", 503)).mockResolvedValueOnce(success({ implementation_plan: plan }));
    client.createImplementationPlanConfirmationRound.mockResolvedValueOnce(failure("DEPENDENCY_UNAVAILABLE", 503)).mockResolvedValueOnce(success({ confirmation_round: round }));
    client.confirmConfirmationRound.mockResolvedValueOnce(failure("DEPENDENCY_UNAVAILABLE", 503)).mockResolvedValueOnce(success({ confirmation_round: round }));
    const planInput = { name: "Plan", sourcePrdVersionId: "prd-version-1", sourceDesignReviewId: "review-1" };
    const saveInput = { expectedVersion: 1, changeNote: "first", content };
    const roundInput = { planVersionId: "version-1", implementationSummary: "A human implementation scope summary", readiness };
    const retry = async (call: () => Promise<unknown>, command: ReturnType<typeof vi.fn>) => { await expect(call()).rejects.toBeInstanceOf(PortError); await call(); expect(command.mock.calls[1][2]["Idempotency-Key"]).toBe(command.mock.calls[0][2]["Idempotency-Key"]); };
    await retry(() => realApi.implementationPlans.create("pv-1", planInput), client.createProjectVersionImplementationPlan);
    await retry(() => realApi.implementationPlans.saveVersion("plan-1", saveInput), client.createImplementationPlanVersion);
    await retry(() => realApi.implementationPlans.setEffective("version-1", 1), client.setEffectiveImplementationPlanVersion);
    await retry(() => realApi.confirmationRounds.create("plan-1", roundInput), client.createImplementationPlanConfirmationRound);
    await retry(() => realApi.confirmationRounds.confirm("round-1", 2), client.confirmConfirmationRound);
    client.updateConfirmationRoundDraft.mockResolvedValue(success({ confirmation_round: round }));
    await realApi.confirmationRounds.updateDraft("round-1", { expectedVersion: 2, ...roundInput });
    expect(client.updateConfirmationRoundDraft.mock.calls[0][2]).toEqual(expect.not.objectContaining({ "Idempotency-Key": expect.anything() }));
  });

  it("refreshes once after a 401 and retries the original protected request", async () => {
    client.listProjects.mockResolvedValueOnce(failure("AUTH_REQUIRED", 401)).mockResolvedValueOnce(emptyProjects());
    client.refreshAccessToken.mockResolvedValue(refreshed());

    await expect(realApi.projects.list()).resolves.toEqual([]);

    expect(client.refreshAccessToken).toHaveBeenCalledTimes(1);
    expect(client.listProjects).toHaveBeenCalledTimes(2);
    expect(client.listProjects.mock.calls[1][1].headers).toEqual({ Authorization: "Bearer rotated-token" });
  });

  it("uses a single refresh rotation for concurrent 401 responses", async () => {
    client.listProjects.mockResolvedValueOnce(failure("AUTH_REQUIRED", 401)).mockResolvedValueOnce(emptyProjects());
    client.listProjectVersions.mockResolvedValueOnce(failure("UNAUTHORIZED", 401)).mockResolvedValueOnce(emptyVersions());
    client.refreshAccessToken.mockResolvedValue(refreshed());

    await expect(Promise.all([realApi.projects.list(), realApi.projects.versions("project-1")])).resolves.toEqual([[], []]);

    expect(client.refreshAccessToken).toHaveBeenCalledTimes(1);
  });

  it("does not recurse when refresh fails and preserves the refresh business error", async () => {
    const recover = vi.fn();
    window.addEventListener("aipdv:session-recovery", recover);
    client.listProjects.mockResolvedValue(failure("AUTH_REQUIRED", 401));
    client.refreshAccessToken.mockResolvedValue(failure("TOKEN_REUSE_DETECTED", 401));

    await expect(realApi.projects.list()).rejects.toMatchObject({ category: "UNAUTHENTICATED", apiCode: "TOKEN_REUSE_DETECTED", status: 401, traceId: "trace-error" });

    expect(client.refreshAccessToken).toHaveBeenCalledTimes(1);
    expect(client.listProjects).toHaveBeenCalledTimes(1);
    expect(recover).toHaveBeenCalledTimes(1);
    window.removeEventListener("aipdv:session-recovery", recover);
  });

  it("clears the current token and emits one recovery event when the retried request is still unauthorized", async () => {
    const recover = vi.fn();
    window.addEventListener("aipdv:session-recovery", recover);
    client.listProjects.mockResolvedValueOnce(failure("AUTH_REQUIRED", 401)).mockResolvedValueOnce(failure("UNAUTHORIZED", 401)).mockResolvedValueOnce(emptyProjects());
    client.refreshAccessToken.mockResolvedValue(refreshed());

    await expect(realApi.projects.list()).rejects.toMatchObject({ category: "UNAUTHENTICATED", apiCode: "UNAUTHORIZED" });
    await expect(realApi.projects.list()).resolves.toEqual([]);

    expect(client.refreshAccessToken).toHaveBeenCalledTimes(1);
    expect(recover).toHaveBeenCalledTimes(1);
    expect(client.listProjects.mock.calls[1][1].headers).toEqual({ Authorization: "Bearer rotated-token" });
    expect(client.listProjects.mock.calls[2][1].headers).toBeUndefined();
    window.removeEventListener("aipdv:session-recovery", recover);
  });

  it("does not allow a refresh started before logout to restore authorization", async () => {
    const pendingRefresh = deferred<ReturnType<typeof refreshed>>();
    client.refreshAccessToken.mockReturnValue(pendingRefresh.promise);
    client.getSession.mockResolvedValue(session());
    client.logout.mockResolvedValue(success({}));
    const refresh = realApi.identity.refresh();
    await Promise.resolve();
    const signedOut = realApi.identity.logout();
    await Promise.resolve();

    expect(client.logout).not.toHaveBeenCalled();

    pendingRefresh.resolve(refreshed());
    await Promise.all([refresh, signedOut]);
    expect(client.logout).toHaveBeenCalledTimes(1);
    expect(client.logout.mock.calls[0][1]).toMatchObject({ credentials: "include" });
    expect(client.logout.mock.calls[0][1].headers).toBeUndefined();
    client.listProjects.mockResolvedValue(emptyProjects());
    await realApi.projects.list();

    expect(client.listProjects.mock.calls[0][1].headers).toBeUndefined();
  });

  it("does not start a replacement refresh when an old protected request receives 401 after logout", async () => {
    const delayedResponse = deferred<ReturnType<typeof emptyProjects>>();
    client.listProjects.mockReturnValueOnce(delayedResponse.promise);
    client.logout.mockResolvedValue(success({}));
    const oldRequest = realApi.projects.list();
    await Promise.resolve();
    await realApi.identity.logout();

    delayedResponse.resolve(failure("AUTH_REQUIRED", 401));
    await expect(oldRequest).rejects.toMatchObject({ category: "UNAUTHENTICATED", apiCode: "AUTH_REQUIRED" });

    expect(client.refreshAccessToken).not.toHaveBeenCalled();
  });

  it("does not allow an old refresh to overwrite a newer login or registration", async () => {
    const firstRefresh = deferred<ReturnType<typeof refreshed>>();
    client.refreshAccessToken.mockReturnValueOnce(firstRefresh.promise);
    client.getSession.mockResolvedValue(session());
    client.login.mockResolvedValue(authToken("login-token"));
    const staleRefresh = realApi.identity.refresh();
    await Promise.resolve();
    const login = realApi.identity.login({ email: "user@example.com", password: "password" });
    await Promise.resolve();
    expect(client.login).not.toHaveBeenCalled();
    firstRefresh.resolve(refreshed());
    await login;
    await staleRefresh;
    client.listProjects.mockResolvedValue(emptyProjects());
    await realApi.projects.list();
    expect(client.listProjects.mock.calls[0][1].headers).toEqual({ Authorization: "Bearer login-token" });

    const secondRefresh = deferred<ReturnType<typeof refreshed>>();
    client.refreshAccessToken.mockReturnValueOnce(secondRefresh.promise);
    const staleRefreshAfterLogin = realApi.identity.refresh();
    await Promise.resolve();
    client.register.mockResolvedValue(authToken("register-token"));
    const register = realApi.identity.register({ displayName: "User", email: "user@example.com", password: "password" });
    await Promise.resolve();
    expect(client.register).not.toHaveBeenCalled();
    secondRefresh.resolve(refreshed());
    await register;
    await staleRefreshAfterLogin;
    client.listProjects.mockResolvedValue(emptyProjects());
    await realApi.projects.list();
    expect(client.listProjects.mock.calls[1][1].headers).toEqual({ Authorization: "Bearer register-token" });
  });

  it("preserves generated business code, category, status, details and trace", async () => {
    client.listProjects.mockResolvedValueOnce(failure("VERSION_CONFLICT", 409, [{ field: "version", message: "stale" }]));

    await expect(realApi.projects.list()).rejects.toMatchObject({
      category: "CONFLICT",
      apiCode: "VERSION_CONFLICT",
      status: 409,
      traceId: "trace-error",
      details: [{ field: "version", message: "stale" }],
    });

    client.listProjects.mockResolvedValueOnce(failure("RATE_LIMITED", 429));
    try { await realApi.projects.list(); } catch (error) {
      expect(error).toBeInstanceOf(PortError);
      expect((error as PortError).category).toBe("RATE_LIMITED");
      expect((error as PortError).apiCode).toBe("RATE_LIMITED");
    }
  });

  it("maps frozen Requirement summary and keeps the AI task polling boundary", async () => {
    client.listRequirements.mockResolvedValue(success({ items: [{ id: "req-1", title: "需求", project_version_id: "v1", status: "draft", source_type: "manual", priority: "normal", current_version_id: "rv1", effective_version_id: null, version: 1, updated_at: "2026-08-08T00:00:00Z" }], has_more: false, next_cursor: null }));
    await expect(realApi.requirements.list("v1")).resolves.toEqual([{ id: "req-1", title: "需求", projectVersionId: "v1", status: "draft", sourceType: "manual", priority: "normal", currentVersionId: "rv1", effectiveVersionId: null, version: 1, updatedAt: "2026-08-08T00:00:00Z" }]);

    client.createAiTask.mockResolvedValue(success({ task_id: "task-1", task_public_id: "public-1", task_type: "requirement.clarify", status: "queued", target_snapshot_hash: "a".repeat(64), poll_url: "/tasks/1", events_url: "/tasks/1/events", missing_items: [], created_by_user_id: "user-1", queued_at: "2026-08-08T00:00:00Z", capability_summary: {}, result_refs: [] }));
    await expect(realApi.ai.createTask({ requirementId: "req-1", versionId: "rv1", sourceRefIds: ["src-1"] })).resolves.toMatchObject({ taskId: "task-1", status: "queued", resultRefs: [] });
    expect(client.createAiTask.mock.calls[0][0].target).toEqual({ object_type: "requirement", object_id: "req-1", object_version_id: "rv1" });

    client.getAiTask.mockResolvedValue(success({ task_id: "task-1", task_public_id: "public-1", task_type: "requirement.clarify", status: "ready", target_snapshot_hash: "a".repeat(64), poll_url: "/tasks/1", events_url: "/tasks/1/events", missing_items: [], created_by_user_id: "user-1", queued_at: "2026-08-08T00:00:00Z", capability_summary: {}, result_refs: [{ result_id: "result-1", status: "ready", target_snapshot_hash: "b".repeat(64), content_ref: "forbidden", content_fingerprint: "forbidden", ai_call_id: "forbidden", result_no: 1 }] }));
    const ready = await realApi.ai.getTask("task-1");
    expect(ready.resultRefs).toEqual([{ resultId: "result-1", status: "ready", targetSnapshotHash: "b".repeat(64) }]);
    expect(Object.keys(ready.resultRefs[0]).sort()).toEqual(["resultId", "status", "targetSnapshotHash"].sort());
  });

  it("preserves the R3 raw_input field through the FrontendApi adapter", async () => {
    client.getRequirement.mockResolvedValue(success({
      requirement: { id: "req-1", title: "需求", project_version_id: "v1", status: "draft", source_type: "manual", priority: "normal", current_version_id: "rv1", effective_version_id: null, version: 1, updated_at: "2026-08-09T00:00:00Z" },
      current_version: {
        id: "rv1", requirement_id: "req-1", version_no: "V1", content_hash: "b".repeat(64), content_format: "application/json",
        content_json: {
          raw_input: "R3 原始需求正文",
          raw_input_ref: { source_id: "src-1", source_version_id: null, source_type: "manual", label: "手工输入", content_hash: "c".repeat(64) },
          clarification: { mode: "auto", assessment_ref: null, assessment_summary: null, assessment: null, rounds: [], finish_reason: null },
          baseline: { assumptions: [], unresolved_items: [], dimensions: Object.fromEntries(["goal", "users_and_roles", "usage_scenarios", "functional_scope", "business_rules", "exception_cases", "permission_requirements", "acceptance_criteria"].map((key) => [key, { confirmed_facts: [], source_refs: [], deferred_items: [], not_applicable_items: [] }])) },
        },
        confirmation_status: "draft", is_effective: false, source_version_id: null, created_from_ai_result_id: null, unresolved_count: 0, risk_acceptances: [], created_at: "2026-08-09T00:00:00Z",
      },
      effective_version: null,
      permissions: { allowed_actions: ["edit"] },
    }));

    const result = await realApi.requirements.get("req-1");
    expect(result.currentVersion?.content.rawInput).toBe("R3 原始需求正文");
    expect(result.currentVersion?.content.clarification.continueDeepConfirmed).toBe(false);
  });

  it("serializes the complete revise payload with structured SourceRefs and nullable ObjectRef", async () => {
    const source = { sourceId: "src-1", sourceVersionId: "src-v1", sourceType: "manual", label: "原始输入", contentHash: "c".repeat(64) };
    const sourceWire = { source_id: "src-1", source_version_id: "src-v1", source_type: "manual", label: "原始输入", content_hash: "c".repeat(64) };
    const dimension = { confirmedFacts: ["已确认"], sourceRefs: [source], deferredItems: ["延后"], notApplicableItems: [] };
    const dimensionWire = { confirmed_facts: ["已确认"], source_refs: [sourceWire], deferred_items: ["延后"], not_applicable_items: [] };
    const assessmentDimension = { status: "partial" as const, missingItems: ["待补充"], reasons: ["证据不足"], sourceRefs: [source] };
    const assessmentDimensionWire = { status: "partial" as const, missing_items: ["待补充"], source_refs: [sourceWire] };
    const content = {
      rawInput: "完整原始需求",
      rawInputRef: source,
      clarification: {
        mode: "deep" as const,
        continueDeepConfirmed: true,
        assessmentRef: { objectType: "ai_result", objectId: "result-1", objectVersionId: null },
        assessmentSummary: "仍需澄清",
        assessment: {
          aiResultId: "result-1",
          assessmentVersion: "0.2.0",
          complexityBand: "high" as const,
          reasons: ["跨角色规则较多"],
          missingItems: ["待补充"],
          dimensions: { goal: assessmentDimension, users_and_roles: assessmentDimension, usage_scenarios: assessmentDimension, functional_scope: assessmentDimension, business_rules: assessmentDimension, exception_cases: assessmentDimension, permission_requirements: assessmentDimension, acceptance_criteria: assessmentDimension },
          missingDimensions: ["goal" as const],
          recommendedMode: "deep" as const,
          sourceRefs: [source],
        },
        rounds: [{ roundNo: 1, aiTaskId: "task-1", aiResultId: "result-1", questions: [{ questionId: "q-1", dimension: "goal" as const, questionText: "核心目标是什么？", reason: "补足目标", sourceRefs: [source] }], answers: [{ questionId: "q-1", answer: "降低返工" }] }],
        finishReason: null,
      },
      baseline: {
        assumptions: ["假设一"],
        unresolvedItems: ["未决一"],
        dimensions: { goal: dimension, users_and_roles: dimension, usage_scenarios: dimension, functional_scope: dimension, business_rules: dimension, exception_cases: dimension, permission_requirements: dimension, acceptance_criteria: dimension },
      },
    };
    const contentWire = {
      raw_input: "完整原始需求",
      raw_input_ref: sourceWire,
      clarification: {
        mode: "deep",
        continue_deep_confirmed: true,
        assessment_ref: { object_type: "ai_result", object_id: "result-1", object_version_id: null },
        assessment_summary: "仍需澄清",
        assessment: {
          ai_result_id: "result-1",
          assessment_version: "0.2.0",
          complexity_band: "high",
          complexity_reason: "跨角色规则较多",
          dimensions: { goal: assessmentDimensionWire, users_and_roles: assessmentDimensionWire, usage_scenarios: assessmentDimensionWire, functional_scope: assessmentDimensionWire, business_rules: assessmentDimensionWire, exception_cases: assessmentDimensionWire, permission_requirements: assessmentDimensionWire, acceptance_criteria: assessmentDimensionWire },
          missing_dimensions: ["goal"],
          recommended_mode: "deep",
          source_refs: [sourceWire],
        },
        rounds: [{ round_no: 1, ai_task_id: "task-1", ai_result_id: "result-1", questions: [{ question_id: "q-1", dimension: "goal", question_text: "核心目标是什么？", reason: "补足目标", source_refs: [sourceWire] }], answers: [{ question_id: "q-1", answer: "降低返工" }] }],
        finish_reason: null,
      },
      baseline: {
        assumptions: ["假设一"],
        unresolved_items: ["未决一"],
        dimensions: { goal: dimensionWire, users_and_roles: dimensionWire, usage_scenarios: dimensionWire, functional_scope: dimensionWire, business_rules: dimensionWire, exception_cases: dimensionWire, permission_requirements: dimensionWire, acceptance_criteria: dimensionWire },
      },
    };
    client.reviseRequirementVersion.mockResolvedValue(success({ id: "rv2", requirement_id: "req-1", version_no: "V2", content_hash: "d".repeat(64), content_format: "application/json", content_json: contentWire, confirmation_status: "draft", is_effective: false, source_version_id: "rv1", created_from_ai_result_id: null, unresolved_count: 1, risk_acceptances: [], created_at: "2026-08-09T00:00:00Z" }));

    const revised = await realApi.requirements.revise("rv1", { expectedVersion: 7, title: "更新需求", content, riskAcceptances: [{ missingItemCode: "goal", impact: "medium", reason: "已接受" }] });

    expect(client.reviseRequirementVersion.mock.calls[0][1]).toEqual({
      expected_version: 7,
      title: "更新需求",
      content_json: contentWire,
      risk_acceptances: [{ missing_item_code: "goal", impact: "medium", reason: "已接受" }],
    });
    expect(client.reviseRequirementVersion.mock.calls[0][1].content_json.clarification.assessment_ref.object_version_id).toBeNull();
    expect(client.reviseRequirementVersion.mock.calls[0][1].content_json.clarification.rounds[0].questions[0].source_refs[0]).toEqual(sourceWire);
    expect(revised.content.clarification.assessmentRef?.objectVersionId).toBeNull();
    expect(revised.content.clarification.rounds[0].questions[0].sourceRefs[0]).toEqual(source);
    expect(revised.content.clarification.continueDeepConfirmed).toBe(true);

    await realApi.requirements.revise("rv1", { expectedVersion: 8, content: { ...content, clarification: { ...content.clarification, continueDeepConfirmed: false } } });
    expect(client.reviseRequirementVersion.mock.calls[1][1].content_json.clarification.continue_deep_confirmed).toBe(false);
  });

  it("maps structured AI Result SourceRefs and aligned quality fields", async () => {
    const sourceWire = { source_id: "src-1", source_version_id: null, source_type: "manual", label: "原始输入", content_hash: "e".repeat(64) };
    client.getAiResult.mockResolvedValue(success({
      id: "result-1", task_public_id: "task-public-1", task_type: "requirement.clarify", target_snapshot_hash: "f".repeat(64), schema_version: "0.2.0", mode: "standard", round_no: 1, result_kind: "questions", status: "ready",
      source_refs: [sourceWire], capability_summary: { truth_label: "FORMAL_MOCK", provider_code: "formal_mock", model_code: "fixture-v1", api_key: "must-not-propagate" }, content_summary: null,
      content_json: { assessment: null, baseline: null, questions: [{ question_id: "q-1", dimension: "goal", question_text: "目标是什么？", reason: "补足目标", source_refs: [sourceWire] }], result_kind: "questions" },
      convergence: { should_finish: false, finish_reason: null, next_round_no: 2 },
      quality_summary: { format_status: "passed", traceability_status: "passed", safety_status: "passed", required_items_met: 3, required_items_total: 3, major_error: false, blocker_codes: [] },
    }));

    const result = await realApi.ai.getResult("result-1");
    expect(result.content?.questions[0].sourceRefs[0]).toEqual({ sourceId: "src-1", sourceVersionId: null, sourceType: "manual", label: "原始输入", contentHash: "e".repeat(64) });
    expect(result.quality).toEqual({ formatStatus: "passed", traceabilityStatus: "passed", safetyStatus: "passed", requiredItemsMet: 3, requiredItemsTotal: 3, majorError: false, blockerCodes: [] });
    expect(result.capabilitySummary).toEqual({ truthLabel: "FORMAL_MOCK", providerCode: "formal_mock", modelCode: "fixture-v1" });
    expect(result.capabilitySummary).not.toHaveProperty("api_key");
  });

  it("maps aligned assessment dimensions, reasons and missing items", async () => {
    const sourceWire = { source_id: "src-1", source_version_id: null, source_type: "manual", label: "原始输入", content_hash: "e".repeat(64) };
    const dimension = { status: "partial", missing_items: ["量化标准"], reasons: ["证据不足"], source_refs: [sourceWire] };
    client.getAiResult.mockResolvedValue(success({
      id: "assessment-1", task_public_id: "task-public-1", task_type: "requirement.clarify", target_snapshot_hash: "f".repeat(64), schema_version: "0.2.0", mode: "auto", round_no: 0, result_kind: "assessment", status: "ready",
      source_refs: [sourceWire], capability_summary: { truth_label: "REAL", provider_code: 42, model_code: null, internal_call_id: "must-not-propagate" }, content_summary: null,
      content_json: { assessment: { complexity_band: "medium", dimension_completeness: { goal: dimension, users_and_roles: dimension, usage_scenarios: dimension, functional_scope: dimension, business_rules: dimension, exception_cases: dimension, permission_requirements: dimension, acceptance_criteria: dimension }, missing_items: ["量化标准"], reasons: ["范围需要确认"], recommended_mode: "standard", source_refs: [sourceWire] }, baseline: null, questions: [] },
      convergence: { should_finish: false, finish_reason: null, next_round_no: 1 },
      quality_summary: { format_status: "passed", traceability_status: "passed", safety_status: "passed", required_items_met: 8, required_items_total: 8, major_error: false, blocker_codes: [] },
    }));

    const result = await realApi.ai.getResult("assessment-1");
    expect(result.resultKind).toBe("assessment");
    expect(result.content?.assessment).toMatchObject({ complexityBand: "medium", reasons: ["范围需要确认"], missingItems: ["量化标准"], recommendedMode: "standard" });
    expect(result.content?.assessment?.dimensions.goal).toEqual({ status: "partial", missingItems: ["量化标准"], reasons: ["证据不足"], sourceRefs: [{ sourceId: "src-1", sourceVersionId: null, sourceType: "manual", label: "原始输入", contentHash: "e".repeat(64) }] });
    expect(result.capabilitySummary).toEqual({ truthLabel: null, providerCode: null, modelCode: null });
    expect(result.capabilitySummary).not.toHaveProperty("internal_call_id");
  });

  it("formalizes only through the frozen adopt command and returns the durable version", async () => {
    client.formalizeAiResult.mockResolvedValue(success({ adoption_id: "adopt-1", adoption_status: "adopted", artifact_version_ref: { id: "rv2", version_no: "V2", status: "confirmed", content_hash: "d".repeat(64), created_at: "2026-08-12T00:00:00Z" } }));

    await expect(realApi.ai.formalizeBaseline("result-1", { requirementId: "req-1", expectedVersion: 1, targetSnapshotHash: "f".repeat(64) })).resolves.toEqual({ id: "rv2", versionNo: "V2", status: "confirmed", contentHash: "d".repeat(64), createdAt: "2026-08-12T00:00:00Z" });
    expect(client.formalizeAiResult.mock.calls[0][1]).toEqual({ adoption: "adopt", modification_intensity: "none", modified_content_json: null, expected_version: 1, target_object_id: "req-1", target_object_type: "requirement", target_snapshot_hash: "f".repeat(64) });
  });

  it("serializes an explicitly handled candidate only as frozen modified_adopt minor content", async () => {
    const source = { sourceId: "src-1", sourceVersionId: null, sourceType: "manual", label: "原始输入", contentHash: "c".repeat(64) };
    const dimension = { confirmedFacts: ["已确认"], sourceRefs: [source], deferredItems: [], notApplicableItems: [] };
    const baseline: RequirementBaselineView = {
      assumptions: ["假设一"],
      unresolvedItems: [],
      dimensions: { goal: dimension, users_and_roles: dimension, usage_scenarios: dimension, functional_scope: dimension, business_rules: dimension, exception_cases: dimension, permission_requirements: dimension, acceptance_criteria: dimension },
    };
    client.formalizeAiResult.mockResolvedValue(success({ adoption_id: "adopt-2", adoption_status: "adopted", artifact_version_ref: { id: "rv3", version_no: "V3", status: "draft", content_hash: "d".repeat(64), created_at: "2026-08-13T00:00:00Z" } }));

    await expect(realApi.ai.formalizeBaseline("result-2", { requirementId: "req-2", expectedVersion: 2, targetSnapshotHash: "f".repeat(64), adoption: "modified_adopt", modificationIntensity: "minor", modifiedContent: { baseline } })).resolves.toMatchObject({ id: "rv3", versionNo: "V3" });

    expect(client.formalizeAiResult.mock.calls[0][1]).toEqual({
      adoption: "modified_adopt",
      modification_intensity: "minor",
      modified_content_json: {
        baseline: {
          assumptions: ["假设一"],
          unresolved_items: [],
          dimensions: expect.objectContaining({ goal: { confirmed_facts: ["已确认"], source_refs: [{ source_id: "src-1", source_version_id: null, source_type: "manual", label: "原始输入", content_hash: "c".repeat(64) }], deferred_items: [], not_applicable_items: [] } }),
        },
      },
      expected_version: 2,
      target_object_id: "req-2",
      target_object_type: "requirement",
      target_snapshot_hash: "f".repeat(64),
    });
  });

  it("retries an ambiguous complete response with the same idempotency key without reinitializing", async () => {
    client.initFileUpload.mockResolvedValue(success({ upload_id: "upload-1", stored_file_id: "file-1", pending_file_version_id: "pending-1", upload_url: "https://storage.example/upload", http_method: "PUT", required_headers: {}, expires_at: "2026-08-03T00:00:00Z", max_size_bytes: 1024 }));
    client.completeFileUpload.mockRejectedValueOnce(new TypeError("response lost")).mockResolvedValueOnce(success({ file: { id: "file-1", logical_name: "brief.txt", current_version_id: "version-1", status: "available", version: 1 }, current_version: { id: "version-1", storage_status: "available" }, relations: [] }));
    const file = { name: "brief.txt", type: "text/plain", size: 5, arrayBuffer: async () => new TextEncoder().encode("brief").buffer } as File;

    const result = await realApi.files.upload("project-1", file);

    expect(result.status).toBe("uploaded");
    expect(client.initFileUpload).toHaveBeenCalledTimes(1);
    expect(client.completeFileUpload).toHaveBeenCalledTimes(2);
    expect(client.completeFileUpload.mock.calls[0][2]["Idempotency-Key"]).toBe(client.completeFileUpload.mock.calls[1][2]["Idempotency-Key"]);
    expect(client.abortFileUpload).not.toHaveBeenCalled();
  });

  it("creates a project idempotency key when randomUUID is unavailable", async () => {
    const getRandomValues = vi.fn((bytes: Uint8Array) => {
      bytes.fill(0);
      return bytes;
    });
    vi.stubGlobal("crypto", {
      getRandomValues,
      subtle: { digest: vi.fn(async () => new Uint8Array(32).buffer) },
    });
    client.createProject.mockResolvedValue(success({ project: { id: "project-1" }, working_version_id: "version-1" }));

    await expect(realApi.projects.create({ name: "Demo", goal: "Goal", startMode: "new" })).resolves.toEqual({ projectId: "project-1", workingVersionId: "version-1" });

    const idempotencyKey = client.createProject.mock.calls[0][1]["Idempotency-Key"];
    expect(idempotencyKey).toMatch(/^web-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(getRandomValues).toHaveBeenCalledOnce();
  });

  it("maps Test Record CRUD/submit and keeps command idempotency headers", async () => {
    const record = { id: "record-1", confirmation_round_id: "round-1", title: "登录验证", scope: "登录流程", environment: { name: "local", preconditions: ["服务已启动"] }, steps: ["输入账号", "提交"], expected_result: "进入首页", actual_result: "进入首页", result_status: "success", tester_id: "tester-1", status: "draft", submitted_at: null, row_version: 1, test_type: "manual", created_at: "2026-08-24T00:00:00Z", updated_at: "2026-08-24T00:00:00Z" } as const;
    client.listConfirmationRoundTestRecords.mockResolvedValue(success({ items: [record] }));
    client.createConfirmationRoundTestRecord.mockResolvedValue(success({ test_record: record }));
    client.getTestRecord.mockResolvedValue(success({ test_record: record }));
    client.updateTestRecordDraft.mockResolvedValue(success({ test_record: { ...record, row_version: 2 } }));
    client.submitTestRecord.mockResolvedValue(success({ test_record: { ...record, status: "submitted", submitted_at: "2026-08-24T00:01:00Z", row_version: 3 } }));

    await expect(realApi.testRecords.list("round-1")).resolves.toMatchObject([{ id: "record-1", environment: { name: "local" } }]);
    await expect(realApi.testRecords.create("round-1", { title: record.title, scope: record.scope, environment: { name: record.environment.name, preconditions: [...record.environment.preconditions] }, steps: [...record.steps], expectedResult: record.expected_result, actualResult: record.actual_result, resultStatus: record.result_status })).resolves.toMatchObject({ id: "record-1", rowVersion: 1 });
    await expect(realApi.testRecords.get("record-1")).resolves.toMatchObject({ id: "record-1" });
    await expect(realApi.testRecords.update("record-1", { expectedVersion: 1, actualResult: "进入首页" })).resolves.toMatchObject({ rowVersion: 2 });
    await expect(realApi.testRecords.submit("record-1", 2)).resolves.toMatchObject({ status: "submitted", submittedAt: "2026-08-24T00:01:00Z" });
    expect(client.createConfirmationRoundTestRecord.mock.calls[0][2]).toEqual(expect.objectContaining({ "Idempotency-Key": expect.stringMatching(/^web-/) }));
    expect(client.submitTestRecord.mock.calls[0][2]).toEqual(expect.objectContaining({ "Idempotency-Key": expect.stringMatching(/^web-/) }));
    expect(client.updateTestRecordDraft.mock.calls[0][1]).toEqual({ expected_version: 1, actual_result: "进入首页" });
  });
});
