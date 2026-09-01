import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi } from "@/lib/api/mock-adapter";
import { PortError } from "@/lib/api/ports";
import type { AiResultView, ConfirmRequirementVersionInput, FormalizeAiResultInput, FrontendApi, SetClarificationModeInput } from "@/lib/api/ports";
import { RequirementWorkspace } from "./requirement-workspace";

afterEach(() => vi.restoreAllMocks());

function createTwoStepApi(confirmFailure = false) {
  let adoptedDraft = false;
  const create = vi.fn(async (projectVersionId: string, input: Parameters<FrontendApi["requirements"]["create"]>[1]) =>
    asFreshDraft(await mockApi.requirements.create(projectVersionId, input)),
  );
  const get = vi.fn(async (requirementId: string) => {
    const value = await mockApi.requirements.get(requirementId);
    if (!adoptedDraft || !value.currentVersion) return value;
    return {
      ...value,
      requirement: { ...value.requirement, id: "req-atlas-1", status: "draft" as const, effectiveVersionId: null },
      currentVersion: { ...value.currentVersion, requirementId: "version-carrier-20", confirmationStatus: "draft" as const, isEffective: false },
      effectiveVersion: null,
    };
  });
  const setClarificationMode = vi.fn(async (versionId: string, input: SetClarificationModeInput) => ({
    ...(await mockApi.requirements.setClarificationMode(versionId, input)),
    requirementId: "version-carrier-20",
    confirmationStatus: "draft" as const,
    isEffective: false,
    createdFromAiResultId: null,
  }));
  const confirm = vi.fn(async (versionId: string, input: ConfirmRequirementVersionInput) => {
    if (confirmFailure) throw new Error("确认服务暂不可用");
    const value = await mockApi.requirements.confirm(versionId, input);
    adoptedDraft = false;
    return value;
  });
  const formalizeBaseline = vi.fn(async (resultId: string, input: FormalizeAiResultInput) => {
    const value = await mockApi.ai.formalizeBaseline(resultId, input);
    adoptedDraft = true;
    return { ...value, status: "draft" };
  });
  const api: FrontendApi = {
    ...mockApi,
    requirements: { ...mockApi.requirements, list: async () => [], create, get, setClarificationMode, confirm },
    ai: { ...mockApi.ai, formalizeBaseline },
  };
  return { api, get, setClarificationMode, confirm, formalizeBaseline };
}

function asFreshDraft(value: Awaited<ReturnType<FrontendApi["requirements"]["create"]>>) {
  if (!value.currentVersion) return value;
  const currentVersion = {
    ...value.currentVersion,
    confirmationStatus: "draft" as const,
    isEffective: false,
    createdFromAiResultId: null,
  };
  return {
    ...value,
    requirement: { ...value.requirement, status: "draft" as const, currentVersionId: currentVersion.id, effectiveVersionId: null, version: 7 },
    currentVersion,
    effectiveVersion: null,
  };
}

function createFreshInputApi(): FrontendApi {
  return {
    ...mockApi,
    requirements: {
      ...mockApi.requirements,
      list: async () => [],
      create: async (projectVersionId, input) => asFreshDraft(await mockApi.requirements.create(projectVersionId, input)),
      setClarificationMode: async (versionId, input) => ({
        ...(await mockApi.requirements.setClarificationMode(versionId, input)),
        confirmationStatus: "draft" as const,
        isEffective: false,
        createdFromAiResultId: null,
      }),
    },
  };
}

function createUnresolvedCandidateApi(formalizeFailure = false) {
  const steps = createTwoStepApi();
  const getResult = steps.api.ai.getResult.bind(steps.api.ai);
  const formalizeBaseline = vi.fn(async (resultId: string, input: FormalizeAiResultInput) => {
    if (formalizeFailure) throw new Error("修改后采用服务暂不可用");
    return steps.formalizeBaseline(resultId, input);
  });
  const api: FrontendApi = {
    ...steps.api,
    ai: {
      ...steps.api.ai,
      getResult: async (resultId) => {
        const result = await getResult(resultId);
        if (result.resultKind !== "baseline" || !result.content?.baseline) return result;
        return {
          ...result,
          content: { ...result.content, baseline: { ...result.content.baseline, unresolvedItems: ["R4 未决项一", "R4 未决项二"] } },
        };
      },
      formalizeBaseline,
    },
  };
  return { api, formalizeBaseline, confirm: steps.confirm };
}

