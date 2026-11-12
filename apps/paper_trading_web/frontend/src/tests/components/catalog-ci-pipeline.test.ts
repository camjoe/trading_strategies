// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import ciData from "../../assets/ci.json";
import {
  describeTrigger,
  describeWhen,
  filterLabel,
  handleCiPipelineClick,
  pipelineStages,
  renderCiPipeline,
} from "../../features/catalog-ci-pipeline";
import type { CiJob, CiPipeline } from "../../types/ci";

function job(id: string, overrides: Partial<CiJob> = {}): CiJob {
  return {
    id,
    name: id,
    needs: [],
    runs_on: "ubuntu-latest",
    condition: null,
    always_on_push: false,
    when_changed: [],
    path_filters: {},
    steps: [],
    ...overrides,
  };
}

describe("pipelineStages", () => {
  it("places each job one stage after the deepest job it needs", () => {
    const stages = pipelineStages([
      job("changes"),
      job("python", { needs: ["changes"] }),
      job("deploy", { needs: ["python", "changes"] }),
      job("frontend", { needs: ["changes"] }),
    ]);

    expect(stages.map((stage) => stage.map((item) => item.id))).toEqual([
      ["changes"],
      ["python", "frontend"],
      ["deploy"],
    ]);
  });
});

describe("pipeline wording", () => {
  it("names filters and triggers in plain words", () => {
    expect(filterLabel("docs_enforcement_related")).toBe("docs enforcement");
    expect(describeTrigger({ event: "push", branches: ["main", "develop"] })).toBe("push to main, develop");
    expect(describeTrigger({ event: "pull_request", branches: [] })).toBe("every pull request");
  });

  it("says when a job runs", () => {
    expect(describeWhen(job("changes"))).toBe("Every run");
    expect(describeWhen(job("python", { always_on_push: true, when_changed: ["python_related"] }))).toBe(
      "Every push; on a pull request, only when python files change",
    );
    expect(describeWhen(job("docs", { when_changed: ["docs_related", "frontend_related"] }))).toBe(
      "Only when docs or frontend files change",
    );
  });
});

describe("the CI pipeline card", () => {
  it("draws every job in the workflow asset", () => {
    document.body.innerHTML = renderCiPipeline();
    const jobs = Array.from(document.querySelectorAll<HTMLElement>("[data-ci-job]")).map((el) => el.dataset.ciJob);

    expect(jobs).toEqual((ciData as CiPipeline).jobs.map((item) => item.id));
  });

  it("shows and hides the steps of every job", () => {
    document.body.innerHTML = renderCiPipeline();
    const toggle = document.querySelector<HTMLButtonElement>("[data-ci-steps-toggle]") as HTMLButtonElement;
    const hiddenSteps = () => Array.from(document.querySelectorAll<HTMLElement>("[data-ci-steps]")).filter((s) => s.hidden);

    expect(handleCiPipelineClick(toggle)).toBe(true);
    expect(hiddenSteps()).toHaveLength(0);
    expect(toggle.textContent).toBe("Hide steps");

    handleCiPipelineClick(toggle);
    expect(hiddenSteps()).toHaveLength(document.querySelectorAll("[data-ci-steps]").length);
  });
});
