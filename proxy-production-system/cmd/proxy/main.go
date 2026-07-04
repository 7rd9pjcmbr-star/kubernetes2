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
	"log"
	"net/http"
	"os"
	"os/signal"
	"proxy-production-system/internal/config"
	"proxy-production-system/internal/proxy"
	"syscall"
	"time"
)

func main() {
	cfg, err := config.LoadFromEnv()
	if err != nil {
		log.Fatalf("failed to load config: %v", err)
	}

	handler, err := proxy.NewRoundRobinHandler(cfg.Upstreams, proxy.MiddlewareOptions{
		AuthToken:      cfg.AuthToken,
		RateLimitRPS:   cfg.RateLimitRPS,
		RateLimitBurst: cfg.RateLimitBurst,
		TrustForwarded: cfg.TrustForwarded,
	})
	if err != nil {
		log.Fatalf("failed to build proxy handler: %v", err)
	}

	server := &http.Server{
		Addr:         cfg.ListenAddress,
		Handler:      handler,
		ReadTimeout:  cfg.ReadTimeout,
		WriteTimeout: cfg.WriteTimeout,
		IdleTimeout:  cfg.IdleTimeout,
	}

	log.Printf(
		"proxy starting listen=%s upstreams=%v auth_enabled=%t rate_limit_rps=%d rate_limit_burst=%d trust_forwarded=%t",
		cfg.ListenAddress,
		cfg.Upstreams,
		cfg.AuthToken != "",
		cfg.RateLimitRPS,
		cfg.RateLimitBurst,
		cfg.TrustForwarded,
	)
	go func() {
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("proxy server failed: %v", err)
		}
	}()

	waitForSignal()
	log.Printf("shutdown requested")

	ctx, cancel := context.WithTimeout(context.Background(), cfg.ShutdownPeriod)
	defer cancel()
	if err := server.Shutdown(ctx); err != nil {
		log.Fatalf("graceful shutdown failed: %v", err)
	}
	log.Printf("proxy stopped cleanly")
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
