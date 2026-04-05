import "./styles.css";
import { find, findAll } from "./lib/dom";
import { createAccountsFeature } from "./features/accounts";
import { createAdminFeature } from "./features/admin";
import { createAltStrategiesFeature } from "./features/alt-strategies";
import { createBacktestingFeature } from "./features/backtesting";
import { createCompareFeature } from "./features/compare";
import { createLogsFeature } from "./features/logs";
import { createTestAccountFeature } from "./features/test-account";
import { initDocsFeature } from "./features/docs";
import { buildDocsTemplate } from "./lib/docs-renderer";
import appLayoutTemplate from "./views/app-layout.html?raw";
import navTemplate from "./views/nav.html?raw";
import tradesTemplate from "./views/trades.html?raw";
import backtestingTemplate from "./views/backtesting.html?raw";
import accountsTemplate from "./views/accounts.html?raw";
import adminTemplate from "./views/admin.html?raw";
import compareTemplate from "./views/compare.html?raw";
import testAccountTemplate from "./views/test-account.html?raw";
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
  app.innerHTML = appLayoutTemplate
    .replace("<!-- NAV_PARTIAL -->", navTemplate)
    .replace("<!-- TRADES_TAB_PARTIAL -->", tradesTemplate)
    .replace("<!-- BACKTESTING_TAB_PARTIAL -->", backtestingTemplate)
    .replace("<!-- ACCOUNTS_TAB_PARTIAL -->", accountsTemplate)
    .replace("<!-- TEST_ACCOUNT_TAB_PARTIAL -->", testAccountTemplate)
    .replace("<!-- ADMIN_TAB_PARTIAL -->", adminTemplate)
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
const compareFeature = createCompareFeature();
const adminFeature = createAdminFeature({
  onAccountsChanged: async () => {
    await accountsFeature.loadAccounts();
    await adminFeature.loadDeleteAccounts();
    await compareFeature.loadComparison();
  },
});
const logsFeature = createLogsFeature();
const testAccountFeature = createTestAccountFeature();
const altStrategiesFeature = createAltStrategiesFeature();

async function bootstrap(): Promise<void> {
  renderShell();
  initTabs();
  initDocsFeature(openTab);
  accountsFeature.wireActions();
  adminFeature.wireActions();
  logsFeature.wireActions();
  compareFeature.wireActions();
  backtestingFeature.wireActions();
  testAccountFeature.wireActions();
  altStrategiesFeature.wireActions();
  await accountsFeature.loadAccounts();
  await adminFeature.loadDeleteAccounts();
  await logsFeature.loadLogFiles();
  await compareFeature.loadComparison();
  await backtestingFeature.loadBacktestRuns();
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
