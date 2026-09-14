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
)

// GatewayConfig wires the VN-style forward proxy gateway.
type GatewayConfig struct {
	PoolEntries   []string
	Rotation      RotationMode
	StickyTTL     time.Duration
	HTTPAddress   string
	SocksAddress  string
	Auth          GatewayAuth
	HealthEvery   time.Duration
	AdminToken    string
	EliteMode     bool
}

// Gateway serves HTTP/SOCKS5 forward proxy plus a small admin API.
type Gateway struct {
	pool   *GatewayPool
	auth   GatewayAuth
	config GatewayConfig
}

func NewGateway(cfg GatewayConfig) (*Gateway, error) {
	pool, err := NewGatewayPool(cfg.PoolEntries, cfg.Rotation, cfg.StickyTTL)
	if err != nil {
		return nil, err
	}
	return &Gateway{
		pool:   pool,
		auth:   cfg.Auth,
		config: cfg,
	}, nil
}

func (g *Gateway) Pool() *GatewayPool {
	return g.pool
}

func (g *Gateway) AdminHandler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		stats := g.pool.Stats()
		status := http.StatusOK
		if stats.Healthy == 0 {
			status = http.StatusServiceUnavailable
		}
		w.WriteHeader(status)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"status":  statusText(status),
			"healthy": stats.Healthy,
			"total":   stats.Total,
		})
	})
	mux.HandleFunc("/api/v1/pool/stats", func(w http.ResponseWriter, r *http.Request) {
		if !g.authorizeAdmin(r) {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(g.pool.Stats())
	})
	return mux
}

func (g *Gateway) ForwardHTTPHandler() http.Handler {
	return &ForwardHTTPProxy{
		Pool:      g.pool,
		Auth:      g.auth,
		EliteMode: g.config.EliteMode,
	}
}

func (g *Gateway) Start(ctx context.Context) error {
	checker := &HealthChecker{Pool: g.pool, Interval: g.config.HealthEvery}
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
			Pool: g.pool,
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
