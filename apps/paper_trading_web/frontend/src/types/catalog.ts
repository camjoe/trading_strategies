export type CatalogKind = "cli" | "job" | "tool";
export type CatalogRisk = "read-only" | "writes-local" | "broker";

export interface CatalogArgument {
  flags: string[];
  dest: string;
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
  risk: CatalogRisk;
  module: string | null;
  schedule: string | null;
  help: string;
  example: string;
  arguments: CatalogArgument[];
}

export interface CatalogGroup {
  name: string;
  kind: CatalogKind;
}

export interface CatalogData {
  schema_version: number;
  cli_invocation: string;
  groups: CatalogGroup[];
  commands: CatalogEntry[];
}

export interface CatalogFilter {
  query: string;
  kind: CatalogKind | "all";
  risk: CatalogRisk | "all";
}
