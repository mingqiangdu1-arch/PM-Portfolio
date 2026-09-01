import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { ImplementationPlanWorkspace } from "./implementation-plan-workspace";
import { capabilitiesForRoles, PortError, type DesignReviewView, type FrontendApi, type ImplementationPlanView, type PrdView } from "@/lib/api/ports";

const content = { schemaVersion: "implementation_plan.mvp3.v1" as const, features: [{ key: "feature", description: "A feature" }], businessRules: [], stateRequirements: [], exceptions: [], interactions: [], dependencies: [], acceptanceScope: [{ key: "acceptance", description: "An acceptance rule" }] };

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => { resolve = resolvePromise; });
  return { promise, resolve };
}

describe("ImplementationPlanWorkspace", () => {
  it("automatically binds the exact confirmed PRD review context without internal ID inputs", async () => {
    const prd: PrdView = { id: "prd-1", projectVersionId: "atlas-v2", sourceRequirementVersionId: "req-v1", name: "Atlas PRD", status: "confirmed", currentVersionId: "prd-v1", rowVersion: 4 };
    const review: DesignReviewView = { id: "review-1", projectVersionId: "atlas-v2", roundNo: 2, rowVersion: 2, status: "passed", summary: null, prdId: "prd-1", prdVersionId: "prd-v1", contentHash: "a".repeat(64) };
    const create = vi.fn().mockResolvedValue({ id: "plan-1", projectVersionId: "atlas-v2", sourcePrdVersionId: "prd-v1", sourceDesignReviewId: "review-1", name: "实施计划", status: "draft", currentVersionId: null, effectiveVersionId: null, rowVersion: 1, confirmationState: "not_ready", versions: [] });
    const api = { projects: { overview: vi.fn().mockResolvedValue({ capabilities: capabilitiesForRoles(["owner"]) }) }, prds: { list: vi.fn().mockResolvedValue([prd]), get: vi.fn().mockResolvedValue({ prd, review }) }, implementationPlans: { list: vi.fn().mockResolvedValue([]), create, get: vi.fn().mockResolvedValue({}) } } as unknown as FrontendApi;
    render(<ImplementationPlanWorkspace projectId="atlas" projectVersionId="atlas-v2" api={api} />);
    expect(await screen.findByText("Atlas PRD · 设计评审第 2 轮已通过")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Review ID|Version ID/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("计划名称"), { target: { value: "实施计划" } });
    fireEvent.click(screen.getByRole("button", { name: "创建计划" }));
    await waitFor(() => expect(create).toHaveBeenCalledWith("atlas-v2", { name: "实施计划", sourcePrdVersionId: "prd-v1", sourceDesignReviewId: "review-1" }));
  });

  it("loads summary then full detail before enabling save, and preserves the local edit on success", async () => {
    const detail = deferred<ImplementationPlanView>();
    const plan: ImplementationPlanView = { id: "plan-1", projectVersionId: "atlas-v2", sourcePrdVersionId: "prd-v1", sourceDesignReviewId: "review-1", name: "Atlas 实现计划", status: "active", currentVersionId: "plan-version-1", effectiveVersionId: "plan-version-1", rowVersion: 2, confirmationState: "needs_confirmation", versions: [{ id: "plan-version-1", implementationPlanId: "plan-1", sourceVersionId: null, versionNo: "V1", reviewId: "review-1", content, contentHash: "p".repeat(64), changeNote: "first", isEffective: true, createdBy: "user-1", createdAt: "2026-08-24T00:00:00Z" }] };
    const saveVersion = vi.fn().mockResolvedValue({ version: { ...plan.versions[0], id: "plan-version-2", versionNo: "V2", sourceVersionId: "plan-version-1", isEffective: false }, planRowVersion: 3 });
    const api = { projects: { overview: vi.fn().mockResolvedValue({ capabilities: capabilitiesForRoles(["owner"]) }) }, implementationPlans: { list: vi.fn().mockResolvedValue([{ ...plan, versions: [] }]), get: vi.fn().mockReturnValue(detail.promise), saveVersion } } as unknown as FrontendApi;

    render(<ImplementationPlanWorkspace projectId="atlas" projectVersionId="atlas-v2" api={api} />);
    expect(await screen.findByRole("heading", { name: "实施计划工作台" })).toBeInTheDocument();
    await waitFor(() => expect(api.implementationPlans.get).toHaveBeenCalledWith("plan-1"));
    expect(screen.getByRole("button", { name: "保存不可变版本" })).toBeDisabled();
    detail.resolve(plan);
    await waitFor(() => expect(screen.getByDisplayValue(/implementation_plan\.mvp3\.v1/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "保存不可变版本" })).toBeEnabled();
    fireEvent.change(screen.getByLabelText("变更说明"), { target: { value: "补充实现边界与验收说明" } });
    fireEvent.click(screen.getByRole("button", { name: "保存不可变版本" }));
    await waitFor(() => expect(screen.getByText(/已保存为不可变版本/)).toBeInTheDocument());
    expect(saveVersion).toHaveBeenCalledWith("plan-1", expect.objectContaining({ expectedVersion: 2, changeNote: "补充实现边界与验收说明" }));
  });

  it("normalizes legacy string items before saving", async () => {
    const plan: ImplementationPlanView = { id: "plan-legacy", projectVersionId: "atlas-v2", sourcePrdVersionId: "prd-v1", sourceDesignReviewId: "review-1", name: "Legacy Plan", status: "draft", currentVersionId: null, effectiveVersionId: null, rowVersion: 1, confirmationState: "not_ready", versions: [{ id: "plan-version-1", implementationPlanId: "plan-legacy", sourceVersionId: null, versionNo: "V1", reviewId: "review-1", content, contentHash: "p".repeat(64), changeNote: "first", isEffective: true, createdBy: "user-1", createdAt: "2026-08-24T00:00:00Z" }] };
    const saveVersion = vi.fn().mockResolvedValue({ version: { ...plan.versions[0], id: "plan-version-2", versionNo: "V2" }, planRowVersion: 2 });
    const api = { projects: { overview: vi.fn().mockResolvedValue({ capabilities: capabilitiesForRoles(["owner"]) }) }, implementationPlans: { list: vi.fn().mockResolvedValue([{ ...plan, versions: [] }]), get: vi.fn().mockResolvedValue(plan), saveVersion } } as unknown as FrontendApi;
    render(<ImplementationPlanWorkspace projectId="atlas" projectVersionId="atlas-v2" api={api} />);
    await waitFor(() => expect(screen.getByDisplayValue(/implementation_plan\.mvp3\.v1/)).toBeInTheDocument());
    const legacyContent = JSON.parse(JSON.stringify({ ...content, features: ["支持字符串形式的历史计划项"], businessRules: ["保留业务规则"], acceptanceScope: ["完成保存验收"] })) as unknown;
    fireEvent.change(screen.getByLabelText("计划内容（JSON）"), { target: { value: JSON.stringify(legacyContent) } });
    fireEvent.change(screen.getByLabelText("变更说明"), { target: { value: "兼容历史计划内容格式" } });
    fireEvent.click(screen.getByRole("button", { name: "保存不可变版本" }));
    await waitFor(() => expect(screen.getByText(/已保存为不可变版本/)).toBeInTheDocument());
    expect(saveVersion).toHaveBeenCalledWith("plan-legacy", expect.objectContaining({ content: expect.objectContaining({ features: [{ key: "features_1", description: "支持字符串形式的历史计划项" }], businessRules: [{ key: "business_rules_1", description: "保留业务规则" }] }) }));
  });

  it("keeps local content and exposes retry after a detail conflict/failure", async () => {
    const plan: ImplementationPlanView = { id: "plan-2", projectVersionId: "atlas-v2", sourcePrdVersionId: "prd-v1", sourceDesignReviewId: "review-1", name: "Plan 2", status: "draft", currentVersionId: null, effectiveVersionId: null, rowVersion: 1, confirmationState: "not_ready", versions: [] };
    const get = vi.fn().mockRejectedValueOnce(new Error("VERSION_CONFLICT")).mockResolvedValue(plan);
    const api = { projects: { overview: vi.fn().mockResolvedValue({ capabilities: capabilitiesForRoles(["owner"]) }) }, implementationPlans: { list: vi.fn().mockResolvedValue([{ ...plan, versions: [] }]), get } } as unknown as FrontendApi;
    render(<ImplementationPlanWorkspace projectId="atlas" projectVersionId="atlas-v2" api={api} />);
    await screen.findByText("计划详情加载失败");
    expect(screen.getByRole("button", { name: "重试读取详情" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试读取详情" }));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect(screen.getByText("尚未保存版本。")).toBeInTheDocument();
  });

  it("clears version content when switching from a versioned Plan to a no-version Plan", async () => {
    const first: ImplementationPlanView = { id: "plan-versioned", projectVersionId: "atlas-v2", sourcePrdVersionId: "prd-v1", sourceDesignReviewId: "review-1", name: "Versioned Plan", status: "active", currentVersionId: "version-1", effectiveVersionId: "version-1", rowVersion: 2, confirmationState: "needs_confirmation", versions: [{ id: "version-1", implementationPlanId: "plan-versioned", sourceVersionId: null, versionNo: "V1", reviewId: "review-1", content, contentHash: "p".repeat(64), changeNote: "first", isEffective: true, createdBy: "user-1", createdAt: "2026-08-24T00:00:00Z" }] };
    const empty: ImplementationPlanView = { id: "plan-empty", projectVersionId: "atlas-v2", sourcePrdVersionId: "prd-v2", sourceDesignReviewId: "review-2", name: "Empty Plan", status: "draft", currentVersionId: null, effectiveVersionId: null, rowVersion: 1, confirmationState: "not_ready", versions: [] };
    const secondDetail = deferred<ImplementationPlanView>();
    const get = vi.fn().mockImplementation((id: string) => id === first.id ? Promise.resolve(first) : secondDetail.promise);
    const saveVersion = vi.fn();
    const api = { projects: { overview: vi.fn().mockResolvedValue({ capabilities: capabilitiesForRoles(["owner"]) }) }, implementationPlans: { list: vi.fn().mockResolvedValue([{ ...first, versions: [] }, { ...empty, versions: [] }]), get, saveVersion } } as unknown as FrontendApi;
    render(<ImplementationPlanWorkspace projectId="atlas" projectVersionId="atlas-v2" api={api} />);
    await waitFor(() => expect(screen.getByDisplayValue(/implementation_plan\.mvp3\.v1/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Empty Plan/ }));
    await waitFor(() => expect(get).toHaveBeenCalledWith("plan-empty"));
    expect(screen.getByRole("button", { name: "保存不可变版本" })).toBeDisabled();
    secondDetail.resolve(empty);
    await waitFor(() => expect(screen.getByText("尚未保存版本。")).toBeInTheDocument());
    expect(screen.getByLabelText("计划内容（JSON）")).toHaveValue("");
    fireEvent.click(screen.getByRole("button", { name: "保存不可变版本" }));
    expect(saveVersion).not.toHaveBeenCalled();
  });

  it("preserves valid local content and change note on VERSION_CONFLICT without false success", async () => {
    const plan: ImplementationPlanView = { id: "plan-conflict", projectVersionId: "atlas-v2", sourcePrdVersionId: "prd-v1", sourceDesignReviewId: "review-1", name: "Conflict Plan", status: "active", currentVersionId: "version-1", effectiveVersionId: "version-1", rowVersion: 7, confirmationState: "needs_confirmation", versions: [{ id: "version-1", implementationPlanId: "plan-conflict", sourceVersionId: null, versionNo: "V1", reviewId: "review-1", content, contentHash: "p".repeat(64), changeNote: "first", isEffective: true, createdBy: "user-1", createdAt: "2026-08-24T00:00:00Z" }] };
    const editedContent = JSON.stringify({ ...content, features: [{ key: "feature", description: "Edited feature boundary" }] }, null, 2);
    const changeNote = "保留本地变更并等待重新加载";
    const saveVersion = vi.fn().mockRejectedValue(new PortError("CONFLICT", "版本冲突，请重新加载后重试。", 409, "trace-conflict", [], "VERSION_CONFLICT"));
    const setEffective = vi.fn();
    const api = { projects: { overview: vi.fn().mockResolvedValue({ capabilities: capabilitiesForRoles(["owner"]) }) }, implementationPlans: { list: vi.fn().mockResolvedValue([{ ...plan, versions: [] }]), get: vi.fn().mockResolvedValue(plan), saveVersion, setEffective } } as unknown as FrontendApi;
    render(<ImplementationPlanWorkspace projectId="atlas" projectVersionId="atlas-v2" api={api} />);
    await waitFor(() => expect(screen.getByDisplayValue(/implementation_plan\.mvp3\.v1/)).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("计划内容（JSON）"), { target: { value: editedContent } });
    fireEvent.change(screen.getByLabelText("变更说明"), { target: { value: changeNote } });
    fireEvent.click(screen.getByRole("button", { name: "保存不可变版本" }));
    await waitFor(() => expect(screen.getByText(/版本冲突/)).toBeInTheDocument());
    expect(screen.getByLabelText("计划内容（JSON）")).toHaveValue(editedContent);
    expect(screen.getByLabelText("变更说明")).toHaveValue(changeNote);
    expect(screen.queryByText(/已保存为不可变版本/)).not.toBeInTheDocument();
    expect(screen.queryByText(/当前版本已设为有效版本/)).not.toBeInTheDocument();
    expect(setEffective).not.toHaveBeenCalled();
  });
});
