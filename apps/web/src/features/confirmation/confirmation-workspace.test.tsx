import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { ConfirmationWorkspace } from "./confirmation-workspace";
import { capabilitiesForRoles, type ConfirmationRoundView, type FrontendApi, type ImplementationPlanView, type ProjectRole } from "@/lib/api/ports";

const plan: ImplementationPlanView = { id: "plan-1", projectVersionId: "atlas-v2", sourcePrdVersionId: "prd-v1", sourceDesignReviewId: "review-1", name: "Atlas 实现计划", status: "active", currentVersionId: "plan-version-1", effectiveVersionId: "plan-version-1", rowVersion: 3, confirmationState: "needs_reconfirmation", versions: [{ id: "plan-version-1", implementationPlanId: "plan-1", sourceVersionId: null, versionNo: "V1", reviewId: "review-1", content: { schemaVersion: "implementation_plan.mvp3.v1", features: [{ key: "feature", description: "A feature" }], businessRules: [], stateRequirements: [], exceptions: [], interactions: [], dependencies: [], acceptanceScope: [{ key: "acceptance", description: "An acceptance rule" }] }, contentHash: "p".repeat(64), changeNote: "first", isEffective: true, createdBy: "user-1", createdAt: "2026-08-24T00:00:00Z" }] };
const priorRound: ConfirmationRoundView = { id: "round-1", implementationPlanId: "plan-1", planVersionId: "plan-version-1", sourceRoundId: null, roundNo: 1, status: "confirmed", confirmStatus: "confirmed", implementationSummary: "上一轮已经确认的实现范围摘要", readiness: { schemaVersion: "implementation_confirmation.readiness.mvp3.v1", scopeStatus: "ready", implementationStatus: "ready", configurationStatus: "not_applicable", dataChangeStatus: "not_applicable", knownBlockers: [] }, rowVersion: 2, isEffective: false, confirmedBy: "owner-1", confirmedAt: "2026-08-24T00:00:00Z", supersededAt: null };

function apiFor(role: ProjectRole) {
  const create = vi.fn().mockResolvedValue({ ...priorRound, id: "round-2", roundNo: 2, sourceRoundId: "round-1", status: "draft", confirmStatus: null, isEffective: false, rowVersion: 1 });
  const api = { projects: { overview: vi.fn().mockResolvedValue({ capabilities: capabilitiesForRoles([role]) }) }, implementationPlans: { get: vi.fn().mockResolvedValue(plan) }, confirmationRounds: { list: vi.fn().mockResolvedValue([priorRound]), create, updateDraft: vi.fn(), confirm: vi.fn() } } as unknown as FrontendApi;
  return { api, create };
}

