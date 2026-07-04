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
	"net/http"
	"net/http/httputil"
	"net/url"

	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
)

func NewRoundRobinHandler(upstreams []string, options MiddlewareOptions) (http.Handler, error) {
	if len(upstreams) == 0 {
		return nil, fmt.Errorf("at least one upstream is required")
	}

	pool := newUpstreamPool(upstreams)
	reverseProxy := &httputil.ReverseProxy{
		Director: func(req *http.Request) {
			target, err := url.Parse(pool.next())
			if err != nil {
				// Keep the request local and return a clear error via ModifyResponse.
				req.URL.Scheme = "http"
				req.URL.Host = "127.0.0.1"
				req.Host = "127.0.0.1"
				return
			}

			req.URL.Scheme = target.Scheme
			req.URL.Host = target.Host
			req.Host = target.Host
			otel.GetTextMapPropagator().Inject(req.Context(), propagation.HeaderCarrier(req.Header))
		},
		Transport: otelhttp.NewTransport(http.DefaultTransport),
		ErrorHandler: func(w http.ResponseWriter, req *http.Request, err error) {
			if options.Metrics != nil {
				options.Metrics.IncUpstreamError()
			}
			slog.Error("proxy upstream error",
				"method", req.Method,
				"path", req.URL.Path,
				"error", err,
			)
			http.Error(w, "upstream unavailable", http.StatusBadGateway)
		},
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ready"}`))
	})
	if options.Metrics != nil {
		mux.Handle("/metrics", options.Metrics.Handler())
	}
	mux.Handle("/", reverseProxy)

	handler := withRateLimit(options, mux)
	handler = withAuth(options.AuthToken, options.Metrics, handler)
	handler = withRequestTimeout(options.RequestTimeout, handler)
	handler = withRequestLogging(handler, options.TrustForwarded, options.Metrics)
	return handler, nil
}
