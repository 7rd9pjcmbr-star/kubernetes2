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
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"proxy-production-system/internal/config"
	"proxy-production-system/internal/observability"
	"proxy-production-system/internal/proxy"
	"syscall"
	"time"

	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

func main() {
	cfg, err := config.LoadFromEnv()
	if err != nil {
		_, _ = fmt.Fprintf(os.Stderr, "failed to load config: %v\n", err)
		os.Exit(1)
	}
	observability.ConfigureLogger(cfg.LogFormat)

	traceShutdown, err := observability.ConfigureTracing(context.Background(), observability.TracingConfig{
		ServiceName: cfg.ServiceName,
		Endpoint:    cfg.TraceEndpoint,
		Insecure:    cfg.TraceInsecure,
		SampleRatio: cfg.TraceSample,
	})
	if err != nil {
		slog.Error("failed to initialize tracing", "error", err)
		os.Exit(1)
	}
	defer func() {
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := traceShutdown(shutdownCtx); err != nil {
			slog.Error("failed to shutdown tracing provider", "error", err)
		}
	}()

	metrics := proxy.NewMetrics()
	handler, err := proxy.NewRoundRobinHandler(cfg.Upstreams, proxy.MiddlewareOptions{
		AuthToken:      cfg.AuthToken,
		RateLimitRPS:   cfg.RateLimitRPS,
		RateLimitBurst: cfg.RateLimitBurst,
		TrustForwarded: cfg.TrustForwarded,
		RequestTimeout: cfg.RequestTimeout,
		Metrics:        metrics,
	})
	if err != nil {
		slog.Error("failed to build proxy handler", "error", err)
		os.Exit(1)
	}
	handler = otelhttp.NewHandler(handler, "proxy-http-server")

	server := &http.Server{
		Addr:         cfg.ListenAddress,
		Handler:      handler,
		ReadTimeout:  cfg.ReadTimeout,
		WriteTimeout: cfg.WriteTimeout,
		IdleTimeout:  cfg.IdleTimeout,
	}

	slog.Info("proxy starting",
		"listen", cfg.ListenAddress,
		"upstreams", cfg.Upstreams,
		"auth_enabled", cfg.AuthToken != "",
		"rate_limit_rps", cfg.RateLimitRPS,
		"rate_limit_burst", cfg.RateLimitBurst,
		"trust_forwarded", cfg.TrustForwarded,
		"request_timeout", cfg.RequestTimeout.String(),
		"log_format", cfg.LogFormat,
		"service_name", cfg.ServiceName,
		"trace_endpoint", cfg.TraceEndpoint,
		"trace_sample_ratio", cfg.TraceSample,
	)
	go func() {
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("proxy server failed", "error", err)
			os.Exit(1)
		}
	}()

	waitForSignal()
	slog.Info("shutdown requested")

	ctx, cancel := context.WithTimeout(context.Background(), cfg.ShutdownPeriod)
	defer cancel()
	if err := server.Shutdown(ctx); err != nil {
		slog.Error("graceful shutdown failed", "error", err)
		os.Exit(1)
	}
	slog.Info("proxy stopped cleanly")
}

func waitForSignal() {
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, syscall.SIGINT, syscall.SIGTERM)
	defer signal.Stop(signals)

	select {
	case <-signals:
	case <-time.After(24 * time.Hour):
	}
}
