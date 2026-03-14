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

function renderShell(): void {
  appRoot.innerHTML = shellTemplate;
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
  accountsFeature.wireActions();
  logsFeature.wireActions();
  backtestingFeature.wireActions();
  await accountsFeature.loadAccounts();
  await logsFeature.loadLogFiles();
  await backtestingFeature.loadBacktestRuns();
}

void bootstrap();
