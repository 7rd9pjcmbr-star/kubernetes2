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

package proxy

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"time"

	"proxy-production-system/internal/store"
)

// GatewayConfig wires the VN-style forward proxy gateway.
type GatewayConfig struct {
	PoolEntries      []string
	PoolFiles        []string
	Rotation         RotationMode
	StickyTTL        time.Duration
	HTTPAddress      string
	SocksAddress     string
	Auth             GatewayAuth
	HealthEvery      time.Duration
	AdminToken       string
	EliteMode        bool
	SyncEvery        time.Duration
	MetricsEvery     time.Duration
}

// Gateway serves HTTP/SOCKS5 forward proxy plus admin CRUD and pool sync.
type Gateway struct {
	manager *PoolManager
	sync    *BackendSyncService
	auth    GatewayAuth
	config  GatewayConfig
}

func NewGateway(cfg GatewayConfig, repo store.BackendRepository) (*Gateway, error) {
	manager := NewPoolManager(cfg.Rotation, cfg.StickyTTL)
	syncService := NewBackendSyncService(repo, manager, cfg.SyncEvery, cfg.MetricsEvery)

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if err := syncService.InitialLoad(ctx, cfg.PoolEntries, cfg.PoolFiles); err != nil {
		return nil, fmt.Errorf("initial backend load: %w", err)
	}

	return &Gateway{
		manager: manager,
		sync:    syncService,
		auth:    cfg.Auth,
		config:  cfg,
	}, nil
}

func (g *Gateway) Manager() *PoolManager {
	return g.manager
}

func (g *Gateway) AdminHandler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, _ *http.Request) {
		stats := g.manager.Stats()
		status := http.StatusOK
		if stats.Total == 0 || stats.Healthy == 0 {
			status = http.StatusServiceUnavailable
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"status":  statusText(status),
			"healthy": stats.Healthy,
			"total":   stats.Total,
		})
	})
	mux.HandleFunc("GET /api/v1/pool/stats", func(w http.ResponseWriter, r *http.Request) {
		if !g.authorizeAdmin(r) {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		writeJSON(w, http.StatusOK, g.manager.Stats())
	})
	g.registerAdminRoutes(mux)
	return mux
}

func (g *Gateway) ForwardHTTPHandler() http.Handler {
	return &ForwardHTTPProxy{
		Pool:      g.manager,
		Auth:      g.auth,
		EliteMode: g.config.EliteMode,
	}
}

func (g *Gateway) Start(ctx context.Context) error {
	go g.sync.Run(ctx)

	checker := &HealthChecker{Pool: g.manager, Interval: g.config.HealthEvery}
	go checker.Run(ctx)

	errCh := make(chan error, 2)

	if g.config.HTTPAddress != "" {
		server := &http.Server{
			Addr:    g.config.HTTPAddress,
			Handler: g.ForwardHTTPHandler(),
		}
		go func() {
			log.Printf("http gateway listening addr=%s rotation=%s", g.config.HTTPAddress, g.config.Rotation)
			errCh <- server.ListenAndServe()
		}()
		go func() {
			<-ctx.Done()
			_ = server.Close()
		}()
	}

	if g.config.SocksAddress != "" {
		socks := &Socks5Server{
			Addr: g.config.SocksAddress,
			Pool: g.manager,
			Auth: g.auth,
		}
		go func() {
			errCh <- socks.ListenAndServe(ctx)
		}()
	}

	select {
	case <-ctx.Done():
		return nil
	case err := <-errCh:
		if err == http.ErrServerClosed {
			return nil
		}
		return fmt.Errorf("gateway server failed: %w", err)
	}
}

func (g *Gateway) authorizeAdmin(r *http.Request) bool {
	if g.config.AdminToken == "" {
		return true
	}
	return r.Header.Get("X-Admin-Token") == g.config.AdminToken
}

func statusText(code int) string {
	if code == http.StatusOK {
		return "ok"
	}
	return "degraded"
}
