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
	"testing"
	"time"
)

func TestRateLimiterRefillsTokens(t *testing.T) {
	current := time.Unix(0, 0)
	store := newRateLimiterStore(2, 2)
	store.now = func() time.Time { return current }

	key := "192.168.1.1"
	if !store.Allow(key) {
		t.Fatalf("first request should pass")
	}
	if !store.Allow(key) {
		t.Fatalf("second request should pass")
	}
	if store.Allow(key) {
		t.Fatalf("third request should be blocked before refill")
	}

	current = current.Add(1 * time.Second)
	if !store.Allow(key) {
		t.Fatalf("request should pass after refill")
	}
}
