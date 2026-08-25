import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { IssueWorkspace } from "./issue-workspace";
import { capabilitiesForRoles, type FrontendApi, type IssueView, type TestRecordView } from "@/lib/api/ports";


const record: TestRecordView = {
  id: "record-1", projectId: "project-1", projectVersionId: "version-1", confirmationRoundId: "round-1",
  title: "登录验证", scope: "登录流程", environment: { name: "local", preconditions: [] }, steps: ["submit"],
  expectedResult: "saved", actualResult: "error", resultStatus: "failed", testerId: "tester-1", status: "submitted",
  submittedAt: "2026-08-25T00:00:00Z", rowVersion: 2, noIssueConclusion: false, testType: "manual",
  createdAt: "2026-08-25T00:00:00Z", updatedAt: "2026-08-25T00:00:00Z",
};

const openIssue: IssueView = {
  id: "issue-1", projectVersionId: "version-1", testRecordId: "record-1", sourceType: "test_record", issueType: "defect",
  title: "提交失败", description: "提交后返回错误", priority: "high", severity: "high", status: "open_needs_disposition",
  assigneeId: null, rowVersion: 1,
  bugDetail: { reproduceSteps: "submit", expectedResult: "saved", actualResult: "error", environment: null },
  optimizationDetail: null, dispositions: [], createdAt: "2026-08-25T00:00:00Z", updatedAt: "2026-08-25T00:00:00Z",
};


it("creates a conditionally valid defect and records owner disposition", async () => {
  const issues = {
    list: vi.fn().mockResolvedValue([]),
    create: vi.fn().mockResolvedValue(openIssue),
    get: vi.fn().mockResolvedValue(openIssue),
    update: vi.fn().mockResolvedValue(openIssue),
    dispose: vi.fn().mockResolvedValue({ ...openIssue, status: "routed_current_fix" as const, rowVersion: 2 }),
  };
  const api = { issues } as unknown as FrontendApi;
  const presence = vi.fn();
  render(<IssueWorkspace projectId="project-1" projectVersionId="version-1" record={record} capabilities={capabilitiesForRoles(["owner"])} api={api} onIssuePresenceChange={presence} />);

  await screen.findByText("尚无 Issue");
  fireEvent.click(screen.getByRole("button", { name: "创建 Issue" }));
  fireEvent.change(screen.getByLabelText("Title"), { target: { value: "提交失败" } });
  fireEvent.change(screen.getByLabelText("Description"), { target: { value: "提交后返回错误" } });
  fireEvent.change(screen.getByLabelText("Priority"), { target: { value: "high" } });
  fireEvent.change(screen.getByLabelText("Severity"), { target: { value: "high" } });
  fireEvent.change(screen.getByLabelText("Reproduce steps"), { target: { value: "submit" } });
  fireEvent.change(screen.getByLabelText("Expected result"), { target: { value: "saved" } });
  fireEvent.change(screen.getByLabelText("Actual result"), { target: { value: "error" } });
  fireEvent.click(screen.getByRole("button", { name: "保存 Issue" }));

  await waitFor(() => expect(issues.create).toHaveBeenCalledWith("version-1", expect.objectContaining({
    testRecordId: "record-1", issueType: "defect", bugDetail: expect.objectContaining({ reproduceSteps: "submit" }), optimizationDetail: null,
  })));
  expect(presence).toHaveBeenLastCalledWith(true);
  fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "在当前版本修复" } });
  fireEvent.change(screen.getByLabelText("Responsible user ID"), { target: { value: "7" } });
  fireEvent.click(screen.getByRole("button", { name: "当前版本修正" }));
  await waitFor(() => expect(issues.dispose).toHaveBeenCalledWith("issue-1", 1, "current_version_fix", "在当前版本修复", "7"));
  expect(await screen.findByText(/请创建新的 Confirmation Round/)).toBeInTheDocument();
});
