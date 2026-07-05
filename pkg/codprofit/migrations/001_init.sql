CREATE TABLE IF NOT EXISTS codprofit_workspaces (
    id TEXT PRIMARY KEY,
    plan TEXT NOT NULL CHECK (plan IN ('free', 'starter', 'growth', 'team')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS codprofit_analyses (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES codprofit_workspaces(id),
    created_by TEXT NOT NULL,
    input_json JSONB NOT NULL,
    output_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_codprofit_analyses_workspace_created
    ON codprofit_analyses (workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS codprofit_benchmarks (
    category TEXT NOT NULL,
    province_code TEXT NOT NULL,
    baseline_return_rate_pct NUMERIC(5,2) NOT NULL CHECK (baseline_return_rate_pct BETWEEN 0 AND 100),
    carrier_delay_score NUMERIC(5,2) NOT NULL CHECK (carrier_delay_score BETWEEN 0 AND 100),
    price_band_risk_score NUMERIC(5,2) NOT NULL CHECK (price_band_risk_score BETWEEN 0 AND 100),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (category, province_code)
);

CREATE TABLE IF NOT EXISTS codprofit_usage_monthly (
    workspace_id TEXT NOT NULL REFERENCES codprofit_workspaces(id),
    month_key TEXT NOT NULL,
    analyses_count INT NOT NULL DEFAULT 0,
    exports_count INT NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, month_key)
);
