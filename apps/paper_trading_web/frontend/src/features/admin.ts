import { applyAccountConfigOptionsToAdminForm } from "../lib/account-config-options";
import { createAdminAccountsController } from "./admin/accounts";
import { createAdminOperationsController } from "./admin/operations";
import { createAdminPromotionsController } from "./admin/promotions";
import { createAdminSectionsController } from "./admin/sections";
import type { AdminFeature, AdminFeatureOptions } from "./admin/types";


export type { AdminFeature, AdminFeatureOptions } from "./admin/types";


export function createAdminFeature(options: AdminFeatureOptions = {}): AdminFeature {
  const sectionsController = createAdminSectionsController();
  const operationsController = createAdminOperationsController();
  const promotionsController = createAdminPromotionsController();
  const accountsController = createAdminAccountsController(options, {
    loadOperationsOverview: operationsController.loadOperationsOverview,
    loadPromotionOverview: promotionsController.loadPromotionOverview,
  });

  function wireActions(): void {
    sectionsController.wireActions();
    accountsController.wireActions();
    operationsController.wireActions();
    promotionsController.wireActions();

    sectionsController.initialize();
    accountsController.initialize();
    applyAccountConfigOptionsToAdminForm();
    void operationsController.loadOperationsOverview();
  }

  return {
    wireActions,
    loadDeleteAccounts: accountsController.loadDeleteAccounts,
  };
}