async function persistedRequirement(isEffective: boolean, isAiSourced = true) {
  const value = await mockApi.requirements.get("persisted-source");
  if (!value.currentVersion) throw new Error("Fixture requires a current Requirement Version.");
  const version = {
    ...value.currentVersion,
    id: "persisted-v2",
    requirementId: "persisted-requirement",
    versionNo: "V2",
    confirmationStatus: isEffective ? "confirmed" as const : "draft" as const,
    isEffective,
    createdFromAiResultId: isAiSourced ? "persisted-baseline-result" : null,
  };
  return {
    ...value,
    requirement: { ...value.requirement, id: "persisted-requirement", title: "已恢复 Requirement", status: isEffective ? "effective" as const : "draft" as const, currentVersionId: version.id, effectiveVersionId: isEffective ? version.id : null, version: 7 },
    currentVersion: version,
    effectiveVersion: isEffective ? version : null,
  };
}

async function clarificationRecoveryFixture(completedRounds: number[] = [], options: { mode?: "standard" | "deep"; continueDeepConfirmed?: boolean } = {}) {
  const value = await persistedRequirement(false, false);
  if (!value.currentVersion) throw new Error("Fixture requires a current Requirement Version.");
  const sourceRef = value.currentVersion.content.rawInputRef;
  const contentHash = "9".repeat(64);
  const clarificationMode = options.mode ?? "standard";
  const currentVersion = {
    ...value.currentVersion,
    id: "recovery-version-29",
    contentHash,
    content: {
      ...value.currentVersion.content,
      clarification: {
        ...value.currentVersion.content.clarification,
        mode: clarificationMode,
        continueDeepConfirmed: options.continueDeepConfirmed ?? false,
        rounds: completedRounds.map((roundNo) => ({
          roundNo,
          aiTaskId: `old-task-${roundNo}`,
          aiResultId: `old-result-${roundNo}`,
          questions: [{ questionId: `q-${roundNo}`, dimension: "goal" as const, questionText: `已完成问题 q-${roundNo}`, reason: "补足需求", sourceRefs: [sourceRef] }],
          answers: [{ questionId: `q-${roundNo}`, answer: `已保存回答 ${roundNo}` }],
        })),
        finishReason: null,
      },
    },
  };
  const requirement = {
    ...value,
    requirement: { ...value.requirement, currentVersionId: currentVersion.id },
    currentVersion,
  };
  const result: AiResultView = {
    id: "result-4",
    taskPublicId: "2169067d-1f72-e6d5-6ace-58e25f2c8dbd",
    taskType: "requirement.clarify",
    targetSnapshotHash: contentHash,
    mode: clarificationMode,
    roundNo: completedRounds.length + 1,
    resultKind: "questions",
    status: "ready",
    content: {
      assessment: null,
      baseline: null,
      questions: ["q-1", "q-2", "q-3"].map((questionId, index) => ({
        questionId,
        dimension: (["goal", "functional_scope", "acceptance_criteria"] as const)[index],
        questionText: `恢复问题 ${questionId}`,
        reason: "补足需求",
        sourceRefs: [sourceRef],
      })),
    },
    convergence: { shouldFinish: false, finishReason: null, nextRoundNo: resultRoundAfter(completedRounds.length + 1, clarificationMode) },
    quality: { formatStatus: "passed", traceabilityStatus: "passed", safetyStatus: "passed", requiredItemsMet: 3, requiredItemsTotal: 3, majorError: false, blockerCodes: [] },
    capabilitySummary: { truthLabel: "REAL_PROVIDER", providerCode: "deepseek", modelCode: "model" },
  };
  return { requirement, result };
}

function resultRoundAfter(roundNo: number, mode: "standard" | "deep") {
  return roundNo >= (mode === "standard" ? 3 : 5) ? null : roundNo + 1;
}

async function submitRecoveredAnswers(completedRounds: number[], options: { mode: "standard" | "deep"; continueDeepConfirmed?: boolean }, finishNow = false) {
  const { requirement, result } = await clarificationRecoveryFixture(completedRounds, options);
  const submitClarificationAnswers = vi.fn(async () => ({ version: requirement.currentVersion!, baselineCandidateRef: null }));
  const createTask = vi.fn(mockApi.ai.createTask);
  const api: FrontendApi = {
    ...mockApi,
    requirements: { ...mockApi.requirements, list: async () => [requirement.requirement], get: async () => requirement, submitClarificationAnswers },
    ai: { ...mockApi.ai, findClarificationResult: async () => result, createTask },
  };
  render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);
  await screen.findByRole("heading", { name: `3. 第 ${result.roundNo} 轮问题（3/3）` });
  for (const [index, questionId] of ["q-1", "q-2", "q-3"].entries()) {
    fireEvent.change(screen.getByLabelText(`恢复问题 ${questionId}`), { target: { value: `回答${index + 1}` } });
  }
  fireEvent.click(screen.getByRole("button", { name: finishNow ? "结束并审核需求基线" : "保存回答" }));
  await waitFor(() => expect(submitClarificationAnswers).toHaveBeenCalledOnce());
  await waitFor(() => expect(createTask).toHaveBeenCalledOnce());
  return { requirement, result, submitClarificationAnswers, createTask };
}

