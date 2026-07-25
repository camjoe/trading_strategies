import "./styles.css";
import { find, findAll } from "./lib/dom";
import { createAccountsFeature } from "./features/accounts";
import { createAdminFeature } from "./features/admin";
import { init as initAutonomyMonitor } from "./features/autonomy-monitor";
import { applyAccountConfigOptionsToAdminForm, loadAccountConfigOptions } from "./lib/account-config-options";
import { createAltStrategiesFeature } from "./features/alt-strategies";
import { createBacktestingFeature } from "./features/backtesting";
import { createCompareFeature } from "./features/compare";
import { createPortfolioFeature } from "./features/portfolio";
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
import adminParametersTemplate from "./views/admin/parameters.html?raw";
import backtestingTemplate from "./views/backtesting.html?raw";
import accountsTemplate from "./views/accounts.html?raw";
import adminTemplate from "./views/admin.html?raw";
import compareTemplate from "./views/compare.html?raw";
import portfolioTemplate from "./views/portfolio.html?raw";
import altStrategiesTemplate from "./views/alt-strategies.html?raw";
import autonomyMonitorTemplate from "./views/autonomy-monitor.html?raw";
import strategyLabTemplate from "./views/strategy-lab.html?raw";
import { createStrategyLabFeature } from "./features/strategy-lab";
import { errorMessage } from "./lib/http";

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
    .replace("<!-- ADMIN_PROMOTIONS_PARTIAL -->", adminPromotionsTemplate)
    .replace("<!-- ADMIN_PARAMETERS_PARTIAL -->", adminParametersTemplate)
    .replace("<!-- ADMIN_ARTIFACTS_PARTIAL -->", adminArtifactsTemplate);
  app.innerHTML = appLayoutTemplate
    .replace("<!-- NAV_PARTIAL -->", navTemplate)
    .replace("<!-- LOGS_TAB_PARTIAL -->", logsTemplate)
    .replace("<!-- BACKTESTING_TAB_PARTIAL -->", backtestingTemplate)
    .replace("<!-- ACCOUNTS_TAB_PARTIAL -->", accountsTemplate)
    .replace("<!-- AUTONOMY_MONITOR_TAB_PARTIAL -->", autonomyMonitorTemplate)
    .replace("<!-- ADMIN_TAB_PARTIAL -->", resolvedAdminTemplate)
    .replace("<!-- COMPARE_TAB_PARTIAL -->", compareTemplate)
    .replace("<!-- PORTFOLIO_TAB_PARTIAL -->", portfolioTemplate)
    .replace("<!-- ALT_STRATEGIES_TAB_PARTIAL -->", altStrategiesTemplate)
    .replace("<!-- STRATEGY_LAB_TAB_PARTIAL -->", strategyLabTemplate)
    .replace("<!-- DOCS_TAB_PARTIAL -->", buildDocsTemplate());
  const demoBanner = find<HTMLElement>("#demoModeBanner");
  if (demoBanner && import.meta.env.VITE_DEMO_MODE === "1") {
    demoBanner.hidden = false;
  }
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
const portfolioFeature = createPortfolioFeature();
const logsFeature = createLogsFeature();
const altStrategiesFeature = createAltStrategiesFeature();
const strategyLabFeature = createStrategyLabFeature();

async function bootstrap(): Promise<void> {
  renderShell();
  initTabs();
  openTab("accounts");  // Set initial active tab
  initDocsFeature(openTab);
  accountsFeature.wireActions();
  adminFeature.wireActions();
  logsFeature.wireActions();
  compareFeature.wireActions();
  portfolioFeature.wireActions();
  backtestingFeature.wireActions();
  altStrategiesFeature.wireActions();
  strategyLabFeature.wireActions();
  initAutonomyMonitor({
    onOpenAccount: async (accountName, bookName) => {
      openTab("accounts");
      await accountsFeature.loadAccountDetail(accountName, { section: "books", bookName });
    },
    onOpenStrategyLab: () => openTab("strategy-lab"),
    onOpenParameters: () => {
      openTab("admin");
      document.querySelector<HTMLButtonElement>('[data-admin-section-target="parameters"]')?.click();
    },
  });

  try {
    await loadAccountConfigOptions();
    applyAccountConfigOptionsToAdminForm();
  } catch (error) {
    console.warn(`Failed to load account config options: ${errorMessage(error, "unknown error")}`);
  }

  await accountsFeature.loadAccounts();
  await adminFeature.loadDeleteAccounts();
  await logsFeature.loadLogFiles();
  await compareFeature.loadComparison();
  await portfolioFeature.loadRollup();
  await backtestingFeature.loadBacktestRuns();
  // Background fetch so the provider health badge is visible before the Alt Strategies tab is first opened
  void altStrategiesFeature.fetchProviderHealth();
  void strategyLabFeature.load();
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
