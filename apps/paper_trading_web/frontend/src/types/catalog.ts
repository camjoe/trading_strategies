export type CatalogKind = "cli" | "job" | "tool";
export type CatalogRisk = "read-only" | "writes-local" | "broker";

export interface CatalogArgument {
  flags: string[];
  dest: string;
  scope: "global" | "command";
  positional: boolean;
  kind: "flag" | "value" | "repeatable";
  type: string;
  required: boolean;
  default: unknown;
  choices: string[] | null;
  help: string;
}

export interface CatalogEntry {
  name: string;
  kind: CatalogKind;
  group: string;
  family: string | null;
  risk: CatalogRisk;
  module: string | null;
  schedule: string | null;
  runnable: boolean;
  help: string;
  example: string;
  arguments: CatalogArgument[];
}

export interface CatalogGroup {
  name: string;
  kind: CatalogKind;
}

export interface CatalogFamily {
  name: string;
  help: string;
}

export interface CatalogData {
  schema_version: number;
  cli_invocation: string;
  groups: CatalogGroup[];
  families: CatalogFamily[];
  commands: CatalogEntry[];
}

export interface CatalogRunResult {
  name: string;
  command: string;
  exitCode: number | null;
  timedOut: boolean;
  truncated: boolean;
  durationSeconds: number;
  output: string;
}

export interface CatalogFilter {
  query: string;
  kind: CatalogKind | "all";
  risk: CatalogRisk | "all";
}
