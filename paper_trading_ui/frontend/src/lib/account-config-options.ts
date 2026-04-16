import { getJson } from "./http";
import type { AccountConfigOptions } from "../types";

type OptionsKey =
  | "goalPeriods"
  | "riskPolicies"
  | "instrumentModes"
  | "optionTypes"
  | "rotationModes"
  | "rotationOptimalityModes"
  | "rotationOverlayModes";

let cachedOptions: AccountConfigOptions | null = null;

type RenderOptions = {
  includeEmpty?: boolean;
  emptyLabel?: string;
};

type AdminSelectConfig = {
  selector: string;
  optionsKey: OptionsKey;
  defaultKey?: keyof AccountConfigOptions["defaults"];
  includeEmpty?: boolean;
  emptyLabel?: string;
};

const ADMIN_SELECT_CONFIGS: AdminSelectConfig[] = [
  { selector: 'select[name="goalPeriod"]', optionsKey: "goalPeriods", defaultKey: "goalPeriod" },
  { selector: 'select[name="riskPolicy"]', optionsKey: "riskPolicies", defaultKey: "riskPolicy" },
  { selector: 'select[name="instrumentMode"]', optionsKey: "instrumentModes", defaultKey: "instrumentMode" },
  { selector: 'select[name="optionType"]', optionsKey: "optionTypes", includeEmpty: true, emptyLabel: "(none)" },
  { selector: 'select[name="rotationMode"]', optionsKey: "rotationModes", defaultKey: "rotationMode" },
  {
    selector: 'select[name="rotationOptimalityMode"]',
    optionsKey: "rotationOptimalityModes",
    defaultKey: "rotationOptimalityMode",
  },
  {
    selector: 'select[name="rotationOverlayMode"]',
    optionsKey: "rotationOverlayModes",
    defaultKey: "rotationOverlayMode",
  },
];

function buildValueList(values: readonly string[], currentValue: string | undefined): string[] {
  const deduped = new Set(values);
  if (currentValue) {
    deduped.add(currentValue);
  }
  return Array.from(deduped);
}

export function setAccountConfigOptions(options: AccountConfigOptions | null): void {
  cachedOptions = options;
}

export function resetAccountConfigOptions(): void {
  cachedOptions = null;
}

export function getAccountConfigOptions(): AccountConfigOptions | null {
  return cachedOptions;
}

export async function loadAccountConfigOptions(): Promise<AccountConfigOptions> {
  const options = await getJson<AccountConfigOptions>("/api/accounts/config/options");
  cachedOptions = options;
  return options;
}

export function renderOptionTags(
  values: readonly string[],
  currentValue: string | undefined,
  options: RenderOptions = {},
): string {
  const renderedValues = buildValueList(values, currentValue);
  const includeEmpty = options.includeEmpty === true;
  const emptyLabel = options.emptyLabel ?? "— none —";
  const emptySelected = includeEmpty && !currentValue;
  const valueOptions = renderedValues
    .map((value) => `<option value="${value}"${currentValue === value ? " selected" : ""}>${value}</option>`)
    .join("");
  if (!includeEmpty) {
    return valueOptions;
  }
  return `<option value=""${emptySelected ? " selected" : ""}>${emptyLabel}</option>${valueOptions}`;
}

export function applyAccountConfigOptionsToAdminForm(root: ParentNode = document): void {
  const options = getAccountConfigOptions();
  if (!options) {
    return;
  }

  for (const config of ADMIN_SELECT_CONFIGS) {
    const select = root.querySelector<HTMLSelectElement>(config.selector);
    if (!select) {
      continue;
    }
    const defaultValue = config.defaultKey ? options.defaults[config.defaultKey] : undefined;
    const currentValue = select.value || defaultValue;
    select.innerHTML = renderOptionTags(options[config.optionsKey], currentValue, {
      includeEmpty: config.includeEmpty,
      emptyLabel: config.emptyLabel,
    });
    if (currentValue !== undefined) {
      select.value = currentValue;
    }
  }
}
