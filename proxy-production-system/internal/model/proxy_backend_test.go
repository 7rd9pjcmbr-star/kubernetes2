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

package model

import (
	"testing"
	"time"
)

func TestProxyBackendUpstreamURL(t *testing.T) {
	t.Helper()

	backend := ProxyBackend{IP: "203.0.113.10", Port: 3128, Type: BackendTypeSocks5}
	if got := backend.UpstreamURL(); got != "socks5://203.0.113.10:3128" {
		t.Fatalf("unexpected upstream url: got=%q", got)
	}
}

func TestQualityScorePrefersEliteLowLatency(t *testing.T) {
	t.Helper()

	elite := ProxyBackend{
		Status:      BackendStatusActive,
		Anonymity:   AnonymityElite,
		Latency:     40,
		SuccessRate: 99,
	}
	slow := ProxyBackend{
		Status:      BackendStatusActive,
		Anonymity:   AnonymityAnonymous,
		Latency:     400,
		SuccessRate: 99,
	}
	if elite.QualityScore() <= slow.QualityScore() {
		t.Fatalf("elite node should outrank slower anonymous node: elite=%f slow=%f",
			elite.QualityScore(), slow.QualityScore())
	}
}

func TestRecordRequestMarksDeadOnLowSuccessRate(t *testing.T) {
	t.Helper()

	backend := ProxyBackend{Status: BackendStatusActive, SuccessRate: 100}
	now := time.Now()
	for i := 0; i < 10; i++ {
		backend.RecordRequest(false, now)
	}
	if backend.Status != BackendStatusDead {
		t.Fatalf("expected dead status after repeated failures, got %q", backend.Status)
	}
}
