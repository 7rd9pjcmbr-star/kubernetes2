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
	"log"
	"net"
	"net/http"
	"strings"
	"sync/atomic"
	"time"
)

type MiddlewareOptions struct {
	AuthToken      string
	RateLimitRPS   int
	RateLimitBurst int
	TrustForwarded bool
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

		log.Printf("request_id=%s client_ip=%s method=%s path=%s status=%d duration_ms=%d",
			requestID,
			clientIP,
			req.Method,
			req.URL.Path,
			rw.statusCode,
			elapsed.Milliseconds(),
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
			metrics.IncAuthRejection()
			http.Error(w, "missing X-Proxy-Token header", http.StatusUnauthorized)
			return
		}
		if provided != trimmed {
			metrics.IncAuthRejection()
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
			opts.Metrics.IncRateLimitRejection()
			http.Error(w, "rate limit exceeded for client IP", http.StatusTooManyRequests)
			return
		}
		next.ServeHTTP(w, req)
	})
}

func isProbePath(path string) bool {
	return path == "/healthz" || path == "/readyz" || path == "/metrics"
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

type statusRecorder struct {
	http.ResponseWriter
	statusCode int
}

func (r *statusRecorder) WriteHeader(code int) {
	r.statusCode = code
	r.ResponseWriter.WriteHeader(code)
}
