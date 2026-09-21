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
	"testing"
)

func TestSanitizeEliteRequestStripsProxyHeaders(t *testing.T) {
	t.Helper()

	req, err := http.NewRequest(http.MethodGet, "http://example.com/", nil)
	if err != nil {
		t.Fatalf("NewRequest failed: %v", err)
	}
	req.Header.Set("X-Forwarded-For", "203.0.113.1")
	req.Header.Set("Via", "1.1 proxy")
	req.Header.Set("Proxy-Connection", "keep-alive")
	req.Header.Set("User-Agent", "custom-agent")

	SanitizeEliteRequest(req)

	for _, header := range eliteStripHeaders {
		if req.Header.Get(header) != "" {
			t.Fatalf("expected header %q removed, got %q", header, req.Header.Get(header))
		}
	}
	if req.Header.Get("User-Agent") != "custom-agent" {
		t.Fatalf("existing User-Agent should be preserved, got %q", req.Header.Get("User-Agent"))
	}
}

func TestSanitizeEliteRequestSetsDefaultUserAgent(t *testing.T) {
	t.Helper()

	req, err := http.NewRequest(http.MethodGet, "http://example.com/", nil)
	if err != nil {
		t.Fatalf("NewRequest failed: %v", err)
	}

	SanitizeEliteRequest(req)

	if req.Header.Get("User-Agent") != defaultEliteUserAgent {
		t.Fatalf("unexpected default User-Agent: got=%q", req.Header.Get("User-Agent"))
	}
}
