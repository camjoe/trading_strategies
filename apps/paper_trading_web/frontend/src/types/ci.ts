export interface CiTrigger {
  event: string;
  branches: string[];
}

export interface CiStep {
  name: string;
  uses: string | null;
  run: string | null;
}

export interface CiJob {
  id: string;
  name: string;
  needs: string[];
  runs_on: string | null;
  condition: string | null;
  always_on_push: boolean;
  when_changed: string[];
  path_filters: Record<string, string[]>;
  steps: CiStep[];
}

export interface CiPipeline {
  schema_version: number;
  file: string;
  name: string;
  triggers: CiTrigger[];
  jobs: CiJob[];
}
