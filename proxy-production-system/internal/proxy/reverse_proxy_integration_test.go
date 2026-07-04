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
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"proxy-production-system/internal/buildinfo"
	"testing"
)

func TestRoundRobinHandlerDistributesRequestsAcrossUpstreams(t *testing.T) {
	upstreamA := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("upstream-a"))
	}))
	defer upstreamA.Close()

	upstreamB := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("upstream-b"))
	}))
	defer upstreamB.Close()

	handler, err := NewRoundRobinHandler(
		[]string{upstreamA.URL, upstreamB.URL},
		MiddlewareOptions{Metrics: NewMetrics()},
	)
	if err != nil {
		t.Fatalf("failed to build handler: %v", err)
	}

	got := make([]string, 0, 4)
	for i := 0; i < 4; i++ {
		req := httptest.NewRequest(http.MethodGet, "/api", nil)
		req.RemoteAddr = "10.0.0.10:12345"
		resp := httptest.NewRecorder()
		handler.ServeHTTP(resp, req)
		if resp.Code != http.StatusOK {
			t.Fatalf("unexpected status code at request %d: got=%d want=%d", i, resp.Code, http.StatusOK)
		}
		got = append(got, resp.Body.String())
	}

	want := []string{"upstream-a", "upstream-b", "upstream-a", "upstream-b"}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("unexpected upstream at index %d: got=%q want=%q", i, got[i], want[i])
		}
	}
}

func TestRoundRobinHandlerRequiresAuthTokenWhenEnabled(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("ok"))
	}))
	defer upstream.Close()

	handler, err := NewRoundRobinHandler(
		[]string{upstream.URL},
		MiddlewareOptions{
			AuthToken: "secret-token",
			Metrics:   NewMetrics(),
		},
	)
	if err != nil {
		t.Fatalf("failed to build handler: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet, "/api", nil)
	req.RemoteAddr = "10.0.0.20:22334"
	resp := httptest.NewRecorder()
	handler.ServeHTTP(resp, req)

	if resp.Code != http.StatusUnauthorized {
		t.Fatalf("unexpected status code: got=%d want=%d", resp.Code, http.StatusUnauthorized)
	}
}

func TestRoundRobinHandlerExposesMetricsEndpoint(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("ok"))
	}))
	defer upstream.Close()

	handler, err := NewRoundRobinHandler(
		[]string{upstream.URL},
		MiddlewareOptions{
			AuthToken: "secret-token",
			Metrics:   NewMetrics(),
		},
	)
	if err != nil {
		t.Fatalf("failed to build handler: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	resp := httptest.NewRecorder()
	handler.ServeHTTP(resp, req)
	if resp.Code != http.StatusOK {
		t.Fatalf("unexpected status code: got=%d want=%d", resp.Code, http.StatusOK)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("failed to read metrics body: %v", err)
	}
	if len(body) == 0 {
		t.Fatalf("expected non-empty metrics body")
	}
}

func TestRoundRobinHandlerSetsSecurityHeaders(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("ok"))
	}))
	defer upstream.Close()

	handler, err := NewRoundRobinHandler(
		[]string{upstream.URL},
		MiddlewareOptions{Metrics: NewMetrics()},
	)
	if err != nil {
		t.Fatalf("failed to build handler: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet, "/api", nil)
	resp := httptest.NewRecorder()
	handler.ServeHTTP(resp, req)

	for key, expected := range map[string]string{
		"X-Content-Type-Options":            "nosniff",
		"X-Frame-Options":                   "DENY",
		"Referrer-Policy":                   "no-referrer",
		"X-Permitted-Cross-Domain-Policies": "none",
	} {
		if got := resp.Header().Get(key); got != expected {
			t.Fatalf("unexpected header %s: got=%q want=%q", key, got, expected)
		}
	}
}

func TestRoundRobinHandlerVersionEndpointIncludesBuildInfo(t *testing.T) {
	original := buildinfo.Get()
	buildinfo.Version = "v9.9.9"
	buildinfo.Commit = "abc1234"
	buildinfo.BuildDate = "2026-07-04T00:00:00Z"
	defer func() {
		buildinfo.Version = original.Version
		buildinfo.Commit = original.Commit
		buildinfo.BuildDate = original.BuildDate
	}()

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("ok"))
	}))
	defer upstream.Close()

	handler, err := NewRoundRobinHandler(
		[]string{upstream.URL},
		MiddlewareOptions{Metrics: NewMetrics()},
	)
	if err != nil {
		t.Fatalf("failed to build handler: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet, "/version", nil)
	resp := httptest.NewRecorder()
	handler.ServeHTTP(resp, req)

	if resp.Code != http.StatusOK {
		t.Fatalf("unexpected status code: got=%d want=%d", resp.Code, http.StatusOK)
	}
	var info buildinfo.Info
	if err := json.NewDecoder(resp.Body).Decode(&info); err != nil {
		t.Fatalf("failed to decode version response: %v", err)
	}
	if info.Version != "v9.9.9" || info.Commit != "abc1234" {
		t.Fatalf("unexpected version payload: %#v", info)
	}
}
