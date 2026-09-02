type MarketCategory = {
  category: string;
  market_growth?: number | null;
  store_units_sold?: number;
  store_revenue?: number;
  store_daily_units?: number;
  days_of_cover?: number | null;
  signal: "BUY" | "HOLD" | "REDUCE" | "MONITOR";
};

export type MarketIntelligence = {
  status: "available" | "unavailable";
  state: string;
  source: string;
  message?: string;
  as_of?: string | null;
  source_updated_at?: string | null;
  lookback_days?: number;
  statewide_growth?: number | null;
  average_retail_price_per_gram?: number | null;
  average_retail_price_change?: number | null;
  categories: MarketCategory[];
};

function percent(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString(undefined, { style: "percent", maximumFractionDigits: 1, signDisplay: "exceptZero" });
}

function money(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString(undefined, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function MarketPulse({ market }: { market: MarketIntelligence }) {
  if (market.status !== "available") {
    return (
      <section className="inventory-panel market-pulse market-pulse-unavailable">
        <div className="market-pulse-heading">
          <div>
            <h3>Massachusetts Market Pulse</h3>
            <p>{market.message || "Public market data is temporarily unavailable. Store-level Buyer Intelligence is unaffected."}</p>
          </div>
          <span className="status-pill neutral">Offline</span>
        </div>
      </section>
    );
  }

  return (
    <section className="inventory-panel market-pulse">
      <div className="market-pulse-heading">
        <div>
          <h3>Massachusetts Market Pulse</h3>
          <p>Native public-market context layered over this store&apos;s sales and inventory. Store evidence remains the primary buying signal.</p>
        </div>
        <span className="status-pill success">Native data</span>
      </div>

      <div className="metrics three market-pulse-metrics">
        <article className="metric"><span>Statewide trend</span><strong>{percent(market.statewide_growth)}</strong></article>
        <article className="metric"><span>Avg retail / gram</span><strong>{money(market.average_retail_price_per_gram)}</strong></article>
        <article className="metric"><span>Price movement</span><strong>{percent(market.average_retail_price_change)}</strong></article>
      </div>

      {market.categories.length ? (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Category</th><th>MA Trend</th><th>Store Units</th><th>Days Cover</th><th>Signal</th></tr></thead>
            <tbody>
              {market.categories.map((row) => (
                <tr key={row.category}>
                  <td>{row.category}</td>
                  <td>{percent(row.market_growth)}</td>
                  <td>{Number(row.store_units_sold || 0).toLocaleString(undefined, { maximumFractionDigits: 1 })}</td>
                  <td>{row.days_of_cover == null ? "—" : row.days_of_cover.toLocaleString(undefined, { maximumFractionDigits: 1 })}</td>
                  <td><strong>{row.signal}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <div className="info-banner">No comparable category-level market rows were available in the latest public dataset.</div>}

      <p className="market-pulse-source">Source: {market.source}{market.as_of ? ` · Market through ${market.as_of}` : ""}{market.source_updated_at ? ` · Source updated ${market.source_updated_at}` : ""}</p>
    </section>
  );
}
