import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi } from "@/lib/api/mock-adapter";
import { PortError } from "@/lib/api/ports";
import type { DesignReviewView, FrontendApi, PrdVersionView, PrdView } from "@/lib/api/ports";
import { PrdWorkbench } from "./prd-workbench";

const confirmedRequirement = { id: "req-1", title: "已确认需求", projectVersionId: "pv-1", status: "effective" as const, sourceType: "manual" as const, priority: "normal" as const, currentVersionId: "req-v2", effectiveVersionId: "req-v2", version: 2, updatedAt: "2026-08-22T00:00:00Z" };

function createApi(): FrontendApi {
  let prd: PrdView | null = null;
  let version: PrdVersionView | null = null;
  let review: DesignReviewView | null = null;
  let round = 0;
  return {
    ...mockApi,
    requirements: { ...mockApi.requirements, list: async () => [confirmedRequirement] },
    prds: {
      async list() { return prd ? [prd] : []; },
      async create(projectVersionId, input) { prd = { id: "prd-1", projectVersionId, sourceRequirementVersionId: input.sourceRequirementVersionId, name: input.name, status: "draft", rowVersion: 1, currentVersionId: null }; return prd; },
      async get() { if (!prd) throw new Error("missing prd"); return { prd, review }; },
      async getVersion() { if (!version) throw new Error("missing version"); return version; },
      async saveVersion(_prdId, input) { if (!prd || prd.rowVersion !== input.expectedVersion) throw new PortError("CONFLICT", "版本冲突", 409, undefined, [], "VERSION_CONFLICT"); const number = version ? "V2" : "V1"; version = { id: `prd-${number}`, prdId: prd.id, versionNo: number, contentHash: number === "V1" ? "a".repeat(64) : "b".repeat(64), content: input.content, sourceVersionId: prd.currentVersionId, isEffective: true }; prd = { ...prd, currentVersionId: version.id, rowVersion: prd.rowVersion + 1, status: "draft" }; return version; },
      async submitReview(_projectVersionId, input) { if (!prd || prd.rowVersion !== input.expectedVersion || !version) throw new PortError("CONFLICT", "版本冲突", 409, undefined, [], "VERSION_CONFLICT"); round += 1; review = { id: `review-${round}`, projectVersionId: prd.projectVersionId, roundNo: round, rowVersion: 1, status: "open", summary: null, prdId: input.prdId, prdVersionId: input.prdVersionId, contentHash: input.contentHash }; prd = { ...prd, status: "in_review", rowVersion: prd.rowVersion + 1 }; return review; },
      async getReview() { if (!review) throw new Error("missing review"); return review; },
      async decideReview(_reviewId, input) { if (!review || !prd || review.rowVersion !== input.expectedVersion) throw new PortError("CONFLICT", "版本冲突", 409, undefined, [], "VERSION_CONFLICT"); review = { ...review, rowVersion: review.rowVersion + 1, status: input.decision === "pass" ? "passed" : "changes_requested", summary: input.decision === "pass" ? null : input.summary ?? null }; prd = { ...prd, rowVersion: prd.rowVersion + 1, status: input.decision === "pass" ? "confirmed" : "changes_requested" }; return review; },
    },
  };
}

function fillContent() {
  fireEvent.change(screen.getByLabelText("背景"), { target: { value: "背景" } });
  fireEvent.change(screen.getByLabelText("目标"), { target: { value: "目标" } });
  fireEvent.change(screen.getByLabelText("主要用户"), { target: { value: "产品负责人" } });
  fireEvent.change(screen.getByLabelText("范围内"), { target: { value: "范围内" } });
  fireEvent.change(screen.getByLabelText("范围外"), { target: { value: "范围外" } });
  fireEvent.change(screen.getByLabelText("核心工作流"), { target: { value: "创建并保存" } });
  fireEvent.change(screen.getByLabelText("关键规则"), { target: { value: "显式保存" } });
  fireEvent.change(screen.getByLabelText("异常与边界"), { target: { value: "无 confirmed Baseline 时不可创建" } });
  fireEvent.change(screen.getByLabelText("验收标准"), { target: { value: "版本可追溯" } });
}

