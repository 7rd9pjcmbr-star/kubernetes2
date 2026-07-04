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
	"testing"
)

func TestWithAuthRejectsMissingToken(t *testing.T) {
	handler := withAuth("secret-token", http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodGet, "/api", nil)
	resp := httptest.NewRecorder()
	handler.ServeHTTP(resp, req)

	if resp.Code != http.StatusUnauthorized {
		t.Fatalf("unexpected status: got=%d want=%d", resp.Code, http.StatusUnauthorized)
	}
}

func TestWithAuthAllowsHealthzWithoutToken(t *testing.T) {
	handler := withAuth("secret-token", http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	resp := httptest.NewRecorder()
	handler.ServeHTTP(resp, req)

	if resp.Code != http.StatusOK {
		t.Fatalf("unexpected status: got=%d want=%d", resp.Code, http.StatusOK)
	}
}

func TestWithAuthAllowsReadyzWithoutToken(t *testing.T) {
	handler := withAuth("secret-token", http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodGet, "/readyz", nil)
	resp := httptest.NewRecorder()
	handler.ServeHTTP(resp, req)

	if resp.Code != http.StatusOK {
		t.Fatalf("unexpected status: got=%d want=%d", resp.Code, http.StatusOK)
	}
}

func TestWithRateLimitRejectsWhenBurstExceeded(t *testing.T) {
	opts := MiddlewareOptions{RateLimitRPS: 1, RateLimitBurst: 1}
	handler := withRateLimit(opts, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	reqOne := httptest.NewRequest(http.MethodGet, "/api", nil)
	reqOne.RemoteAddr = "10.0.0.1:1234"
	respOne := httptest.NewRecorder()
	handler.ServeHTTP(respOne, reqOne)

	if respOne.Code != http.StatusOK {
		t.Fatalf("first request should pass: got=%d want=%d", respOne.Code, http.StatusOK)
	}

	reqTwo := httptest.NewRequest(http.MethodGet, "/api", nil)
	reqTwo.RemoteAddr = "10.0.0.1:1234"
	respTwo := httptest.NewRecorder()
	handler.ServeHTTP(respTwo, reqTwo)

	if respTwo.Code != http.StatusTooManyRequests {
		t.Fatalf("second request should be limited: got=%d want=%d", respTwo.Code, http.StatusTooManyRequests)
	}
}
