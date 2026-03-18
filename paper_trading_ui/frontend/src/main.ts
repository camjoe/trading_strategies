import "./styles.css";
import { find, findAll } from "./lib/dom";
import { createAccountsFeature } from "./features/accounts";
import { createBacktestingFeature } from "./features/backtesting";
import { createLogsFeature } from "./features/logs";
import { initDocsFeature } from "./features/docs";
import appLayoutTemplate from "./templates/app-layout.html?raw";
import navTemplate from "./templates/nav.html?raw";
import tradesTemplate from "./templates/trades.html?raw";
import backtestingTemplate from "./templates/backtesting.html?raw";
import accountsTemplate from "./templates/accounts.html?raw";
import docsTemplate from "./templates/docs.html?raw";

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
    .replace("<!-- DOCS_TAB_PARTIAL -->", docsTemplate);
}

const backtestingFeature = createBacktestingFeature();
const accountsFeature = createAccountsFeature({
  onAccountsLoaded: (accounts) => {
    backtestingFeature.setAccounts(accounts);
  },
  onOpenRunReport: (runId) => backtestingFeature.loadBacktestReport(runId),
});
const logsFeature = createLogsFeature();

async function bootstrap(): Promise<void> {
  renderShell();
  initTabs();
  initDocsFeature(openTab);
  accountsFeature.wireActions();
  logsFeature.wireActions();
  backtestingFeature.wireActions();
  await accountsFeature.loadAccounts();
  await logsFeature.loadLogFiles();
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
