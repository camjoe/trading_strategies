import "./styles.css";
import { find, findAll } from "./lib/dom";
import { createAccountsFeature } from "./features/accounts";
import { createAdminFeature } from "./features/admin";
import { applyAccountConfigOptionsToAdminForm, loadAccountConfigOptions } from "./lib/account-config-options";
import { createAltStrategiesFeature } from "./features/alt-strategies";
import { createBacktestingFeature } from "./features/backtesting";
import { createCompareFeature } from "./features/compare";
import { createLogsFeature } from "./features/logs";
import { initDocsFeature } from "./features/docs";
import { buildDocsTemplate } from "./lib/docs-renderer";
import appLayoutTemplate from "./views/app-layout.html?raw";
import navTemplate from "./views/nav.html?raw";
import logsTemplate from "./views/trades.html?raw";
import adminArtifactsTemplate from "./views/admin/artifacts.html?raw";
import adminAccountsTemplate from "./views/admin/accounts.html?raw";
import adminJobsTemplate from "./views/admin/jobs.html?raw";
import adminOverviewTemplate from "./views/admin/overview.html?raw";
import adminPromotionsTemplate from "./views/admin/promotions.html?raw";
import adminTestAccountTemplate from "./views/admin/test-account.html?raw";
import backtestingTemplate from "./views/backtesting.html?raw";
import accountsTemplate from "./views/accounts.html?raw";
import adminTemplate from "./views/admin.html?raw";
import compareTemplate from "./views/compare.html?raw";
import altStrategiesTemplate from "./views/alt-strategies.html?raw";

const appRoot = find<HTMLDivElement>("#app");
if (!appRoot) {
  throw new Error("Missing #app root");
}
const app = appRoot;

function openTab(target: string): void {
  const tabBtns = findAll<HTMLButtonElement>(".tab-btn");
  const tabPanels = findAll<HTMLElement>(".tab-panel");

  tabBtns.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === target);
  });
  tabPanels.forEach((panel) => {
    panel.hidden = panel.id !== `tab-${target}`;
  });
}

function renderShell(): void {
  const resolvedAdminTemplate = adminTemplate
    .replace("<!-- ADMIN_OVERVIEW_PARTIAL -->", adminOverviewTemplate)
    .replace("<!-- ADMIN_JOBS_PARTIAL -->", adminJobsTemplate)
    .replace("<!-- ADMIN_ACCOUNTS_PARTIAL -->", adminAccountsTemplate)
    .replace("<!-- ADMIN_TEST_ACCOUNT_PARTIAL -->", adminTestAccountTemplate)
    .replace("<!-- ADMIN_PROMOTIONS_PARTIAL -->", adminPromotionsTemplate)
    .replace("<!-- ADMIN_ARTIFACTS_PARTIAL -->", adminArtifactsTemplate);
  app.innerHTML = appLayoutTemplate
    .replace("<!-- NAV_PARTIAL -->", navTemplate)
    .replace("<!-- LOGS_TAB_PARTIAL -->", logsTemplate)
    .replace("<!-- BACKTESTING_TAB_PARTIAL -->", backtestingTemplate)
    .replace("<!-- ACCOUNTS_TAB_PARTIAL -->", accountsTemplate)
    .replace("<!-- ADMIN_TAB_PARTIAL -->", resolvedAdminTemplate)
    .replace("<!-- COMPARE_TAB_PARTIAL -->", compareTemplate)
    .replace("<!-- ALT_STRATEGIES_TAB_PARTIAL -->", altStrategiesTemplate)
    .replace("<!-- DOCS_TAB_PARTIAL -->", buildDocsTemplate());
}

const backtestingFeature = createBacktestingFeature();
const accountsFeature = createAccountsFeature({
  onAccountsLoaded: (accounts) => {
    backtestingFeature.setAccounts(accounts);
  },
  onOpenRunReport: (runId) => backtestingFeature.loadBacktestReport(runId),
});
const compareFeature = createCompareFeature({
  onOpenAccount: async (accountName) => {
    openTab("accounts");
    await accountsFeature.loadAccountDetail(accountName);
  },
});
const adminFeature = createAdminFeature({
  onAccountsChanged: async () => {
    await accountsFeature.loadAccounts();
    await adminFeature.loadDeleteAccounts();
    await compareFeature.loadComparison();
  },
});
const logsFeature = createLogsFeature();
const altStrategiesFeature = createAltStrategiesFeature();

async function bootstrap(): Promise<void> {
  renderShell();
  await loadAccountConfigOptions();
  applyAccountConfigOptionsToAdminForm();
  initTabs();
  initDocsFeature(openTab);
  accountsFeature.wireActions();
  adminFeature.wireActions();
  logsFeature.wireActions();
  compareFeature.wireActions();
  backtestingFeature.wireActions();
  altStrategiesFeature.wireActions();
  await accountsFeature.loadAccounts();
  await adminFeature.loadDeleteAccounts();
  await logsFeature.loadLogFiles();
  await compareFeature.loadComparison();
  await backtestingFeature.loadBacktestRuns();
  // Background fetch so the provider health badge is visible before the Alt Strategies tab is first opened
  void altStrategiesFeature.fetchProviderHealth();
}

function initTabs(): void {
  const tabBtns = findAll<HTMLButtonElement>(".tab-btn");

  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.tab;
      if (!target) {
        return;
      }
      openTab(target);
    });
  });
}

void bootstrap();
