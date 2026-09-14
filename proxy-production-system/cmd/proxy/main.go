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
	"proxy-production-system/internal/store"
	"syscall"
	"time"
)

func main() {
	cfg, err := config.LoadFromEnv()
	if err != nil {
		log.Fatalf("failed to load config: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	if cfg.Gateway.Enabled {
		repo, err := store.OpenRepository(ctx, store.OpenConfig{
			MongoURI:        cfg.Gateway.MongoURI,
			MongoDatabase:   cfg.Gateway.MongoDatabase,
			MongoCollection: cfg.Gateway.MongoCollection,
		})
		if err != nil {
			log.Fatalf("failed to open backend repository: %v", err)
		}

		gatewayCfg := proxy.GatewayConfig{
			PoolEntries:  cfg.Gateway.PoolEntries,
			PoolFiles:    cfg.Gateway.PoolFiles,
			Rotation:     cfg.Gateway.Rotation,
			StickyTTL:    cfg.Gateway.StickyTTL,
			HTTPAddress:  cfg.Gateway.HTTPAddress,
			SocksAddress: cfg.Gateway.SocksAddress,
			HealthEvery:  cfg.Gateway.HealthEvery,
			AdminToken:   cfg.Gateway.AdminToken,
			EliteMode:    cfg.Gateway.EliteMode,
			SyncEvery:    cfg.Gateway.SyncEvery,
			MetricsEvery: cfg.Gateway.MetricsEvery,
			Auth: proxy.NewGatewayAuth(
				cfg.Gateway.GatewayUser,
				cfg.Gateway.GatewayPass,
				cfg.Gateway.ClientWhitelist,
			),
		}
		gateway, err := proxy.NewGateway(gatewayCfg, repo)
		if err != nil {
			log.Fatalf("failed to build gateway: %v", err)
		}
		go func() {
			if err := gateway.Start(ctx); err != nil {
				log.Printf("gateway stopped with error: %v", err)
				cancel()
			}
		}()

		if cfg.Gateway.AdminAddress != "" {
			adminServer := &http.Server{
				Addr:    cfg.Gateway.AdminAddress,
				Handler: gateway.AdminHandler(),
			}
			go func() {
				log.Printf("gateway admin listening addr=%s", cfg.Gateway.AdminAddress)
				if err := adminServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
					log.Printf("admin server failed: %v", err)
				}
			}()
			go func() {
				<-ctx.Done()
				shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), cfg.ShutdownPeriod)
				defer shutdownCancel()
				_ = adminServer.Shutdown(shutdownCtx)
			}()
		}

		stats := gateway.Manager().Stats()
		log.Printf("gateway enabled rotation=%s pool_total=%d pool_healthy=%d http=%s socks=%s mongo=%t",
			cfg.Gateway.Rotation, stats.Total, stats.Healthy, cfg.Gateway.HTTPAddress, cfg.Gateway.SocksAddress, cfg.Gateway.MongoURI != "")
	}

	handler, err := proxy.NewRoundRobinHandler(cfg.Upstreams, cfg.StaticRoot)
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

	log.Printf("proxy starting listen=%s upstreams=%v static_root=%q", cfg.ListenAddress, cfg.Upstreams, cfg.StaticRoot)
	go func() {
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("proxy server failed: %v", err)
		}
	}()

	waitForSignal()
	log.Printf("shutdown requested")
	cancel()

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), cfg.ShutdownPeriod)
	defer shutdownCancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
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
