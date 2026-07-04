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
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"strings"
	"sync/atomic"
	"time"

	"go.opentelemetry.io/otel/trace"
)

type MiddlewareOptions struct {
	AuthToken      string
	RateLimitRPS   int
	RateLimitBurst int
	TrustForwarded bool
	RequestTimeout time.Duration
	Metrics        *Metrics
}

var requestSequence uint64

func withRequestLogging(next http.Handler, trustForwarded bool, metrics *Metrics) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		start := time.Now()
		requestID := nextRequestID()
		clientIP := sourceIP(req, trustForwarded)

		rw := &statusRecorder{ResponseWriter: w, statusCode: http.StatusOK}
		rw.Header().Set("X-Request-Id", requestID)
		next.ServeHTTP(rw, req)
		elapsed := time.Since(start)
		metrics.ObserveRequest(req.Method, req.URL.Path, rw.statusCode, elapsed)
		traceID := traceIDFromContext(req)

		slog.Info("http request completed",
			"request_id", requestID,
			"trace_id", traceID,
			"client_ip", clientIP,
			"method", req.Method,
			"path", req.URL.Path,
			"status", rw.statusCode,
			"duration_ms", elapsed.Milliseconds(),
		)
	})
}

func withAuth(token string, metrics *Metrics, next http.Handler) http.Handler {
	trimmed := strings.TrimSpace(token)
	if trimmed == "" {
		return next
	}

	return http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		if isProbePath(req.URL.Path) {
			next.ServeHTTP(w, req)
			return
		}
		provided := strings.TrimSpace(req.Header.Get("X-Proxy-Token"))
		if provided == "" {
			if metrics != nil {
				metrics.IncAuthRejection()
			}
			http.Error(w, "missing X-Proxy-Token header", http.StatusUnauthorized)
			return
		}
		if provided != trimmed {
			if metrics != nil {
				metrics.IncAuthRejection()
			}
			http.Error(w, "invalid X-Proxy-Token value", http.StatusUnauthorized)
			return
		}
		next.ServeHTTP(w, req)
	})
}

func withRateLimit(opts MiddlewareOptions, next http.Handler) http.Handler {
	if opts.RateLimitRPS <= 0 || opts.RateLimitBurst <= 0 {
		return next
	}
	limiter := newRateLimiterStore(opts.RateLimitRPS, opts.RateLimitBurst)
	return http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		if isProbePath(req.URL.Path) {
			next.ServeHTTP(w, req)
			return
		}

		clientIP := sourceIP(req, opts.TrustForwarded)
		if !limiter.Allow(clientIP) {
			if opts.Metrics != nil {
				opts.Metrics.IncRateLimitRejection()
			}
			http.Error(w, "rate limit exceeded for client IP", http.StatusTooManyRequests)
			return
		}
		next.ServeHTTP(w, req)
	})
}

func withRequestTimeout(timeout time.Duration, next http.Handler) http.Handler {
	if timeout <= 0 {
		return next
	}
	return http.TimeoutHandler(next, timeout, "request timeout")
}

func withSecurityHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("X-Frame-Options", "DENY")
		w.Header().Set("Referrer-Policy", "no-referrer")
		w.Header().Set("X-Permitted-Cross-Domain-Policies", "none")
		if req.TLS != nil {
			w.Header().Set("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
		}
		next.ServeHTTP(w, req)
	})
}

func isProbePath(path string) bool {
	return path == "/healthz" || path == "/readyz" || path == "/metrics" || path == "/version"
}

func sourceIP(req *http.Request, trustForwarded bool) string {
	if trustForwarded {
		if forwarded := strings.TrimSpace(req.Header.Get("X-Forwarded-For")); forwarded != "" {
			parts := strings.Split(forwarded, ",")
			if len(parts) > 0 && strings.TrimSpace(parts[0]) != "" {
				return strings.TrimSpace(parts[0])
			}
		}
		if realIP := strings.TrimSpace(req.Header.Get("X-Real-Ip")); realIP != "" {
			return realIP
		}
	}

	host, _, err := net.SplitHostPort(req.RemoteAddr)
	if err != nil {
		return req.RemoteAddr
	}
	return host
}

func nextRequestID() string {
	seq := atomic.AddUint64(&requestSequence, 1)
	return fmt.Sprintf("req-%d-%d", time.Now().UnixMilli(), seq)
}

func traceIDFromContext(req *http.Request) string {
	spanContext := trace.SpanFromContext(req.Context()).SpanContext()
	if !spanContext.IsValid() {
		return ""
	}
	return spanContext.TraceID().String()
}

type statusRecorder struct {
	http.ResponseWriter
	statusCode int
}

func (r *statusRecorder) WriteHeader(code int) {
	r.statusCode = code
	r.ResponseWriter.WriteHeader(code)
}
