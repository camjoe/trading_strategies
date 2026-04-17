import { applyAccountConfigOptionsToAdminForm } from "../lib/account-config-options";
import { createAdminAccountsController } from "./admin/accounts";
import { createAdminArtifactsController } from "./admin/artifacts";
import { createAdminOperationsController } from "./admin/operations";
import { createAdminPromotionsController } from "./admin/promotions";
import { createAdminSectionsController } from "./admin/sections";
import { createAdminTestAccountController } from "./admin/test-account";
import type { AdminFeature, AdminFeatureOptions } from "./admin/types";


export type { AdminFeature, AdminFeatureOptions } from "./admin/types";


export function createAdminFeature(options: AdminFeatureOptions = {}): AdminFeature {
  const sectionsController = createAdminSectionsController();
  const operationsController = createAdminOperationsController();
  const promotionsController = createAdminPromotionsController();
  const artifactsController = createAdminArtifactsController();
  const testAccountController = createAdminTestAccountController();
  const accountsController = createAdminAccountsController(options, {
    loadOperationsOverview: operationsController.loadOperationsOverview,
    loadPromotionOverview: promotionsController.loadPromotionOverview,
  });

  function wireActions(): void {
    sectionsController.wireActions();
    accountsController.wireActions();
    operationsController.wireActions();
    promotionsController.wireActions();
    artifactsController.wireActions();
    testAccountController.wireActions();

    sectionsController.initialize();
    accountsController.initialize();
    applyAccountConfigOptionsToAdminForm();
    void artifactsController.loadCsvExports();
    void operationsController.loadOperationsOverview();
  }

  return {
    wireActions,
    loadDeleteAccounts: accountsController.loadDeleteAccounts,
  };
}
