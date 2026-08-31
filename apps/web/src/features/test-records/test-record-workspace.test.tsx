import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { TestRecordWorkspace } from "./test-record-workspace";
import { capabilitiesForRoles, type ConfirmationRoundView, type FrontendApi, type TestRecordView } from "@/lib/api/ports";

const round: ConfirmationRoundView = { id: "round-1", implementationPlanId: "plan-1", planVersionId: "plan-version-1", sourceRoundId: null, roundNo: 1, status: "confirmed", confirmStatus: "confirmed", implementationSummary: "已确认的实现范围", readiness: { schemaVersion: "implementation_confirmation.readiness.mvp3.v1", scopeStatus: "ready", implementationStatus: "ready", configurationStatus: "not_applicable", dataChangeStatus: "not_applicable", knownBlockers: [] }, rowVersion: 3, isEffective: true, confirmedBy: "owner-1", confirmedAt: "2026-08-24T00:00:00Z", supersededAt: null };
const record: TestRecordView = { id: "record-1", projectId: "project-1", projectVersionId: "version-1", confirmationRoundId: "round-1", title: "登录验证", scope: "登录流程", environment: { name: "local", preconditions: ["服务已启动"] }, steps: ["输入账号", "提交"], expectedResult: "进入首页", actualResult: "进入首页", resultStatus: "success", testerId: "tester-1", status: "draft", submittedAt: null, rowVersion: 1, noIssueConclusion: false, testType: "manual", createdAt: "2026-08-24T00:00:00Z", updatedAt: "2026-08-24T00:00:00Z" };

function apiFor(overrides: Partial<FrontendApi["testRecords"]> = {}) {
  const testRecords = { list: vi.fn().mockResolvedValue([]), create: vi.fn().mockResolvedValue(record), get: vi.fn().mockResolvedValue(record), update: vi.fn().mockResolvedValue({ ...record, rowVersion: 2 }), submit: vi.fn().mockResolvedValue({ ...record, status: "submitted" as const, submittedAt: "2026-08-24T00:01:00Z", rowVersion: 3 }), concludeNoIssue: vi.fn().mockResolvedValue({ ...record, status: "submitted" as const, submittedAt: "2026-08-24T00:01:00Z", rowVersion: 4, noIssueConclusion: true }), ...overrides };
  const issues = { list: vi.fn().mockResolvedValue([]), create: vi.fn(), get: vi.fn(), update: vi.fn(), dispose: vi.fn() };
  return { api: { testRecords, issues } as unknown as FrontendApi, testRecords, issues };
}

