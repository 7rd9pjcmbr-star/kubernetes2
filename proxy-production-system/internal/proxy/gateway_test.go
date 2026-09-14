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
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
)

func TestGatewayPoolStickySessionKeepsSameNode(t *testing.T) {
	t.Helper()

	pool, err := NewGatewayPool([]string{
		"http://127.0.0.1:18001|4g|VN-HCM",
		"http://127.0.0.1:18002|residential|VN-HN",
	}, RotationSticky, 0)
	if err != nil {
		t.Fatalf("NewGatewayPool returned error: %v", err)
	}

	first, err := pool.Select("shop-a")
	if err != nil {
		t.Fatalf("first Select failed: %v", err)
	}
	second, err := pool.Select("shop-a")
	if err != nil {
		t.Fatalf("second Select failed: %v", err)
	}
	if first.ID() != second.ID() {
		t.Fatalf("sticky session changed node: first=%q second=%q", first.ID(), second.ID())
	}
}

func TestExtractSessionIDFromUsername(t *testing.T) {
	t.Helper()

	if got := ExtractSessionID("customer-session-shop123"); got != "shop123" {
		t.Fatalf("unexpected session id: got=%q", got)
	}
	if got := ExtractSessionID("customer"); got != "" {
		t.Fatalf("expected empty session id, got=%q", got)
	}
}

func TestForwardHTTPProxyEliteModeStripsHeaders(t *testing.T) {
	t.Helper()

	var seenUserAgent string
	var seenForwardedFor string
	var seenVia string
	target := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seenUserAgent = r.Header.Get("User-Agent")
		seenForwardedFor = r.Header.Get("X-Forwarded-For")
		seenVia = r.Header.Get("Via")
		_, _ = w.Write([]byte("ok"))
	}))
	defer target.Close()

	pool, err := NewGatewayPool([]string{target.URL + "|isp|VN"}, RotationRoundRobin, 0)
	if err != nil {
		t.Fatalf("NewGatewayPool returned error: %v", err)
	}

	proxyHandler := &ForwardHTTPProxy{Pool: pool, Auth: GatewayAuth{}, EliteMode: true}
	server := httptest.NewServer(proxyHandler)
	defer server.Close()

	client := &http.Client{
		Transport: &http.Transport{Proxy: http.ProxyURL(mustParseURL(t, server.URL))},
	}
	req, err := http.NewRequest(http.MethodGet, target.URL+"/probe", nil)
	if err != nil {
		t.Fatalf("NewRequest failed: %v", err)
	}
	req.Header.Set("X-Forwarded-For", "203.0.113.9")
	req.Header.Set("Via", "1.1 bad-proxy")
	req.Header.Set("User-Agent", "Mozilla/5.0 EliteTest")
	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	resp.Body.Close()

	if seenForwardedFor != "" {
		t.Fatalf("X-Forwarded-For leaked to upstream: %q", seenForwardedFor)
	}
	if seenVia != "" {
		t.Fatalf("Via leaked to upstream: %q", seenVia)
	}
	if seenUserAgent != "Mozilla/5.0 EliteTest" {
		t.Fatalf("custom User-Agent should survive elite filter: got=%q", seenUserAgent)
	}
}

func TestForwardHTTPProxyRequiresAuthWhenConfigured(t *testing.T) {
	t.Helper()

	target := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("upstream-ok"))
	}))
	defer target.Close()

	pool, err := NewGatewayPool([]string{target.URL + "|isp|VN"}, RotationRoundRobin, 0)
	if err != nil {
		t.Fatalf("NewGatewayPool returned error: %v", err)
	}

	proxyHandler := &ForwardHTTPProxy{
		Pool: pool,
		Auth: NewGatewayAuth("player", "secret", nil),
	}
	server := httptest.NewServer(proxyHandler)
	defer server.Close()

	client := &http.Client{
		Transport: &http.Transport{
			Proxy: http.ProxyURL(mustParseURL(t, server.URL)),
		},
	}

	resp, err := client.Get("http://example.com/")
	if err != nil {
		if !strings.Contains(err.Error(), "407") {
			t.Fatalf("expected proxy auth failure, got: %v", err)
		}
	} else {
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusProxyAuthRequired {
			t.Fatalf("expected 407, got status=%d", resp.StatusCode)
		}
	}

	req, err := http.NewRequest(http.MethodGet, "http://example.com/", nil)
	if err != nil {
		t.Fatalf("failed to create request: %v", err)
	}
	req.SetBasicAuth("player", "secret")
	resp, err = client.Do(req)
	if err != nil {
		t.Fatalf("authenticated request failed: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		t.Fatalf("unexpected status=%d body=%q", resp.StatusCode, string(body))
	}
}

func mustParseURL(t *testing.T, raw string) *url.URL {
	t.Helper()
	parsed, err := url.Parse(raw)
	if err != nil {
		t.Fatalf("parse url %q: %v", raw, err)
	}
	return parsed
}
