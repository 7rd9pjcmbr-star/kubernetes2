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

package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"proxy-production-system/internal/proxy"
)

const (
	defaultListenAddress     = ":8080"
	defaultGatewayHTTP       = ":8888"
	defaultGatewaySocks      = ":1080"
	defaultReadTimeout       = 15 * time.Second
	defaultWriteTimeout      = 15 * time.Second
	defaultIdleTimeout       = 60 * time.Second
	defaultShutdownPeriod    = 20 * time.Second
	defaultStickyTTL         = 10 * time.Minute
	defaultHealthInterval    = 30 * time.Second
	defaultRotation          = proxy.RotationRoundRobin
	defaultSyncInterval      = 10 * time.Second
	defaultMetricsInterval   = 30 * time.Second
	defaultMongoDatabase     = "proxy_gateway"
	defaultMongoCollection   = "backends"
)

// Config contains runtime options for the proxy server.
type Config struct {
	ListenAddress  string
	Upstreams      []string
	StaticRoot     string
	ReadTimeout    time.Duration
	WriteTimeout   time.Duration
	IdleTimeout    time.Duration
	ShutdownPeriod time.Duration
	Gateway        GatewayConfig
}

// GatewayConfig configures the VN-style forward proxy gateway.
type GatewayConfig struct {
	Enabled       bool
	PoolEntries   []string
	PoolFiles     []string
	Rotation      proxy.RotationMode
	StickyTTL     time.Duration
	HTTPAddress   string
	SocksAddress  string
	AdminAddress  string
	GatewayUser   string
	GatewayPass   string
	ClientWhitelist []string
	HealthEvery   time.Duration
	AdminToken    string
	EliteMode     bool
	MongoURI        string
	MongoDatabase   string
	MongoCollection string
	SyncEvery       time.Duration
	MetricsEvery    time.Duration
}

func LoadFromEnv() (Config, error) {
	cfg := Config{
		ListenAddress:  getEnv("PROXY_LISTEN_ADDRESS", defaultListenAddress),
		StaticRoot:     strings.TrimSpace(os.Getenv("PROXY_STATIC_ROOT")),
		ReadTimeout:    getDurationEnv("PROXY_READ_TIMEOUT", defaultReadTimeout),
		WriteTimeout:   getDurationEnv("PROXY_WRITE_TIMEOUT", defaultWriteTimeout),
		IdleTimeout:    getDurationEnv("PROXY_IDLE_TIMEOUT", defaultIdleTimeout),
		ShutdownPeriod: getDurationEnv("PROXY_SHUTDOWN_TIMEOUT", defaultShutdownPeriod),
	}

	poolEntries := splitCSV(os.Getenv("PROXY_POOL"))
	poolFiles := splitCSV(os.Getenv("PROXY_POOL_FILES"))
	upstreams := splitCSV(os.Getenv("PROXY_UPSTREAMS"))
	cfg.Gateway = loadGatewayConfig(poolEntries, poolFiles)

	if cfg.Gateway.Enabled {
		if len(upstreams) == 0 {
			upstreams = []string{"http://127.0.0.1:65535"}
		}
	} else if len(upstreams) == 0 {
		return Config{}, fmt.Errorf("missing PROXY_UPSTREAMS or PROXY_POOL")
	}
	cfg.Upstreams = upstreams

	if err := validate(cfg); err != nil {
		return Config{}, err
	}
	return cfg, nil
}

