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
)

const (
	defaultListenAddress  = ":8080"
	defaultReadTimeout    = 15 * time.Second
	defaultWriteTimeout   = 15 * time.Second
	defaultIdleTimeout    = 60 * time.Second
	defaultShutdownPeriod = 20 * time.Second
)

// Config contains runtime options for the proxy server.
type Config struct {
	ListenAddress  string
	Upstreams      []string
	ReadTimeout    time.Duration
	WriteTimeout   time.Duration
	IdleTimeout    time.Duration
	ShutdownPeriod time.Duration
}

func LoadFromEnv() (Config, error) {
	cfg := Config{
		ListenAddress:  getEnv("PROXY_LISTEN_ADDRESS", defaultListenAddress),
		ReadTimeout:    getDurationEnv("PROXY_READ_TIMEOUT", defaultReadTimeout),
		WriteTimeout:   getDurationEnv("PROXY_WRITE_TIMEOUT", defaultWriteTimeout),
		IdleTimeout:    getDurationEnv("PROXY_IDLE_TIMEOUT", defaultIdleTimeout),
		ShutdownPeriod: getDurationEnv("PROXY_SHUTDOWN_TIMEOUT", defaultShutdownPeriod),
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