describe("TestRecordWorkspace", () => {
  it("creates, saves and submits a draft with expected version", async () => {
    const { api, testRecords } = apiFor();
    render(<TestRecordWorkspace round={round} capabilities={capabilitiesForRoles(["tester"])} api={api} />);
    await screen.findByText("尚无测试记录");
    fireEvent.change(screen.getByLabelText("记录标题"), { target: { value: "登录验证" } });
    fireEvent.change(screen.getByLabelText("测试范围"), { target: { value: "登录流程" } });
    fireEvent.change(screen.getByLabelText(/测试步骤/), { target: { value: "输入账号\n提交" } });
    fireEvent.change(screen.getByLabelText("预期结果"), { target: { value: "进入首页" } });
    fireEvent.change(screen.getByLabelText("实际结果"), { target: { value: "进入首页" } });
    fireEvent.click(screen.getByRole("button", { name: "创建草稿" }));
    await waitFor(() => expect(testRecords.create).toHaveBeenCalledWith("round-1", expect.objectContaining({ steps: ["输入账号", "提交"] })));
    await screen.findByText("编辑测试记录草稿");
    fireEvent.change(screen.getByLabelText("实际结果"), { target: { value: "进入首页并显示欢迎语" } });
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
    await waitFor(() => expect(testRecords.update).toHaveBeenCalledWith("record-1", expect.objectContaining({ expectedVersion: 1, actualResult: "进入首页并显示欢迎语" })));
    fireEvent.click(screen.getByRole("button", { name: "提交并冻结" }));
    await waitFor(() => expect(testRecords.submit).toHaveBeenCalledWith("record-1", 2));
    expect(await screen.findByText("已提交记录（只读）")).toBeInTheDocument();
  });

  it("allows an incomplete draft to be created and saved, while keeping result labels user-facing", async () => {
    const { api, testRecords } = apiFor();
    render(<TestRecordWorkspace round={round} capabilities={capabilitiesForRoles(["tester"])} api={api} />);
    await screen.findByText("尚无测试记录");
    fireEvent.change(screen.getByLabelText("记录标题"), { target: { value: "最小草稿" } });
    fireEvent.click(screen.getByRole("button", { name: "创建草稿" }));
    await waitFor(() => expect(testRecords.create).toHaveBeenCalledWith("round-1", expect.objectContaining({ title: "最小草稿", scope: "", steps: [], expectedResult: "", actualResult: "" })));
    expect(screen.getByRole("option", { name: "通过" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "未通过" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "部分完成" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("测试范围"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
    await waitFor(() => expect(testRecords.update).toHaveBeenCalledWith("record-1", expect.objectContaining({ expectedVersion: 1, scope: "" })));
  });

  it("reads historical rounds and reopens a record through GET without enabling writes", async () => {
    const historical = { ...round, status: "superseded" as const, isEffective: false };
    const reopened = { ...record, status: "submitted" as const, actualResult: "重新读取的持久化事实", submittedAt: "2026-08-24T00:01:00Z" };
    const { api, testRecords } = apiFor({ list: vi.fn().mockResolvedValue([reopened]), get: vi.fn().mockResolvedValue(reopened) });
    render(<TestRecordWorkspace round={historical} capabilities={capabilitiesForRoles(["owner"])} api={api} />);
    expect(await screen.findByText("历史确认轮次（只读）")).toBeInTheDocument();
    expect(testRecords.list).toHaveBeenCalledWith("round-1");
    fireEvent.click(screen.getByRole("button", { name: /登录验证/ }));
    await waitFor(() => expect(testRecords.get).toHaveBeenCalledWith("record-1"));
    expect(await screen.findByDisplayValue("重新读取的持久化事实")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "保存草稿" })).not.toBeInTheDocument();
  });

  it("uses the complete role set: reviewer plus tester can write, reviewer alone cannot", async () => {
    const writable = apiFor();
    render(<TestRecordWorkspace round={round} capabilities={capabilitiesForRoles(["reviewer", "tester"])} api={writable.api} />);
    expect(await screen.findByRole("button", { name: "创建草稿" })).toBeEnabled();
  });

  it("does not offer mutation controls to reviewers and keeps submitted records readonly", async () => {
    const { api } = apiFor({ list: vi.fn().mockResolvedValue([{ ...record, status: "submitted", submittedAt: "2026-08-24T00:01:00Z" }]) });
    render(<TestRecordWorkspace round={round} capabilities={capabilitiesForRoles(["reviewer"])} api={api} />);
    expect(await screen.findByText("当前身份只读")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "提交并冻结" })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByDisplayValue("进入首页").every((field) => field.hasAttribute("disabled"))).toBe(true));
  });

  it("makes the no-Issue decision explicit and reaches Validation Complete", async () => {
    const submitted = { ...record, status: "submitted" as const, submittedAt: "2026-08-24T00:01:00Z", rowVersion: 3 };
    const { api, testRecords, issues } = apiFor({ list: vi.fn().mockResolvedValue([submitted]) });
    render(<TestRecordWorkspace round={round} capabilities={capabilitiesForRoles(["tester"])} api={api} />);
    const action = await screen.findByRole("button", { name: "确认无问题，完成验证" });
    await waitFor(() => expect(issues.list).toHaveBeenCalledWith("version-1"));
    fireEvent.click(action);
    await waitFor(() => expect(testRecords.concludeNoIssue).toHaveBeenCalledWith("record-1", 3));
    expect(await screen.findByText("验证已完成")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "创建问题" })).not.toBeInTheDocument();
  });
});
