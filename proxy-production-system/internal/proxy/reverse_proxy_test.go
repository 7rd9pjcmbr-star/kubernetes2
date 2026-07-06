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
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRoundRobinHandlerServesV2AndV3StaticSites(t *testing.T) {
	t.Helper()

	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("proxied-response"))
	}))
	defer upstream.Close()

	staticRoot := t.TempDir()
	writeStaticFile(t, filepath.Join(staticRoot, "website", "index.html"), "<h1>v2-page</h1>")
	writeStaticFile(t, filepath.Join(staticRoot, "website-v3", "index.html"), "<h1>v3-page</h1>")

	handler, err := NewRoundRobinHandler([]string{upstream.URL}, staticRoot)
	if err != nil {
		t.Fatalf("NewRoundRobinHandler returned error: %v", err)
	}

	server := httptest.NewServer(handler)
	defer server.Close()

	assertBodyContains(t, server.URL+"/v2/", "v2-page")
	assertBodyContains(t, server.URL+"/v3/", "v3-page")
	assertBodyContains(t, server.URL+"/", "proxied-response")
}

func TestRoundRobinHandlerReturnsErrorWhenStaticSiteMissing(t *testing.T) {
	t.Helper()

	_, err := NewRoundRobinHandler([]string{"http://127.0.0.1:18080"}, t.TempDir())
	if err == nil {
		t.Fatalf("expected static site validation error, got nil")
	}
	if !strings.Contains(err.Error(), "static site") {
		t.Fatalf("expected static site error details, got: %v", err)
	}
}

func writeStaticFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("failed to create test directory: %v", err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("failed to write test file %q: %v", path, err)
	}
}

func assertBodyContains(t *testing.T, url, expected string) {
	t.Helper()

	resp, err := http.Get(url)
	if err != nil {
		t.Fatalf("GET %s failed: %v", url, err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("failed to read response body for %s: %v", url, err)
	}
	if !strings.Contains(string(body), expected) {
		t.Fatalf("unexpected response body for %s: got=%q expected substring=%q", url, string(body), expected)
	}
}
