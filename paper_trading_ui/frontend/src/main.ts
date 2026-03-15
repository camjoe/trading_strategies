import "./styles.css";
import { find } from "./lib/dom";
import { createAccountsFeature } from "./features/accounts";
import { createBacktestingFeature } from "./features/backtesting";
import { createLogsFeature } from "./features/logs";
import shellTemplate from "./templates/shell.html?raw";

const appRoot = find<HTMLDivElement>("#app");
if (!appRoot) {
  throw new Error("Missing #app root");
}
const app = appRoot;

function renderShell(): void {
  app.innerHTML = shellTemplate;
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
  accountsFeature.wireActions();
  logsFeature.wireActions();
  backtestingFeature.wireActions();
  await accountsFeature.loadAccounts();
  await logsFeature.loadLogFiles();
  await backtestingFeature.loadBacktestRuns();
}

function initTabs(): void {
  const tabBtns = document.querySelectorAll<HTMLButtonElement>(".tab-btn");
  const tabPanels = document.querySelectorAll<HTMLElement>(".tab-panel");

  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.tab;
      tabBtns.forEach((b) => b.classList.toggle("active", b === btn));
      tabPanels.forEach((panel) => {
        panel.hidden = panel.id !== `tab-${target}`;
      });
    });
  });
}

void bootstrap();
