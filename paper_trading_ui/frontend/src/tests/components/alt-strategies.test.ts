import { describe, expect, it } from "vitest";

import type { ProviderStatus, SignalsResponse } from "../../types";
import { renderProviderCards, renderSignalRows } from "../../components/alt-strategies";

// ---------------------------------------------------------------------------
// renderProviderCards
// ---------------------------------------------------------------------------

describe("renderProviderCards", () => {
  it("renders an empty-state message when the list is empty", () => {
    const html = renderProviderCards([]);
    expect(html).toContain("No providers available");
  });

  it("renders a card for an available provider with key scores", () => {
    const provider: ProviderStatus = {
      name: "Policy",
      source_label: "etf-proxies",
      available: true,
      fetched_at: "2026-04-05T18:00:00.000Z",
      key_scores: { policy_risk_on_score: 0.72, policy_defensive_tilt: -0.01 },
    };

    const html = renderProviderCards([provider]);
    expect(html).toContain("Policy");
    expect(html).toContain("etf-proxies");
    expect(html).toContain("✓ Available");
    expect(html).toContain("policy_risk_on_score");
    expect(html).toContain("0.7200");
    // Should NOT show unavailable badge
    expect(html).not.toContain("✗ Unavailable");
  });

  it("renders an unavailable card with no score table", () => {
    const provider: ProviderStatus = {
      name: "News",
      source_label: "rss+vader",
      available: false,
      fetched_at: "2026-04-05T18:00:00.000Z",
      key_scores: {},
    };

    const html = renderProviderCards([provider]);
    expect(html).toContain("✗ Unavailable");
    expect(html).not.toContain("✓ Available");
    // Empty scores should render the dash placeholder
    expect(html).toContain("—");
  });

  it("escapes dangerous characters in provider name and source_label", () => {
    const provider: ProviderStatus = {
      name: "<script>",
      source_label: `"danger"`,
      available: false,
      fetched_at: "2026-04-05T18:00:00.000Z",
      key_scores: {},
    };

    const html = renderProviderCards([provider]);
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("&quot;danger&quot;");
  });

  it("renders multiple provider cards", () => {
    const providers: ProviderStatus[] = [
      { name: "Policy", source_label: "etf-proxies", available: true, fetched_at: "2026-04-05T18:00:00.000Z", key_scores: {} },
      { name: "News", source_label: "rss+vader", available: false, fetched_at: "2026-04-05T18:00:00.000Z", key_scores: {} },
      { name: "Social", source_label: "reddit+gtrends", available: true, fetched_at: "2026-04-05T18:00:00.000Z", key_scores: {} },
    ];

    const html = renderProviderCards(providers);
    expect(html).toContain("Policy");
    expect(html).toContain("News");
    expect(html).toContain("Social");
  });
});

// ---------------------------------------------------------------------------
// renderSignalRows
// ---------------------------------------------------------------------------

describe("renderSignalRows", () => {
  it("renders a table with the correct column headers", () => {
    const response: SignalsResponse = {
      ticker: "AAPL",
      signals: [],
    };

    const html = renderSignalRows(response);
    expect(html).toContain("Strategy");
    expect(html).toContain("Signal");
    expect(html).toContain("Available");
    expect(html).toContain("Key Features");
  });

  it("renders buy signal with .up class", () => {
    const response: SignalsResponse = {
      ticker: "AAPL",
      signals: [
        { strategy: "policy_regime", signal: "buy", available: true, features: { policy_risk_on_score: 0.72 } },
      ],
    };

    const html = renderSignalRows(response);
    expect(html).toContain('class="up"');
    expect(html).toContain("BUY");
    expect(html).toContain("policy_risk_on_score");
    expect(html).toContain("0.7200");
  });

  it("renders sell signal with .down class", () => {
    const response: SignalsResponse = {
      ticker: "AAPL",
      signals: [
        { strategy: "news_sentiment", signal: "sell", available: true, features: { news_sentiment_score: -0.25 } },
      ],
    };

    const html = renderSignalRows(response);
    expect(html).toContain('class="down"');
    expect(html).toContain("SELL");
  });

  it("renders hold signal with no directional class", () => {
    const response: SignalsResponse = {
      ticker: "AAPL",
      signals: [
        { strategy: "social_trend_rotation", signal: "hold", available: false, features: {} },
      ],
    };

    const html = renderSignalRows(response);
    expect(html).toContain('class=""');
    expect(html).toContain("HOLD");
    // Unavailable provider should show ✗
    expect(html).toContain("✗");
    // Empty features should show the dash placeholder
    expect(html).toContain("—");
  });

  it("escapes strategy names and feature keys", () => {
    const response: SignalsResponse = {
      ticker: "AAPL",
      signals: [
        { strategy: "<xss>", signal: "hold", available: true, features: { "<key>": 0.5 } },
      ],
    };

    const html = renderSignalRows(response);
    expect(html).not.toContain("<xss>");
    expect(html).toContain("&lt;xss&gt;");
    expect(html).not.toContain("<key>");
    expect(html).toContain("&lt;key&gt;");
  });
});
