import { find } from "../../lib/dom";
import { currency, esc, pct } from "../../lib/format";
import { getAccountConfigOptions } from "../../lib/account-config-options";
import { errorMessage, getJson, postJson } from "../../lib/http";
import { intOrUndefined, numOrUndefined, strOrUndefined } from "../../lib/form-parse";
import { TEST_ACCOUNT_NAME } from "../../lib/constants";
import type { AccountListItem, AdminCreateAccountPayload } from "../../types";
import type { AdminFeatureOptions, CreateResponse, DeleteResponse } from "./types";
import { setOutput } from "./ui";


export interface AdminAccountsDependencies {
  loadOperationsOverview: () => Promise<void>;
  loadPromotionOverview: () => Promise<void>;
}


export interface AdminAccountsController {
  initialize: () => void;
  loadDeleteAccounts: () => Promise<void>;
  wireActions: () => void;
}


function csvListOrUndefined(value: FormDataEntryValue | null): string[] | undefined {
  const raw = strOrUndefined(value);
  if (!raw) return undefined;
  return raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}


export function createAdminAccountsController(
  options: AdminFeatureOptions,
  dependencies: AdminAccountsDependencies,
): AdminAccountsController {
  function syncInstrumentDetails(form?: HTMLFormElement | null): void {
    const instrumentMode = form?.elements.namedItem("instrumentMode") as HTMLSelectElement | null;
    const instrumentDetails = find<HTMLDetailsElement>("#adminInstrumentAdvanced");
    if (!instrumentMode || !instrumentDetails) return;

    instrumentDetails.open = instrumentMode.value === "leaps";
  }

  function syncRotationDetails(form?: HTMLFormElement | null): void {
    const rotationEnabled = form?.elements.namedItem("rotationEnabled") as HTMLInputElement | null;
    const rotationDetails = find<HTMLDetailsElement>("#adminRotationDetails");
    if (!rotationEnabled || !rotationDetails) return;

    rotationDetails.open = rotationEnabled.checked;
  }

  async function loadDeleteAccounts(): Promise<void> {
    const deleteSelect = find<HTMLSelectElement>("#deleteAccountSelect");
    const promotionSelect = find<HTMLSelectElement>("#promotionAccountSelect");
    if (!deleteSelect && !promotionSelect) return;

    const data = await getJson<{ accounts: AccountListItem[] }>("/api/accounts");
    const managedAccounts = data.accounts.filter((a) => a.name !== TEST_ACCOUNT_NAME);
    const optionsHtml = managedAccounts
      .map((a) => `<option value="${esc(a.name)}">${esc(a.name)} (${esc(a.strategy)})</option>`)
      .join("");

    if (deleteSelect) {
      deleteSelect.innerHTML = `<option value="">Select account</option>${optionsHtml}`;
    }

    if (promotionSelect) {
      const priorValue = promotionSelect.value;
      promotionSelect.innerHTML = `<option value="">Select account</option>${optionsHtml}`;
      const nextValue = managedAccounts.some((account) => account.name === priorValue) ? priorValue : managedAccounts[0]?.name ?? "";
      promotionSelect.value = nextValue;
      if (nextValue) {
        await dependencies.loadPromotionOverview();
      } else {
        const output = find<HTMLDivElement>("#promotionOverviewOutput");
        if (output) {
          setOutput(output, "empty", "Create a managed account first to inspect promotion readiness.");
        }
      }
    }
  }

  async function onDeleteSubmit(event: Event): Promise<void> {
    event.preventDefault();
    const form = event.currentTarget as HTMLFormElement;
    const output = find<HTMLDivElement>("#deleteAccountOutput");
    if (!output) return;

    const data = new FormData(form);
    const accountName = strOrUndefined(data.get("accountName"));
    if (!accountName) {
      setOutput(output, "error", "Select an account first.");
      return;
    }

    const confirmed = window.confirm(
      `Delete account '${accountName}' and all related trades/backtests? This cannot be undone.`,
    );
    if (!confirmed) {
      setOutput(output, "empty", "Deletion cancelled.");
      return;
    }

    setOutput(output, "empty", "Deleting account...");

    try {
      const result = await postJson<DeleteResponse>("/api/admin/accounts/delete", {
        accountName,
        confirm: true,
      });
      setOutput(
        output,
        "success",
        `Deleted ${result.deleted.accounts} account.<br>` +
        `Removed ${result.deleted.trades} trades, ${result.deleted.equitySnapshots} snapshots, ` +
        `${result.deleted.backtestRuns} backtest runs.`,
        true,
      );
      await loadDeleteAccounts();
      await dependencies.loadOperationsOverview();
      await options.onAccountsChanged?.();
    } catch (error) {
      setOutput(output, "error", error instanceof Error ? error.message : "Delete failed.");
    }
  }

  async function onCreateSubmit(event: Event): Promise<void> {
    event.preventDefault();
    const form = event.currentTarget as HTMLFormElement;
    const output = find<HTMLDivElement>("#createAccountOutput");
    if (!output) return;

    const configOptions = getAccountConfigOptions();
    if (!configOptions) {
      setOutput(output, "error", "Account config options are unavailable.");
      return;
    }

    const data = new FormData(form);
    const rotationSchedule = csvListOrUndefined(data.get("rotationScheduleCsv")) ?? [];
    const rotationOverlayWatchlist = csvListOrUndefined(data.get("rotationOverlayWatchlistCsv"));

    const payload: AdminCreateAccountPayload = {
      name: strOrUndefined(data.get("name")),
      descriptiveName: strOrUndefined(data.get("descriptiveName")),
      strategy: strOrUndefined(data.get("strategy")),
      benchmarkTicker: strOrUndefined(data.get("benchmarkTicker")) ?? "SPY",
      initialCash: numOrUndefined(data.get("initialCash")),
      goalMinReturnPct: numOrUndefined(data.get("goalMinReturnPct")),
      goalMaxReturnPct: numOrUndefined(data.get("goalMaxReturnPct")),
      goalPeriod: strOrUndefined(data.get("goalPeriod")) ?? configOptions.defaults.goalPeriod,
      learningEnabled: data.get("learningEnabled") === "on",
      riskPolicy: strOrUndefined(data.get("riskPolicy")) ?? configOptions.defaults.riskPolicy,
      stopLossPct: numOrUndefined(data.get("stopLossPct")),
      takeProfitPct: numOrUndefined(data.get("takeProfitPct")),
      instrumentMode: strOrUndefined(data.get("instrumentMode")) ?? configOptions.defaults.instrumentMode,
      optionStrikeOffsetPct: numOrUndefined(data.get("optionStrikeOffsetPct")),
      optionMinDte: intOrUndefined(data.get("optionMinDte")),
      optionMaxDte: intOrUndefined(data.get("optionMaxDte")),
      optionType: strOrUndefined(data.get("optionType")),
      targetDeltaMin: numOrUndefined(data.get("targetDeltaMin")),
      targetDeltaMax: numOrUndefined(data.get("targetDeltaMax")),
      maxPremiumPerTrade: numOrUndefined(data.get("maxPremiumPerTrade")),
      maxContractsPerTrade: intOrUndefined(data.get("maxContractsPerTrade")),
      ivRankMin: numOrUndefined(data.get("ivRankMin")),
      ivRankMax: numOrUndefined(data.get("ivRankMax")),
      rollDteThreshold: intOrUndefined(data.get("rollDteThreshold")),
      profitTakePct: numOrUndefined(data.get("profitTakePct")),
      maxLossPct: numOrUndefined(data.get("maxLossPct")),
      rotationEnabled: data.get("rotationEnabled") === "on",
      rotationMode: strOrUndefined(data.get("rotationMode")) ?? configOptions.defaults.rotationMode,
      rotationOptimalityMode:
        strOrUndefined(data.get("rotationOptimalityMode")) ?? configOptions.defaults.rotationOptimalityMode,
      rotationIntervalDays: intOrUndefined(data.get("rotationIntervalDays")),
      rotationIntervalMinutes: intOrUndefined(data.get("rotationIntervalMinutes")),
      rotationLookbackDays: intOrUndefined(data.get("rotationLookbackDays")),
      rotationSchedule,
      rotationRegimeStrategyRiskOn: strOrUndefined(data.get("rotationRegimeStrategyRiskOn")),
      rotationRegimeStrategyNeutral: strOrUndefined(data.get("rotationRegimeStrategyNeutral")),
      rotationRegimeStrategyRiskOff: strOrUndefined(data.get("rotationRegimeStrategyRiskOff")),
      rotationOverlayMode:
        strOrUndefined(data.get("rotationOverlayMode")) ?? configOptions.defaults.rotationOverlayMode,
      rotationOverlayMinTickers: intOrUndefined(data.get("rotationOverlayMinTickers")),
      rotationOverlayConfidenceThreshold: numOrUndefined(data.get("rotationOverlayConfidenceThreshold")),
      rotationOverlayWatchlist,
      rotationActiveIndex: intOrUndefined(data.get("rotationActiveIndex")) ?? 0,
      rotationLastAt: strOrUndefined(data.get("rotationLastAt")),
      rotationActiveStrategy: strOrUndefined(data.get("rotationActiveStrategy")),
    };

    if (!payload.name || !payload.strategy || payload.initialCash === undefined) {
      setOutput(output, "error", "Name, strategy, and initial cash are required.");
      return;
    }

    setOutput(output, "empty", "Creating account...");

    try {
      const result = await postJson<CreateResponse>("/api/admin/accounts/create", payload);
      setOutput(
        output,
        "success",
        `Created account ${esc(result.account.name)}.<br>` +
        `Equity: ${currency.format(result.account.equity)} | Return: ${pct(result.account.totalChangePct)}`,
        true,
      );
      form.reset();
      syncInstrumentDetails(form);
      syncRotationDetails(form);
      await loadDeleteAccounts();
      await dependencies.loadOperationsOverview();
      await options.onAccountsChanged?.();
    } catch (error) {
      setOutput(output, "error", error instanceof Error ? error.message : "Create failed.");
    }
  }

  function wireActions(): void {
    const deleteForm = find<HTMLFormElement>("#deleteAccountForm");
    const createForm = find<HTMLFormElement>("#createAccountForm");
    const instrumentMode = find<HTMLSelectElement>("#adminInstrumentMode");
    const rotationEnabled = createForm?.elements.namedItem("rotationEnabled") as HTMLInputElement | null;

    deleteForm?.addEventListener("submit", (event) => {
      void onDeleteSubmit(event);
    });
    createForm?.addEventListener("submit", (event) => {
      void onCreateSubmit(event);
    });
    instrumentMode?.addEventListener("change", () => {
      syncInstrumentDetails(createForm);
    });
    rotationEnabled?.addEventListener("change", () => {
      syncRotationDetails(createForm);
    });
  }

  function initialize(): void {
    const createForm = find<HTMLFormElement>("#createAccountForm");
    syncInstrumentDetails(createForm);
    syncRotationDetails(createForm);
  }

  return {
    initialize,
    loadDeleteAccounts,
    wireActions,
  };
}
