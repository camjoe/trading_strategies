import { getAccountConfigOptions, renderOptionTags } from "../../lib/account-config-options";

export function riskPolicyOptions(currentPolicy: string): string {
  return renderOptionTags(getAccountConfigOptions()?.riskPolicies ?? [], currentPolicy);
}

export function instrumentModeOptions(currentMode: string): string {
  return renderOptionTags(getAccountConfigOptions()?.instrumentModes ?? [], currentMode);
}

export function optionTypeOptions(currentType: string | null): string {
  return renderOptionTags(getAccountConfigOptions()?.optionTypes ?? [], currentType ?? undefined, {
    includeEmpty: true,
  });
}