describe("PrdWorkbench", () => {
  it("creates, saves, submits, revises after changes_requested, resubmits and becomes confirmed read-only", async () => {
    render(<PrdWorkbench projectVersionId="pv-1" api={createApi()} />);
    const name = await screen.findByLabelText("PRD 名称");
    fireEvent.change(name, { target: { value: "冻结 PRD" } });
    fireEvent.click(screen.getByRole("button", { name: "创建 PRD" }));
    await screen.findByText(/PRD 已创建/);

    fillContent();
    fireEvent.change(screen.getByLabelText("变更说明"), { target: { value: "首次保存" } });
    fireEvent.click(screen.getByRole("button", { name: "保存新版本" }));
    await screen.findByText("已保存不可变 PRD 版本 V1。");
    fireEvent.click(screen.getByRole("button", { name: "提交评审" }));
    await screen.findByText(/设计评审第 1 轮已提交/);
    fireEvent.change(screen.getByLabelText("修改意见"), { target: { value: "请补充边界" } });
    fireEvent.click(screen.getByRole("button", { name: "要求修改" }));
    await screen.findByText("请补充边界");

    fireEvent.change(screen.getByLabelText("背景"), { target: { value: "已修订背景" } });
    fireEvent.change(screen.getByLabelText("变更说明"), { target: { value: "处理 Review 意见" } });
    fireEvent.click(screen.getByRole("button", { name: "保存新版本" }));
    await screen.findByText("已保存不可变 PRD 版本 V2。");
    fireEvent.click(screen.getByRole("button", { name: "提交评审" }));
    await screen.findByText(/设计评审第 2 轮已提交/);
    fireEvent.click(screen.getByRole("button", { name: "通过评审" }));
    await screen.findByText("当前 PRD 已通过设计评审；结构化编辑器已只读。");
    expect(screen.getByLabelText("背景")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "保存新版本" })).not.toBeInTheDocument();
  });

  it.each(["VERSION_CONFLICT", "INVALID_STATE", "IDEMPOTENCY_CONFLICT", "VALIDATION_ERROR", "FORBIDDEN", "NOT_FOUND"])("surfaces frozen %s feedback", async (code) => {
    const api = createApi();
    api.prds.create = async () => { throw new PortError(code === "FORBIDDEN" ? "FORBIDDEN" : "FAILED", "冻结错误反馈", code === "FORBIDDEN" ? 403 : 409, undefined, [], code as never); };
    render(<PrdWorkbench projectVersionId="pv-1" api={api} />);
    await screen.findByLabelText("PRD 名称");
    fireEvent.click(screen.getByRole("button", { name: "创建 PRD" }));
    await screen.findByText(`${code}：冻结错误反馈`);
  });

  it("does not create when the source Requirement Version is not unique", async () => {
    const api = createApi();
    api.requirements.list = async () => [confirmedRequirement, { ...confirmedRequirement, id: "req-2", effectiveVersionId: "req-v3" }];
    render(<PrdWorkbench projectVersionId="pv-1" api={api} />);
    await screen.findByText(/现有接口无法唯一确定来源/);
    expect(screen.getByRole("button", { name: "创建 PRD" })).toBeDisabled();
  });

  it("restores the exact design review relation after reopening", async () => {
    const api = createApi();
    await api.prds.create("pv-1", { name: "可恢复 PRD", sourceRequirementVersionId: "req-v2" });
    const saved = await api.prds.saveVersion("prd-1", { expectedVersion: 1, changeNote: "保存", content: { schemaVersion: "prd.mvp2.v1", background: "背景", goal: "目标", primaryUser: "负责人", inScope: ["范围"], outOfScope: ["排除"], coreWorkflow: ["流程"], keyRules: ["规则"], exceptionsAndBoundaries: [], acceptanceCriteria: ["验收"] } });
    await api.prds.submitReview("pv-1", { prdId: "prd-1", prdVersionId: saved.id, contentHash: saved.contentHash, expectedVersion: 2 });
    render(<PrdWorkbench projectVersionId="pv-1" api={api} />);
    expect(await screen.findByRole("heading", { name: /设计评审 · 第 1 轮/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "通过评审" })).toBeInTheDocument();
  });
});
