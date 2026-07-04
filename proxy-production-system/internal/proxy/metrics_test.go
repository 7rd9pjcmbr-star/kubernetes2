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
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestMetricsHandlerExposesProxyCounters(t *testing.T) {
	metrics := NewMetrics()
	metrics.ObserveRequest(http.MethodGet, "/healthz", http.StatusOK, 50*time.Millisecond)
	metrics.IncAuthRejection()
	metrics.IncRateLimitRejection()
	metrics.IncUpstreamError()

	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	resp := httptest.NewRecorder()
	metrics.Handler().ServeHTTP(resp, req)

	if resp.Code != http.StatusOK {
		t.Fatalf("unexpected status: got=%d want=%d", resp.Code, http.StatusOK)
	}
	body := resp.Body.String()
	for _, expected := range []string{
		"proxy_requests_total",
		"proxy_request_duration_seconds",
		"proxy_auth_rejections_total",
		"proxy_rate_limit_rejections_total",
		"proxy_upstream_errors_total",
	} {
		if !strings.Contains(body, expected) {
			t.Fatalf("metrics output missing %q", expected)
		}
	}
}