describe("ConfirmationWorkspace", () => {
  it("allows Round 2 draft creation after confirmed history when reconfirmation is required", async () => {
    const { api, create } = apiFor("owner");
    render(<ConfirmationWorkspace projectId="atlas" planId="plan-1" api={api} />);
    expect(await screen.findByRole("button", { name: /第 1 轮/ })).toBeInTheDocument();
    expect(screen.getByText("历史只读")).toBeInTheDocument();
    const summary = "本轮覆盖实现边界、配置检查与数据变更说明";
    fireEvent.change(screen.getAllByLabelText("实现范围摘要")[0], { target: { value: summary } });
    fireEvent.click(screen.getByRole("button", { name: "创建确认草稿" }));
    await waitFor(() => expect(create).toHaveBeenCalledWith("plan-1", expect.objectContaining({ planVersionId: "plan-version-1", implementationSummary: summary })));
    expect(screen.getByText("确认草稿已创建；只有项目负责人可以最终确认。")).toBeInTheDocument();
  });

  it("re-lists authoritative history after confirm and renders supersession", async () => {
    const superseded = { ...priorRound, status: "superseded" as const, isEffective: false, supersededAt: "2026-08-24T01:00:00Z" };
    const draft = { ...priorRound, id: "round-2", roundNo: 2, sourceRoundId: "round-1", status: "draft" as const, confirmStatus: null, isEffective: false, rowVersion: 1 };
    const confirmed = { ...draft, status: "confirmed" as const, confirmStatus: "confirmed" as const, isEffective: true, confirmedBy: "owner-1", confirmedAt: "2026-08-24T01:00:00Z", rowVersion: 2 };
    const list = vi.fn().mockResolvedValueOnce([priorRound, draft]).mockResolvedValueOnce([superseded, confirmed]);
    const api = { projects: { overview: vi.fn().mockResolvedValue({ capabilities: capabilitiesForRoles(["owner"]) }) }, implementationPlans: { get: vi.fn().mockResolvedValue({ ...plan, confirmationState: "needs_confirmation" }) }, confirmationRounds: { list, create: vi.fn(), updateDraft: vi.fn(), confirm: vi.fn().mockResolvedValue(confirmed) } } as unknown as FrontendApi;
    render(<ConfirmationWorkspace projectId="atlas" planId="plan-1" api={api} />);
    await screen.findByRole("button", { name: "项目负责人最终确认" });
    fireEvent.click(screen.getByRole("button", { name: "项目负责人最终确认" }));
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    expect(screen.getByText("已替代")).toBeInTheDocument();
    expect(screen.getByText(/已确认 · 已绑定实施计划版本/)).toBeInTheDocument();
  });

  it("preserves draft input and exposes conflict/readiness recovery without false success", async () => {
    const draft = { ...priorRound, id: "round-draft", status: "draft" as const, confirmStatus: null, isEffective: false, rowVersion: 4 };
    const api = { projects: { overview: vi.fn().mockResolvedValue({ capabilities: capabilitiesForRoles(["owner"]) }) }, implementationPlans: { get: vi.fn().mockResolvedValue({ ...plan, confirmationState: "needs_confirmation" }) }, confirmationRounds: { list: vi.fn().mockResolvedValue([draft]), create: vi.fn(), updateDraft: vi.fn().mockRejectedValue(new Error("VERSION_CONFLICT")), confirm: vi.fn().mockRejectedValue(new Error("READINESS_INCOMPLETE")) } } as unknown as FrontendApi;
    render(<ConfirmationWorkspace projectId="atlas" planId="plan-1" api={api} />);
    await screen.findByRole("button", { name: "保存草稿" });
    const input = screen.getAllByLabelText("实现范围摘要")[0];
    const local = "本地未保存的实现范围摘要，冲突后仍需保留";
    fireEvent.change(input, { target: { value: local } });
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
    await waitFor(() => expect(screen.getByText(/VERSION_CONFLICT/)).toBeInTheDocument());
    expect(input).toHaveValue(local);
    const confirmButton = screen.getByRole("button", { name: "项目负责人最终确认" });
    expect(confirmButton).toBeDisabled();
    fireEvent.click(confirmButton);
    expect(api.confirmationRounds.confirm).not.toHaveBeenCalled();
    expect(screen.queryByText("确认轮次已正式确认。")).not.toBeInTheDocument();
  });

  it("blocks Owner confirmation until persisted readiness is complete", async () => {
    const draft = { ...priorRound, id: "round-incomplete", status: "draft" as const, confirmStatus: null, isEffective: false, rowVersion: 1, readiness: { ...priorRound.readiness, scopeStatus: "not_ready" as const, implementationStatus: "not_ready" as const } };
    const confirm = vi.fn();
    const api = { projects: { overview: vi.fn().mockResolvedValue({ capabilities: capabilitiesForRoles(["owner"]) }) }, implementationPlans: { get: vi.fn().mockResolvedValue({ ...plan, confirmationState: "needs_confirmation" }) }, confirmationRounds: { list: vi.fn().mockResolvedValue([draft]), create: vi.fn(), updateDraft: vi.fn(), confirm } } as unknown as FrontendApi;
    render(<ConfirmationWorkspace projectId="atlas" planId="plan-1" api={api} />);
    const button = await screen.findByRole("button", { name: "项目负责人最终确认" });
    expect(button).toBeDisabled();
    expect(screen.getByText(/scopeStatus 必须为 ready/)).toBeInTheDocument();
    fireEvent.click(button);
    expect(confirm).not.toHaveBeenCalled();
  });

  it.each([["owner", true], ["implementer", true], ["reviewer", false]] as const)("exposes frozen confirmation capability for %s", async (role, enabled) => {
    const { api } = apiFor(role);
    render(<ConfirmationWorkspace projectId="atlas" planId="plan-1" api={api} />);
    await screen.findByRole("button", { name: /第 1 轮/ });
    expect(screen.getByRole("button", { name: "创建确认草稿" })).toHaveProperty("disabled", !enabled);
    if (!enabled) expect(screen.getByText("当前身份只读")).toBeInTheDocument();
  });

  it("keeps confirmed history readonly and shows readiness semantics", async () => {
    const { api } = apiFor("implementer");
    render(<ConfirmationWorkspace projectId="atlas" planId="plan-1" api={api} />);
    await screen.findByRole("button", { name: /第 1 轮/ });
    expect(screen.getByText("历史只读")).toBeInTheDocument();
    expect(screen.getByText(/不等同于测试通过/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "项目负责人最终确认" })).toBeDisabled();
  });
});
