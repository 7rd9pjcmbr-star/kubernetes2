# codprofit MVP

`pkg/codprofit` contains a self-contained MVP for COD risk + net profit analysis.

## Included components

- Rule-based calculator (`Calculate`)
- Service orchestration (`Service`)
- HTTP handlers + mux registration (`AnalysisHandler`, `NewMux`)
- PostgreSQL repositories for:
  - analyses
  - benchmarks
  - monthly usage
  - workspace plan provider
- SQL migrations under `migrations/`

## Quick wiring example

```go
db, err := sql.Open("postgres", dsn)
if err != nil {
    panic(err)
}

analysisRepo := codprofit.NewPostgresAnalysisRepository(db)
benchmarkRepo := codprofit.NewPostgresBenchmarkRepository(db)
usageRepo := codprofit.NewPostgresUsageRepository(db)
planProvider := codprofit.NewPostgresWorkspacePlanProvider(db)

svc := codprofit.NewService(
    analysisRepo,
    benchmarkRepo,
    usageRepo,
    planProvider,
    codprofit.RandomIDGenerator{},
    codprofit.RealClock{},
    codprofit.DefaultRuleConfig(),
)

handler := codprofit.NewAnalysisHandler(svc)
server := &http.Server{
    Addr:    ":8080",
    Handler: codprofit.NewMux(handler),
}
_ = server.ListenAndServe()
```

## Migration order

1. `migrations/001_init.sql`
2. `migrations/002_seed_benchmarks.sql`

## Run standalone API server

`cmd/codprofit-apiserver` starts an HTTP server with:
- `POST /api/v1/analysis/cod-profit`
- `GET /api/v1/analysis/{analysisId}`
- `GET /healthz`
- `GET /readyz`

Example:

```bash
CODPROFIT_DB_DRIVER=pgx \
CODPROFIT_DB_DSN="postgres://user:pass@localhost:5432/codprofit?sslmode=disable" \
CODPROFIT_LISTEN_ADDRESS=":8080" \
go run ./cmd/codprofit-apiserver
```

If `CODPROFIT_USE_WORKSPACE_PLAN_TABLE=true`, plan lookup reads from `codprofit_workspaces.plan`.
Otherwise `CODPROFIT_DEFAULT_PLAN` is used as a static fallback.

## Request headers expected by handler

- `X-User-Id`: used for create analysis
- `X-Workspace-Id`: used for get analysis

These are placeholders for auth/context middleware and can be replaced once integrated into a broader API stack.