func loadGatewayConfig(poolEntries, poolFiles []string) GatewayConfig {
	enabled := parseBool(os.Getenv("PROXY_GATEWAY_ENABLED"))
	if !enabled && len(poolEntries) > 0 {
		enabled = true
	}

	rotation, err := proxy.ParseRotationMode(getEnv("PROXY_ROTATION", string(defaultRotation)))
	if err != nil {
		rotation = defaultRotation
	}

	return GatewayConfig{
		Enabled:         enabled,
		PoolEntries:     poolEntries,
		PoolFiles:       poolFiles,
		Rotation:        rotation,
		StickyTTL:       getDurationEnv("PROXY_STICKY_TTL", defaultStickyTTL),
		HTTPAddress:     getEnv("PROXY_GATEWAY_HTTP_ADDRESS", defaultGatewayHTTP),
		SocksAddress:    getEnv("PROXY_GATEWAY_SOCKS_ADDRESS", defaultGatewaySocks),
		AdminAddress:    strings.TrimSpace(os.Getenv("PROXY_GATEWAY_ADMIN_ADDRESS")),
		GatewayUser:     strings.TrimSpace(os.Getenv("PROXY_GATEWAY_USER")),
		GatewayPass:     os.Getenv("PROXY_GATEWAY_PASS"),
		ClientWhitelist: splitCSV(os.Getenv("PROXY_CLIENT_WHITELIST")),
		HealthEvery:     getDurationEnv("PROXY_HEALTH_INTERVAL", defaultHealthInterval),
		AdminToken:      strings.TrimSpace(os.Getenv("PROXY_ADMIN_TOKEN")),
		EliteMode:       parseEliteMode(os.Getenv("PROXY_ELITE_MODE")),
		MongoURI:        strings.TrimSpace(os.Getenv("MONGO_URI")),
		MongoDatabase:   getEnv("MONGO_DATABASE", defaultMongoDatabase),
		MongoCollection: getEnv("MONGO_COLLECTION", defaultMongoCollection),
		SyncEvery:       getDurationEnv("MONGO_SYNC_INTERVAL", defaultSyncInterval),
		MetricsEvery:    getDurationEnv("MONGO_METRICS_FLUSH_INTERVAL", defaultMetricsInterval),
	}
}

func parseEliteMode(raw string) bool {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return true
	}
	value, err := strconv.ParseBool(raw)
	return err == nil && value
}

func validate(cfg Config) error {
	for _, upstream := range cfg.Upstreams {
		if !strings.HasPrefix(upstream, "http://") && !strings.HasPrefix(upstream, "https://") {
			return fmt.Errorf("invalid upstream %q: URL must start with http:// or https://", upstream)
		}
	}
	if cfg.Gateway.Enabled && len(cfg.Gateway.PoolEntries) == 0 && len(cfg.Gateway.PoolFiles) == 0 && cfg.Gateway.MongoURI == "" {
		return fmt.Errorf("PROXY_GATEWAY_ENABLED requires PROXY_POOL, PROXY_POOL_FILES, or MONGO_URI")
	}
	if cfg.ReadTimeout <= 0 || cfg.WriteTimeout <= 0 || cfg.IdleTimeout <= 0 || cfg.ShutdownPeriod <= 0 {
		return fmt.Errorf("timeouts must be greater than zero")
	}
	return nil
}

func getDurationEnv(key string, fallback time.Duration) time.Duration {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return fallback
	}
	duration, err := time.ParseDuration(raw)
	if err != nil {
		return fallback
	}
	if duration <= 0 {
		return fallback
	}
	return duration
}

func getEnv(key, fallback string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	return value
}

func splitCSV(value string) []string {
	if strings.TrimSpace(value) == "" {
		return nil
	}
	parts := strings.Split(value, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		trimmed := strings.TrimSpace(part)
		if trimmed != "" {
			out = append(out, trimmed)
		}
	}
	return out
}

func parseBool(raw string) bool {
	value, err := strconv.ParseBool(strings.TrimSpace(raw))
	return err == nil && value
}

// WorkerCountFromEnv reads optional proxy worker tuning.
func WorkerCountFromEnv() int {
	raw := strings.TrimSpace(os.Getenv("PROXY_WORKERS"))
	if raw == "" {
		return 0
	}
	workers, err := strconv.Atoi(raw)
	if err != nil || workers < 0 {
		return 0
	}
	return workers
}
