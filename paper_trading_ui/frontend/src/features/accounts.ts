import { createAccountsController } from "./accounts/controller";
import type { AccountsFeature, AccountsFeatureOptions } from "./accounts/types";

export type {
  AccountsFeature,
  AccountsFeatureOptions,
  DetailSection,
  LoadAccountDetailOptions,
} from "./accounts/types";

export function createAccountsFeature(options: AccountsFeatureOptions = {}): AccountsFeature {
  return createAccountsController(options);
}
