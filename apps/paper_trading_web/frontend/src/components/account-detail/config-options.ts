import { getAccountConfigOptions, renderOptionTags } from "../../lib/account-config-options";

export function riskPolicyOptions(currentPolicy: string): string {
  return renderOptionTags(getAccountConfigOptions()?.riskPolicies ?? [], currentPolicy);
}

export function instrumentModeOptions(currentMode: string): string {
  return renderOptionTags(getAccountConfigOptions()?.instrumentModes ?? [], currentMode);
}

export function rotationModeOptions(currentMode: string): string {
  return renderOptionTags(getAccountConfigOptions()?.rotationModes ?? [], currentMode);
}

export function rotationOptimalityOptions(currentMode: string): string {
  return renderOptionTags(getAccountConfigOptions()?.rotationOptimalityModes ?? [], currentMode);
}

export function rotationOverlayModeOptions(currentMode: string): string {
  return renderOptionTags(getAccountConfigOptions()?.rotationOverlayModes ?? [], currentMode);
}

export function optionTypeOptions(currentType: string | null): string {
  return renderOptionTags(getAccountConfigOptions()?.optionTypes ?? [], currentType ?? undefined, {
    includeEmpty: true,
  });
}