async function reachSkipBaseline(api: FrontendApi) {
  render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);
  await screen.findByLabelText("标题");
  fireEvent.change(screen.getByLabelText("标题"), { target: { value: "团队需求" } });
  fireEvent.change(screen.getByLabelText("原始需求"), { target: { value: "需要澄清目标和权限" } });
  fireEvent.click(screen.getByRole("button", { name: "保存需求草稿" }));
  await screen.findByRole("heading", { name: "团队需求" });
  fireEvent.change(screen.getByLabelText("澄清模式"), { target: { value: "skip" } });
  fireEvent.click(screen.getByRole("button", { name: "开始预检 / 澄清" }));
  await screen.findByText("需求基线候选已就绪，请核对质量与来源后采用。");
}

describe("RequirementWorkspace", () => {
  it("hydrates the exact ready questions on reload with empty answers and creates no AI task", async () => {
    const { requirement, result } = await clarificationRecoveryFixture();
    const findClarificationResult = vi.fn(async () => result);
    const createTask = vi.fn(mockApi.ai.createTask);
    const api: FrontendApi = {
      ...mockApi,
      requirements: { ...mockApi.requirements, list: async () => [requirement.requirement], get: async () => requirement },
      ai: { ...mockApi.ai, findClarificationResult, createTask },
    };

    render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);

    await screen.findByRole("heading", { name: "3. 第 1 轮问题（3/3）" });
    expect(findClarificationResult).toHaveBeenCalledWith("recovery-version-29", "standard", 1);
    expect(createTask).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "开始预检 / 澄清" })).not.toBeInTheDocument();
    expect(screen.queryByText("候选结果未正式化。你仍可以直接编辑人工需求基线并确认。")).not.toBeInTheDocument();
    for (const questionId of ["q-1", "q-2", "q-3"]) {
      expect(screen.getByLabelText(`恢复问题 ${questionId}`)).toHaveValue("");
    }
  });

  it.each([
    [1, []],
    [2, [1]],
    [3, [1, 2]],
  ])("submits recovered Standard round %i with false and exact question identities", async (roundNo, completedRounds) => {
    const { requirement, submitClarificationAnswers, createTask } = await submitRecoveredAnswers(completedRounds, { mode: "standard" });
    expect(submitClarificationAnswers).toHaveBeenCalledWith("recovery-version-29", {
      expectedVersion: requirement.requirement.version,
      roundNo,
      answers: [
        { questionId: "q-1", answer: "回答1" },
        { questionId: "q-2", answer: "回答2" },
        { questionId: "q-3", answer: "回答3" },
      ],
      continueDeepConfirmed: false,
      finishNow: false,
    });
    await waitFor(() => expect(createTask).toHaveBeenCalledOnce());
  });

  it.each([
    [1, [], false],
    [2, [1], false],
    [3, [1, 2], false],
    [4, [1, 2, 3], true],
    [5, [1, 2, 3, 4], true],
  ])("keeps Deep round %i normal answer-save false", async (roundNo, completedRounds, continueDeepConfirmed) => {
    const { submitClarificationAnswers } = await submitRecoveredAnswers(completedRounds, { mode: "deep", continueDeepConfirmed });
    expect(submitClarificationAnswers).toHaveBeenCalledWith("recovery-version-29", expect.objectContaining({
      roundNo,
      continueDeepConfirmed: false,
      finishNow: false,
    }));
    expect(screen.queryByRole("checkbox", { name: /继续深度澄清/ })).not.toBeInTheDocument();
  });

  it("shows continuation only for the authoritative completed-three-round state and sends explicit true", async () => {
    const { requirement } = await clarificationRecoveryFixture([1, 2, 3], { mode: "deep" });
    if (!requirement.currentVersion) throw new Error("Fixture requires a current Requirement Version.");
    const confirmedVersion = {
      ...requirement.currentVersion,
      id: "deep-confirmed-version",
      content: {
        ...requirement.currentVersion.content,
        clarification: { ...requirement.currentVersion.content.clarification, continueDeepConfirmed: true },
      },
    };
    const submitClarificationAnswers = vi.fn(async () => ({ version: confirmedVersion, baselineCandidateRef: null }));
    const findClarificationResult = vi.fn();
    const createTask = vi.fn(mockApi.ai.createTask);
    const api: FrontendApi = {
      ...mockApi,
      requirements: { ...mockApi.requirements, list: async () => [requirement.requirement], get: async () => requirement, submitClarificationAnswers },
      ai: { ...mockApi.ai, findClarificationResult, createTask },
    };

    render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);
    await screen.findByRole("heading", { name: "确认继续深度澄清" });
    expect(screen.queryByRole("button", { name: "开始预检 / 澄清" })).not.toBeInTheDocument();
    expect(findClarificationResult).not.toHaveBeenCalled();
    expect(createTask).not.toHaveBeenCalled();
    const confirmButton = screen.getByRole("button", { name: "确认继续深度澄清" });
    expect(confirmButton).toBeDisabled();
    expect(submitClarificationAnswers).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("checkbox", { name: "我确认继续深度澄清第 4 轮" }));
    fireEvent.click(confirmButton);

    await waitFor(() => expect(submitClarificationAnswers).toHaveBeenCalledWith("recovery-version-29", {
      expectedVersion: requirement.requirement.version,
      roundNo: 3,
      answers: [{ questionId: "q-3", answer: "已保存回答 3" }],
      continueDeepConfirmed: true,
      finishNow: false,
    }));
    await waitFor(() => expect(createTask).toHaveBeenCalledOnce());
  });

  it("forces finish-now to keep deep confirmation false", async () => {
    const { submitClarificationAnswers } = await submitRecoveredAnswers([1, 2], { mode: "deep" }, true);
    expect(submitClarificationAnswers).toHaveBeenCalledWith("recovery-version-29", expect.objectContaining({
      roundNo: 3,
      continueDeepConfirmed: false,
      finishNow: true,
    }));
  });

  it("keeps the normal start and manual paths when no ready result exists", async () => {
    const { requirement } = await clarificationRecoveryFixture();
    const createTask = vi.fn(mockApi.ai.createTask);
    const api: FrontendApi = {
      ...mockApi,
      requirements: { ...mockApi.requirements, list: async () => [requirement.requirement], get: async () => requirement },
      ai: { ...mockApi.ai, findClarificationResult: async () => null, createTask },
    };
    render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);
    await screen.findByRole("button", { name: "开始预检 / 澄清" });
    expect(screen.getByRole("button", { name: "人工确认需求基线" })).toBeEnabled();
    expect(createTask).not.toHaveBeenCalled();
  });

  it("shows a read-only retry on lookup conflict and never falls back to Provider task creation", async () => {
    const { requirement } = await clarificationRecoveryFixture();
    const findClarificationResult = vi.fn(async () => { throw new PortError("CONFLICT", "存在多个权威结果。", 409); });
    const createTask = vi.fn(mockApi.ai.createTask);
    const api: FrontendApi = {
      ...mockApi,
      requirements: { ...mockApi.requirements, list: async () => [requirement.requirement], get: async () => requirement },
      ai: { ...mockApi.ai, findClarificationResult, createTask },
    };
    render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);
    await screen.findByText("存在多个权威结果。");
    expect(screen.queryByRole("button", { name: "开始预检 / 澄清" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新读取已有结果" }));
    await waitFor(() => expect(findClarificationResult).toHaveBeenCalledTimes(2));
    expect(createTask).not.toHaveBeenCalled();
  });

  it.each([
    ["an old target Version", { targetSnapshotHash: "8".repeat(64) }],
    ["a wrong round", { roundNo: 2 }],
  ])("fails closed when recovery returns %s", async (_label, override) => {
    const { requirement, result } = await clarificationRecoveryFixture();
    const createTask = vi.fn(mockApi.ai.createTask);
    const api: FrontendApi = {
      ...mockApi,
      requirements: { ...mockApi.requirements, list: async () => [requirement.requirement], get: async () => requirement },
      ai: { ...mockApi.ai, findClarificationResult: async () => ({ ...result, ...override }), createTask },
    };
    render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);
    await screen.findByText("已读取的 AI 澄清结果与当前需求版本不一致。");
    expect(screen.queryByText("恢复问题 q-1")).not.toBeInTheDocument();
    expect(createTask).not.toHaveBeenCalled();
  });

  it("shows the existing empty state only after list confirms there are no Requirements", async () => {
    const list = vi.fn(async () => []);
    const get = vi.fn();
    const api = { ...mockApi, requirements: { ...mockApi.requirements, list, get } };

    render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);

    expect(screen.getByRole("status")).toHaveTextContent("正在读取当前查看版本的需求");
    expect(screen.queryByRole("heading", { name: "1. 手工输入需求" })).not.toBeInTheDocument();
    await screen.findByRole("heading", { name: "1. 手工输入需求" });
    expect(list).toHaveBeenCalledWith("atlas-v2");
    expect(get).not.toHaveBeenCalled();
  });

  it("does not flash the empty state while the Requirement list is loading", async () => {
    let resolveList: ((items: Awaited<ReturnType<FrontendApi["requirements"]["list"]>>) => void) | undefined;
    const list = vi.fn(() => new Promise<Awaited<ReturnType<FrontendApi["requirements"]["list"]>>>((resolve) => { resolveList = resolve; }));
    const api = { ...mockApi, requirements: { ...mockApi.requirements, list } };

    render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);

    expect(screen.getByRole("status")).toHaveTextContent("正在读取当前查看版本的需求");
    expect(screen.queryByRole("heading", { name: "1. 手工输入需求" })).not.toBeInTheDocument();
    resolveList?.([]);
    await screen.findByRole("heading", { name: "1. 手工输入需求" });
  });

  it("gets the sole persisted Requirement and restores its adopted draft confirmation", async () => {
    const adoptedDraft = await persistedRequirement(false);
    const confirmed = await persistedRequirement(true);
    const list = vi.fn(async () => [adoptedDraft.requirement]);
    const get = vi.fn().mockResolvedValueOnce(adoptedDraft).mockResolvedValueOnce(confirmed);
    const confirm = vi.fn(async () => ({ version: confirmed.currentVersion!, gateResult: "passed" as const }));
    const api = { ...mockApi, requirements: { ...mockApi.requirements, list, get, confirm } };

    render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);

    await screen.findByText("版本 V2 · 草稿 · 尚未设为当前需求基线");
    expect(get).toHaveBeenCalledWith("persisted-requirement");
    fireEvent.click(screen.getByRole("button", { name: "确认并设为当前需求基线" }));
    await screen.findByText("版本 V2 · 已确认 · 当前需求基线");
    expect(confirm).toHaveBeenCalledWith("persisted-v2", { expectedVersion: 7 });
    expect(get).toHaveBeenLastCalledWith("persisted-requirement");
  });

  it("uses the aggregate version for manual revise then confirm, even when version labels diverge", async () => {
    const source = await persistedRequirement(false);
    if (!source.currentVersion) throw new Error("Fixture requires a current Requirement Version.");
    const draft = { ...source.currentVersion, createdFromAiResultId: null, versionNo: "V2" };
    const value = { ...source, currentVersion: draft, requirement: { ...source.requirement, currentVersionId: draft.id } };
    const list = vi.fn(async () => [value.requirement]);
    const get = vi.fn(async () => value);
    const revised = { ...draft, id: "manual-v3", versionNo: "V3", content: { ...draft.content, baseline: value.currentVersion!.content.baseline } };
    const revise = vi.fn(async () => revised);
    const confirmed = { ...revised, confirmationStatus: "confirmed" as const, isEffective: true };
    const confirm = vi.fn(async () => ({ version: confirmed, gateResult: "passed" as const }));
    const api = { ...mockApi, requirements: { ...mockApi.requirements, list, get, revise, confirm } };

    render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);

    await screen.findByText("版本 V2 · 草稿");
    fireEvent.change(screen.getByLabelText("目标"), { target: { value: "人工确认目标" } });
    fireEvent.click(screen.getByRole("button", { name: "人工确认需求基线" }));
    await screen.findByText("需求基线已确认（passed）。");

    expect(revise).toHaveBeenCalledWith("persisted-v2", expect.objectContaining({
      expectedVersion: 7,
      content: expect.objectContaining({
        baseline: expect.objectContaining({
          dimensions: expect.objectContaining({
            goal: expect.objectContaining({ confirmedFacts: ["人工确认目标"] }),
          }),
        }),
      }),
    }));
    expect(confirm).toHaveBeenCalledWith("manual-v3", { expectedVersion: 8 });
    expect(screen.getByText("版本 V3 · 已确认 · 当前需求基线")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "需求阶段已完成" })).toBeInTheDocument();
    expect(screen.getByText(/来源：人工确认需求基线。/)).toBeInTheDocument();
    expect(screen.getByText(/当前需求阶段已满足进入 PRD 的业务条件/)).toBeInTheDocument();
  });

  it("surfaces a real stale aggregate version conflict without retrying or masking it", async () => {
    const source = await persistedRequirement(false);
    if (!source.currentVersion) throw new Error("Fixture requires a current Requirement Version.");
    const draft = { ...source.currentVersion, createdFromAiResultId: null, versionNo: "V2" };
    const value = { ...source, currentVersion: draft, requirement: { ...source.requirement, currentVersionId: draft.id } };
    let serverVersion = 7;
    const revise = vi.fn(async (_versionId: string, input: Parameters<FrontendApi["requirements"]["revise"]>[1]) => {
      if (input.expectedVersion !== serverVersion) throw new Error("Requirement has changed");
      return { ...draft, id: "manual-v3", versionNo: "V3" };
    });
    const api = { ...mockApi, requirements: { ...mockApi.requirements, list: async () => [value.requirement], get: async () => value, revise } };

    render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);

    await screen.findByText("版本 V2 · 草稿");
    serverVersion = 8;
    fireEvent.click(screen.getByRole("button", { name: "人工确认需求基线" }));
    await screen.findByText("Requirement has changed");

    expect(revise).toHaveBeenCalledWith("persisted-v2", expect.objectContaining({ expectedVersion: 7 }));
  });

  it("shows the persisted AI-sourced effective Baseline as a completed Requirement", async () => {
    const confirmed = await persistedRequirement(true);
    const api = { ...mockApi, requirements: { ...mockApi.requirements, list: async () => [confirmed.requirement], get: async () => confirmed } };

    render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);

    await screen.findByRole("heading", { name: "需求阶段已完成" });
    expect(screen.getByText(/需求基线已确认，版本 V2 已设为当前基线。/)).toBeInTheDocument();
    expect(screen.getByText(/来源：采用 AI 候选。/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "确认并设为当前需求基线" })).not.toBeInTheDocument();
  });

  it("keeps the completed state after a fresh GET for an effective manual Baseline", async () => {
    const confirmed = await persistedRequirement(true, false);
    const api = { ...mockApi, requirements: { ...mockApi.requirements, list: async () => [confirmed.requirement], get: async () => confirmed } };

    render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);

    await screen.findByRole("heading", { name: "需求阶段已完成" });
    expect(screen.getByText(/需求基线已确认，版本 V2 已设为当前基线。/)).toBeInTheDocument();
    expect(screen.getByText(/来源：人工确认需求基线。/)).toBeInTheDocument();
  });

  it("does not show the completed state for a draft Requirement", async () => {
    const draft = await persistedRequirement(false, false);
    const api = { ...mockApi, requirements: { ...mockApi.requirements, list: async () => [draft.requirement], get: async () => draft } };

    render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);

    await screen.findByText("版本 V2 · 草稿");
    expect(screen.queryByRole("heading", { name: "需求阶段已完成" })).not.toBeInTheDocument();
  });

  it("requires an explicit selection when the viewed version has multiple Requirements", async () => {
    const first = await persistedRequirement(false);
    const second = { ...first, requirement: { ...first.requirement, id: "second-requirement", title: "第二个 Requirement" } };
    const list = vi.fn(async () => [first.requirement, second.requirement]);
    const get = vi.fn(async () => first);
    const api = { ...mockApi, requirements: { ...mockApi.requirements, list, get } };

    render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);

    await screen.findByRole("heading", { name: "选择需求" });
    expect(get).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "已恢复 Requirement" }));
    await screen.findByText("版本 V2 · 草稿 · 尚未设为当前需求基线");
    expect(get).toHaveBeenCalledWith("persisted-requirement");
  });

  it("retries read failures without creating a Requirement", async () => {
    const list = vi.fn().mockRejectedValueOnce(new Error("读取服务暂不可用")).mockResolvedValueOnce([]);
    const create = vi.fn(mockApi.requirements.create);
    const api = { ...mockApi, requirements: { ...mockApi.requirements, list, create } };

    render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);

    await screen.findByText("读取服务暂不可用");
    fireEvent.click(screen.getByRole("button", { name: "重新读取当前查看版本" }));
    await screen.findByRole("heading", { name: "1. 手工输入需求" });
    expect(list).toHaveBeenCalledTimes(2);
    expect(create).not.toHaveBeenCalled();
  });

  it("retries a failed unique Requirement read without creating data", async () => {
    const adoptedDraft = await persistedRequirement(false);
    const list = vi.fn(async () => [adoptedDraft.requirement]);
    const get = vi.fn().mockRejectedValueOnce(new Error("Requirement 读取失败")).mockResolvedValueOnce(adoptedDraft);
    const create = vi.fn(mockApi.requirements.create);
    const api = { ...mockApi, requirements: { ...mockApi.requirements, list, get, create } };

    render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);

    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "重新读取当前查看版本" }));
    await screen.findByText("版本 V2 · 草稿 · 尚未设为当前需求基线");
    expect(create).not.toHaveBeenCalled();
  });

  it("renders assessment separately, then adopts a draft and explicitly confirms the current baseline", async () => {
    const { api, get, setClarificationMode, confirm, formalizeBaseline } = createTwoStepApi();
    render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);
    expect(screen.getByRole("heading", { name: "需求澄清与需求基线" })).toBeInTheDocument();
    await screen.findByLabelText("标题");
    fireEvent.change(screen.getByLabelText("标题"), { target: { value: "团队需求" } });
    fireEvent.change(screen.getByLabelText("原始需求"), { target: { value: "需要澄清目标和权限" } });
    fireEvent.click(screen.getByRole("button", { name: "保存需求草稿" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "团队需求" })).toBeInTheDocument());
    expect(screen.getByText("演示数据")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "4. 人工需求基线编辑与确认" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "开始预检 / 澄清" }));
    await waitFor(() => expect(screen.getByText("AI 预检已就绪，请明确选择下一步模式。")).toBeInTheDocument());
    expect(setClarificationMode).toHaveBeenNthCalledWith(1, expect.any(String), expect.objectContaining({ mode: "auto", reason: null }));
    expect(screen.getByText("复杂度 medium · 建议 standard")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "采用需求基线并形成新版本" })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("澄清模式"), { target: { value: "skip" } });
    fireEvent.click(screen.getByRole("button", { name: "按所选模式继续" }));
    await waitFor(() => expect(screen.getByText("需求基线候选已就绪，请核对质量与来源后采用。")).toBeInTheDocument());
    expect(setClarificationMode).toHaveBeenNthCalledWith(2, expect.any(String), expect.objectContaining({ mode: "skip", reason: "用户明确选择跳过澄清并进入人工审核" }));
    expect(screen.getByText("AI 能力来源：正式模拟")).toBeInTheDocument();
    expect(screen.getByText("格式 passed · 可追溯性 passed · 安全 passed")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "采用需求基线并形成新版本" }));
    await waitFor(() => expect(screen.getByText("需求基线已采用，形成待确认版本 V10。")).toBeInTheDocument());
    expect(setClarificationMode).toHaveBeenNthCalledWith(1, expect.any(String), expect.objectContaining({ expectedVersion: 7 }));
    expect(setClarificationMode).toHaveBeenNthCalledWith(2, expect.any(String), expect.objectContaining({ expectedVersion: 8 }));
    expect(formalizeBaseline.mock.calls[0]?.[1]).toEqual({ requirementId: "version-carrier-20", expectedVersion: 9, targetSnapshotHash: "2".repeat(64) });
    expect(screen.getByText("版本 V10 · 草稿 · 尚未设为当前需求基线")).toBeInTheDocument();
    expect(screen.queryByText("版本 V10 · 已确认 · 当前需求基线")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "采用需求基线并形成新版本" })).not.toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("req-atlas-1");
    expect(get).not.toHaveBeenCalledWith("version-carrier-20");

    fireEvent.click(screen.getByRole("button", { name: "确认并设为当前需求基线" }));
    await waitFor(() => expect(screen.getByText("需求基线已确认并设为当前基线。")).toBeInTheDocument());
    expect(confirm).toHaveBeenCalledWith("req-v10", { expectedVersion: 10 });
    expect(screen.getByText("版本 V10 · 已确认 · 当前需求基线")).toBeInTheDocument();
    expect(screen.getByLabelText("目标")).toBeInTheDocument();
  });

  it("retains the adopted draft and safe retry when explicit confirmation fails", async () => {
    const { api, confirm } = createTwoStepApi(true);
    await reachSkipBaseline(api);
    fireEvent.click(screen.getByRole("button", { name: "采用需求基线并形成新版本" }));
    await screen.findByText(/尚未设为当前需求基线/);

    fireEvent.click(screen.getByRole("button", { name: "确认并设为当前需求基线" }));
    await screen.findByText("确认服务暂不可用");
    expect(confirm).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ expectedVersion: expect.any(Number) }));
    expect(screen.getByText(/尚未设为当前需求基线/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认并设为当前需求基线" })).toBeEnabled();
    expect(screen.queryByText("需求基线已确认并设为当前基线。")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "采用需求基线并形成新版本" })).not.toBeInTheDocument();
  });

  it("requires explicit handling of every unresolved candidate item before modified adoption", async () => {
    const { api, formalizeBaseline, confirm } = createUnresolvedCandidateApi();
    await reachSkipBaseline(api);

    expect(screen.getByText("R4 未决项一")).toBeInTheDocument();
    expect(screen.getByText("R4 未决项二")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "采用需求基线并形成新版本" })).toBeDisabled();
    expect(formalizeBaseline).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "标记已处理：R4 未决项一" }));
    expect(screen.queryByText("R4 未决项一")).not.toBeInTheDocument();
    expect(screen.getByText("R4 未决项二")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "采用需求基线并形成新版本" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "标记已处理：R4 未决项二" }));
    const modifiedAdopt = screen.getByRole("button", { name: "修改后采用并形成新版本" });
    expect(modifiedAdopt).toBeEnabled();
    fireEvent.click(modifiedAdopt);
    await screen.findByText(/需求基线已采用，形成待确认版本 V\d+。/);
    expect(formalizeBaseline).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({
      adoption: "modified_adopt",
      modificationIntensity: "minor",
      modifiedContent: expect.objectContaining({ baseline: expect.objectContaining({ unresolvedItems: [] }) }),
    }));
    expect(screen.getByText(/版本 V\d+ · 草稿 · 尚未设为当前需求基线/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认并设为当前需求基线" }));
    await screen.findByText("需求基线已确认并设为当前基线。");
    expect(confirm).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ expectedVersion: expect.any(Number) }));
  });

  it("preserves the explicitly edited candidate and retry action when modified adoption fails", async () => {
    const { api, formalizeBaseline } = createUnresolvedCandidateApi(true);
    await reachSkipBaseline(api);
    fireEvent.click(screen.getByRole("button", { name: "标记已处理：R4 未决项一" }));
    fireEvent.click(screen.getByRole("button", { name: "标记已处理：R4 未决项二" }));
    fireEvent.click(screen.getByRole("button", { name: "修改后采用并形成新版本" }));

    await screen.findByText("修改后采用服务暂不可用");
    expect(formalizeBaseline).toHaveBeenCalledTimes(1);
    expect(screen.getByText("未决项已显式处理")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "修改后采用并形成新版本" })).toBeEnabled();
    expect(screen.queryByText("需求基线已采用，形成待确认版本 V2。")).not.toBeInTheDocument();
  });

  it("keeps the existing deep reason unchanged", async () => {
    const api = createFreshInputApi();
    const setClarificationMode = vi.spyOn(api.requirements, "setClarificationMode");
    render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);
    await screen.findByLabelText("标题");
    fireEvent.change(screen.getByLabelText("标题"), { target: { value: "深度澄清需求" } });
    fireEvent.change(screen.getByLabelText("原始需求"), { target: { value: "需要覆盖更多业务边界" } });
    fireEvent.click(screen.getByRole("button", { name: "保存需求草稿" }));
    await screen.findByRole("heading", { name: "深度澄清需求" });
    fireEvent.change(screen.getByLabelText("澄清模式"), { target: { value: "deep" } });
    fireEvent.click(screen.getByRole("button", { name: "开始预检 / 澄清" }));
    await waitFor(() => expect(setClarificationMode).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ mode: "deep", reason: "需要覆盖更多边界" })));
  });

  it("shows a neutral provider truth state when the stored truth label is missing", async () => {
    const api = createFreshInputApi();
    const getResult = api.ai.getResult.bind(api.ai);
    vi.spyOn(api.ai, "getResult").mockImplementation(async (resultId) => ({
      ...(await getResult(resultId)),
      capabilitySummary: { truthLabel: null, providerCode: null, modelCode: null },
    }));
    render(<RequirementWorkspace projectVersionId="atlas-v2" api={api} />);
    await screen.findByLabelText("标题");
    fireEvent.change(screen.getByLabelText("标题"), { target: { value: "Provider 真相缺失需求" } });
    fireEvent.change(screen.getByLabelText("原始需求"), { target: { value: "缺失真相标签时必须保持中立" } });
    fireEvent.click(screen.getByRole("button", { name: "保存需求草稿" }));
    await screen.findByRole("heading", { name: "Provider 真相缺失需求" });
    fireEvent.change(screen.getByLabelText("澄清模式"), { target: { value: "skip" } });
    fireEvent.click(screen.getByRole("button", { name: "开始预检 / 澄清" }));
    await waitFor(() => expect(screen.getByText("AI 能力来源：不可用")).toBeInTheDocument());
    expect(screen.queryByText("AI 能力来源：正式模拟")).not.toBeInTheDocument();
  });

  it("keeps the manual baseline path available when the AI task fails", async () => {
    const freshApi = createFreshInputApi();
    const failedApi = {
      ...freshApi,
      requirements: freshApi.requirements,
      ai: {
        ...freshApi.ai,
        createTask: async () => ({
          taskId: "failed-task",
          taskPublicId: "failed-task",
          taskType: "requirement.clarify" as const,
          status: "failed" as const,
          targetSnapshotHash: "f".repeat(64),
          pollUrl: "/mock/tasks/failed-task",
          eventsUrl: "/mock/tasks/failed-task/events",
          missingItems: [],
          createdByUserId: "user-1",
          queuedAt: "2026-08-09T00:00:00Z",
          resultRefs: [],
        }),
      },
    };

    render(<RequirementWorkspace projectVersionId="atlas-v2" api={failedApi} />);
    await screen.findByLabelText("标题");
    fireEvent.change(screen.getByLabelText("标题"), { target: { value: "失败恢复需求" } });
    fireEvent.change(screen.getByLabelText("原始需求"), { target: { value: "AI 不可用时继续人工确认" } });
    fireEvent.click(screen.getByRole("button", { name: "保存需求草稿" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "失败恢复需求" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "开始预检 / 澄清" }));
    await waitFor(() => expect(screen.getByText("候选结果未正式化。你仍可以直接编辑人工需求基线并确认。")).toBeInTheDocument());
    expect(screen.getByText("AI 不可用时继续人工确认")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "人工确认需求基线" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "采用需求基线并形成新版本" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("目标"), { target: { value: "人工完成目标" } });
    fireEvent.click(screen.getByRole("button", { name: "人工确认需求基线" }));
    await screen.findByRole("heading", { name: "需求阶段已完成" });
    expect(screen.queryByText("候选结果未正式化。你仍可以直接编辑人工需求基线并确认。")).not.toBeInTheDocument();
  });
});
