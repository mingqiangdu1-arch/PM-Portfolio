import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { frontendApi } from "@/lib/api/frontend-api";
import type { ProjectOverviewView } from "@/lib/api/ports";
import { ProjectOverview } from "./project-overview";

const overview: ProjectOverviewView = {
  id: "project-7",
  name: "P1 项目",
  goal: "形成 Requirement Baseline",
  workingVersionId: "version-11",
  workingVersionNo: "V11",
  projectVersion: 11,
  stage: "需求澄清",
  updatedAt: "2026-08-13T00:00:00Z",
  viewedVersionId: "version-11",
  viewedVersionNo: "V11",
  isHistory: false,
  canEdit: true,
  blocker: null,
};

afterEach(() => vi.restoreAllMocks());

describe("ProjectOverview Requirement entry", () => {
  it("links the editable next step to the viewed Requirement version", async () => {
    vi.spyOn(frontendApi.projects, "overview").mockResolvedValueOnce(overview);

    render(<ProjectOverview projectId="project-7" />);

    expect(await screen.findByRole("link", { name: "继续当前阶段" })).toHaveAttribute(
      "href",
      "/projects/project-7/versions/version-11/requirements",
    );
  });

  it("keeps the readonly next step disabled and non-navigable", async () => {
    vi.spyOn(frontendApi.projects, "overview").mockResolvedValueOnce(overview);

    render(<ProjectOverview projectId="project-7" scenario="readonly" />);

    expect(await screen.findByRole("button", { name: "历史版本不可编辑" })).toBeDisabled();
    expect(screen.queryByRole("link", { name: "历史版本不可编辑" })).not.toBeInTheDocument();
  });
});
