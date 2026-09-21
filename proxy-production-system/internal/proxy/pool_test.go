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

import "testing"

func TestUpstreamPoolCyclesInOrder(t *testing.T) {
	pool := newUpstreamPool([]string{"a", "b", "c"})
	got := []string{
		pool.next(),
		pool.next(),
		pool.next(),
		pool.next(),
		pool.next(),
	}
	want := []string{"a", "b", "c", "a", "b"}

	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("unexpected upstream at index %d: got=%q want=%q", i, got[i], want[i])
		}
	}
}
