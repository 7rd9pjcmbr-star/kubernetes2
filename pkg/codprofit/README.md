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

## Request headers expected by handler

- `X-User-Id`: used for create analysis
- `X-Workspace-Id`: used for get analysis

These are placeholders for auth/context middleware and can be replaced once integrated into a broader API stack.
