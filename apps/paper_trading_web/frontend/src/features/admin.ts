import { applyAccountConfigOptionsToAdminForm } from "../lib/account-config-options";
import { createAdminAccountsController } from "./admin/accounts";
import { createAdminArtifactsController } from "./admin/artifacts";
import { createAdminOperationsController } from "./admin/operations";
import { createAdminPromotionsController } from "./admin/promotions";
import { createAdminParametersController } from "./admin/parameters";
import { createAdminSectionsController } from "./admin/sections";
import type { AdminFeature, AdminFeatureOptions } from "./admin/types";


export type { AdminFeature, AdminFeatureOptions } from "./admin/types";


export function createAdminFeature(options: AdminFeatureOptions = {}): AdminFeature {
  const sectionsController = createAdminSectionsController();
  const operationsController = createAdminOperationsController();
  const promotionsController = createAdminPromotionsController();
  const artifactsController = createAdminArtifactsController();
  const parametersController = createAdminParametersController();
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
    parametersController.wireActions();

    sectionsController.initialize();
    accountsController.initialize();
    applyAccountConfigOptionsToAdminForm();
    void artifactsController.loadCsvExports();
    void operationsController.loadOperationsOverview();
    void parametersController.initialize();
  }

  return {
    wireActions,
    loadDeleteAccounts: accountsController.loadDeleteAccounts,
  };
}
