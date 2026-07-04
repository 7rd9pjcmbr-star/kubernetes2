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
	"os"
	"testing"
	"time"
)

func TestLoadFromEnvWithTracingAndLogging(t *testing.T) {
	envs := map[string]string{
		"PROXY_UPSTREAMS":           "http://localhost:8081",
		"PROXY_LOG_FORMAT":          "json",
		"PROXY_SERVICE_NAME":        "proxy-test",
		"PROXY_TRACE_OTLP_ENDPOINT": "otel-collector:4317",
		"PROXY_TRACE_OTLP_INSECURE": "false",
		"PROXY_TRACE_SAMPLE_RATIO":  "0.4",
		"PROXY_RATE_LIMIT_RPS":      "100",
		"PROXY_RATE_LIMIT_BURST":    "200",
		"PROXY_TRUST_FORWARDED":     "true",
		"PROXY_SHUTDOWN_TIMEOUT":    "10s",
		"PROXY_REQUEST_TIMEOUT":     "3s",
		"PROXY_READ_TIMEOUT":        "5s",
		"PROXY_WRITE_TIMEOUT":       "5s",
		"PROXY_IDLE_TIMEOUT":        "30s",
		"PROXY_LISTEN_ADDRESS":      ":8080",
	}
	restore := setEnvForTest(t, envs)
	defer restore()

	cfg, err := LoadFromEnv()
	if err != nil {
		t.Fatalf("LoadFromEnv should succeed: %v", err)
	}
	if cfg.LogFormat != "json" {
		t.Fatalf("unexpected log format: got=%q want=%q", cfg.LogFormat, "json")
	}
	if cfg.ServiceName != "proxy-test" {
		t.Fatalf("unexpected service name: got=%q want=%q", cfg.ServiceName, "proxy-test")
	}
	if cfg.TraceEndpoint != "otel-collector:4317" {
		t.Fatalf("unexpected trace endpoint: got=%q", cfg.TraceEndpoint)
	}
	if cfg.TraceInsecure {
		t.Fatalf("expected trace insecure=false")
	}
	if cfg.TraceSample != 0.4 {
		t.Fatalf("unexpected trace sample ratio: got=%v want=0.4", cfg.TraceSample)
	}
	if cfg.RequestTimeout != 3*time.Second {
		t.Fatalf("unexpected request timeout: got=%v want=3s", cfg.RequestTimeout)
	}
}

func TestLoadFromEnvRejectsInvalidLogFormat(t *testing.T) {
	restore := setEnvForTest(t, map[string]string{
		"PROXY_UPSTREAMS":  "http://localhost:8081",
		"PROXY_LOG_FORMAT": "yaml",
	})
	defer restore()

	_, err := LoadFromEnv()
	if err == nil {
		t.Fatalf("expected error for invalid log format")
	}
}

func TestLoadFromEnvRejectsInvalidTraceSampleRatio(t *testing.T) {
	restore := setEnvForTest(t, map[string]string{
		"PROXY_UPSTREAMS":          "http://localhost:8081",
		"PROXY_TRACE_SAMPLE_RATIO": "1.1",
	})
	defer restore()

	_, err := LoadFromEnv()
	if err == nil {
		t.Fatalf("expected error for invalid trace sample ratio")
	}
}

func setEnvForTest(t *testing.T, values map[string]string) func() {
	t.Helper()
	keys := []string{
		"PROXY_UPSTREAMS",
		"PROXY_LOG_FORMAT",
		"PROXY_SERVICE_NAME",
		"PROXY_TRACE_OTLP_ENDPOINT",
		"PROXY_TRACE_OTLP_INSECURE",
		"PROXY_TRACE_SAMPLE_RATIO",
		"PROXY_RATE_LIMIT_RPS",
		"PROXY_RATE_LIMIT_BURST",
		"PROXY_TRUST_FORWARDED",
		"PROXY_SHUTDOWN_TIMEOUT",
		"PROXY_REQUEST_TIMEOUT",
		"PROXY_READ_TIMEOUT",
		"PROXY_WRITE_TIMEOUT",
		"PROXY_IDLE_TIMEOUT",
		"PROXY_LISTEN_ADDRESS",
	}

	original := map[string]*string{}
	for _, key := range keys {
		value, ok := os.LookupEnv(key)
		if ok {
			v := value
			original[key] = &v
		} else {
			original[key] = nil
		}
		_ = os.Unsetenv(key)
	}
	for key, value := range values {
		_ = os.Setenv(key, value)
	}

	return func() {
		for _, key := range keys {
			if original[key] == nil {
				_ = os.Unsetenv(key)
				continue
			}
			_ = os.Setenv(key, *original[key])
		}
	}
}
