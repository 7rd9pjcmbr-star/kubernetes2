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
	"math"
	"os"
	"strconv"
	"strings"
	"time"
)

const (
	defaultListenAddress  = ":8080"
	defaultReadTimeout    = 15 * time.Second
	defaultWriteTimeout   = 15 * time.Second
	defaultIdleTimeout    = 60 * time.Second
	defaultShutdownPeriod = 20 * time.Second
	defaultServiceName    = "proxy-production-system"
)

// Config contains runtime options for the proxy server.
type Config struct {
	ListenAddress  string
	Upstreams      []string
	ReadTimeout    time.Duration
	WriteTimeout   time.Duration
	IdleTimeout    time.Duration
	ShutdownPeriod time.Duration
	AuthToken      string
	RateLimitRPS   int
	RateLimitBurst int
	TrustForwarded bool
	LogFormat      string
	ServiceName    string
	TraceEndpoint  string
	TraceInsecure  bool
	TraceSample    float64
}

func LoadFromEnv() (Config, error) {
	cfg := Config{
		ListenAddress:  getEnv("PROXY_LISTEN_ADDRESS", defaultListenAddress),
		ReadTimeout:    getDurationEnv("PROXY_READ_TIMEOUT", defaultReadTimeout),
		WriteTimeout:   getDurationEnv("PROXY_WRITE_TIMEOUT", defaultWriteTimeout),
		IdleTimeout:    getDurationEnv("PROXY_IDLE_TIMEOUT", defaultIdleTimeout),
		ShutdownPeriod: getDurationEnv("PROXY_SHUTDOWN_TIMEOUT", defaultShutdownPeriod),
		AuthToken:      strings.TrimSpace(os.Getenv("PROXY_AUTH_TOKEN")),
		RateLimitRPS:   getIntEnv("PROXY_RATE_LIMIT_RPS", 0),
		RateLimitBurst: getIntEnv("PROXY_RATE_LIMIT_BURST", 0),
		TrustForwarded: getBoolEnv("PROXY_TRUST_FORWARDED", false),
		LogFormat:      strings.ToLower(getEnv("PROXY_LOG_FORMAT", "json")),
		ServiceName:    getEnv("PROXY_SERVICE_NAME", defaultServiceName),
		TraceEndpoint:  strings.TrimSpace(os.Getenv("PROXY_TRACE_OTLP_ENDPOINT")),
		TraceInsecure:  getBoolEnv("PROXY_TRACE_OTLP_INSECURE", true),
		TraceSample:    getFloatEnv("PROXY_TRACE_SAMPLE_RATIO", 1.0),
	}

	upstreams := splitTrim(os.Getenv("PROXY_UPSTREAMS"))
	if len(upstreams) == 0 {
		return Config{}, fmt.Errorf("missing PROXY_UPSTREAMS, expected comma-separated upstream URLs")
	}
	cfg.Upstreams = upstreams

	if err := validate(cfg); err != nil {
		return Config{}, err
	}
	return cfg, nil
}

func validate(cfg Config) error {
	for _, upstream := range cfg.Upstreams {
		if !strings.HasPrefix(upstream, "http://") && !strings.HasPrefix(upstream, "https://") {
			return fmt.Errorf("invalid upstream %q: URL must start with http:// or https://", upstream)
		}
	}
	if cfg.ReadTimeout <= 0 || cfg.WriteTimeout <= 0 || cfg.IdleTimeout <= 0 || cfg.ShutdownPeriod <= 0 {
		return fmt.Errorf("timeouts must be greater than zero")
	}
	if cfg.RateLimitRPS < 0 || cfg.RateLimitBurst < 0 {
		return fmt.Errorf("rate limit values must be greater than or equal to zero")
	}
	if cfg.RateLimitRPS > 0 && cfg.RateLimitBurst == 0 {
		return fmt.Errorf("PROXY_RATE_LIMIT_BURST must be set when PROXY_RATE_LIMIT_RPS is enabled")
	}
	if cfg.LogFormat != "json" && cfg.LogFormat != "text" {
		return fmt.Errorf("invalid PROXY_LOG_FORMAT=%q, supported values: json,text", cfg.LogFormat)
	}
	if cfg.ServiceName == "" {
		return fmt.Errorf("PROXY_SERVICE_NAME must not be empty")
	}
	if cfg.TraceSample < 0 || cfg.TraceSample > 1 || math.IsNaN(cfg.TraceSample) {
		return fmt.Errorf("PROXY_TRACE_SAMPLE_RATIO must be in range [0,1]")
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

func getIntEnv(key string, fallback int) int {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return fallback
	}
	value, err := strconv.Atoi(raw)
	if err != nil {
		return fallback
	}
	return value
}

func getBoolEnv(key string, fallback bool) bool {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return fallback
	}
	value, err := strconv.ParseBool(raw)
	if err != nil {
		return fallback
	}
	return value
}

func getFloatEnv(key string, fallback float64) float64 {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return fallback
	}
	value, err := strconv.ParseFloat(raw, 64)
	if err != nil {
		return fallback
	}
	return value
}

func splitTrim(value string) []string {
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
