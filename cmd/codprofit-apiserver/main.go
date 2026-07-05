/*
Copyright The Kubernetes Authors.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package main

import (
	"context"
	"database/sql"
	"errors"
	"flag"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"k8s.io/kubernetes/pkg/codprofit"
)

func main() {
	addr := flag.String("listen-address", getEnv("CODPROFIT_LISTEN_ADDRESS", ":8080"), "HTTP listen address")
	dbDriver := flag.String("db-driver", getEnv("CODPROFIT_DB_DRIVER", "pgx"), "database/sql driver name")
	dbDSN := flag.String("db-dsn", getEnv("CODPROFIT_DB_DSN", ""), "database DSN")
	defaultPlan := flag.String("default-plan", getEnv("CODPROFIT_DEFAULT_PLAN", "free"), "fallback workspace plan")
	flag.Parse()

	if *dbDSN == "" {
		log.Fatalf("missing CODPROFIT_DB_DSN or --db-dsn")
	}

	db, err := sql.Open(*dbDriver, *dbDSN)
	if err != nil {
		log.Fatalf("open db failed: %v", err)
	}
	defer db.Close()

	if err := db.Ping(); err != nil {
		log.Fatalf("database ping failed: %v", err)
	}

	analysisRepo := codprofit.NewPostgresAnalysisRepository(db)
	benchmarkRepo := codprofit.NewPostgresBenchmarkRepository(db)
	usageRepo := codprofit.NewPostgresUsageRepository(db)

	var planProvider codprofit.WorkspacePlanProvider = codprofit.StaticPlanProvider{DefaultPlan: *defaultPlan}
	if getEnv("CODPROFIT_USE_WORKSPACE_PLAN_TABLE", "false") == "true" {
		planProvider = codprofit.NewPostgresWorkspacePlanProvider(db)
	}

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
	mux := codprofit.NewMux(handler)
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	mux.HandleFunc("GET /readyz", func(w http.ResponseWriter, _ *http.Request) {
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		if err := db.PingContext(ctx); err != nil {
			http.Error(w, "db not ready", http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ready"))
	})

	server := &http.Server{
		Addr:              *addr,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		log.Printf("codprofit-apiserver listening on %s", *addr)
		if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("server error: %v", err)
		}
	}()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	<-sigCh

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := server.Shutdown(ctx); err != nil {
		log.Printf("graceful shutdown failed: %v", err)
	}
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
