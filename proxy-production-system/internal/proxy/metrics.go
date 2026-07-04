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
	"net/http"
	"strconv"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

type Metrics struct {
	registry         *prometheus.Registry
	requestsTotal    *prometheus.CounterVec
	requestDuration  *prometheus.HistogramVec
	authRejectsTotal prometheus.Counter
	rateLimitRejects prometheus.Counter
	upstreamErrors   prometheus.Counter
}

func NewMetrics() *Metrics {
	registry := prometheus.NewRegistry()
	metrics := &Metrics{
		registry: registry,
		requestsTotal: prometheus.NewCounterVec(
			prometheus.CounterOpts{
				Name: "proxy_requests_total",
				Help: "Total HTTP requests handled by the proxy.",
			},
			[]string{"method", "path", "status_code"},
		),
		requestDuration: prometheus.NewHistogramVec(
			prometheus.HistogramOpts{
				Name:    "proxy_request_duration_seconds",
				Help:    "Request latency in seconds.",
				Buckets: []float64{0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5},
			},
			[]string{"method", "path"},
		),
		authRejectsTotal: prometheus.NewCounter(
			prometheus.CounterOpts{
				Name: "proxy_auth_rejections_total",
				Help: "Total requests rejected due to missing or invalid auth token.",
			},
		),
		rateLimitRejects: prometheus.NewCounter(
			prometheus.CounterOpts{
				Name: "proxy_rate_limit_rejections_total",
				Help: "Total requests rejected due to rate limits.",
			},
		),
		upstreamErrors: prometheus.NewCounter(
			prometheus.CounterOpts{
				Name: "proxy_upstream_errors_total",
				Help: "Total errors returned by reverse proxy upstream handling.",
			},
		),
	}

	registry.MustRegister(
		metrics.requestsTotal,
		metrics.requestDuration,
		metrics.authRejectsTotal,
		metrics.rateLimitRejects,
		metrics.upstreamErrors,
	)
	return metrics
}

func (m *Metrics) Handler() http.Handler {
	return promhttp.HandlerFor(m.registry, promhttp.HandlerOpts{})
}

func (m *Metrics) ObserveRequest(method, path string, statusCode int, elapsed time.Duration) {
	if m == nil {
		return
	}
	pathLabel := normalizePathLabel(path)
	codeLabel := strconv.Itoa(statusCode)
	m.requestsTotal.WithLabelValues(method, pathLabel, codeLabel).Inc()
	m.requestDuration.WithLabelValues(method, pathLabel).Observe(elapsed.Seconds())
}

func (m *Metrics) IncAuthRejection() {
	if m == nil {
		return
	}
	m.authRejectsTotal.Inc()
}

func (m *Metrics) IncRateLimitRejection() {
	if m == nil {
		return
	}
	m.rateLimitRejects.Inc()
}

func (m *Metrics) IncUpstreamError() {
	if m == nil {
		return
	}
	m.upstreamErrors.Inc()
}

func normalizePathLabel(path string) string {
	switch path {
	case "/healthz", "/readyz", "/metrics":
		return path
	default:
		return "/"
	}
}
