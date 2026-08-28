import { afterEach, describe, expect, it, vi } from "vitest";
import { submitRequirementClarificationAnswers } from "./generated/client";

afterEach(() => vi.unstubAllGlobals());

describe("generated clarification answer client", () => {
  it("preserves an explicit false deep-confirmation boolean in the HTTP JSON body", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    await submitRequirementClarificationAnswers("version-1", {
      expected_version: 4,
      round_no: 1,
      answers: [{ question_id: "q-1", answer: "answer" }],
      continue_deep_confirmed: false,
      finish_now: false,
    }, { "Idempotency-Key": "test-command" });

    expect(fetchMock).toHaveBeenCalledOnce();
    const call = fetchMock.mock.calls[0];
    if (!call) throw new Error("Expected one generated client request.");
    const [url, init] = call;
    expect(String(url)).toMatch(/\/api\/v1\/requirement-versions\/version-1\/clarification-answers$/);
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      expected_version: 4,
      round_no: 1,
      answers: [{ question_id: "q-1", answer: "answer" }],
      continue_deep_confirmed: false,
      finish_now: false,
    });
  });
});
