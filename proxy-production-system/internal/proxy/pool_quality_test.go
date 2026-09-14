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

	"proxy-production-system/internal/model"
)

func TestGatewayPoolQualityPicksEliteFastNode(t *testing.T) {
	t.Helper()

	pool, err := NewGatewayPool([]string{
		"http://127.0.0.1:18001|4g|VN|anonymous|400|95",
		"http://127.0.0.1:18002|residential|VN|elite|40|99",
	}, RotationQuality, 0)
	if err != nil {
		t.Fatalf("NewGatewayPool returned error: %v", err)
	}

	node, err := pool.Select("")
	if err != nil {
		t.Fatalf("Select failed: %v", err)
	}
	if node.ID() != "127.0.0.1:18002" {
		t.Fatalf("quality router picked wrong node: got=%q", node.ID())
	}
}

func TestNewGatewayPoolFromBackends(t *testing.T) {
	t.Helper()

	pool, err := NewGatewayPoolFromBackends([]model.ProxyBackend{
		{
			ID:          "node-a",
			IP:          "203.0.113.1",
			Port:        3128,
			Type:        model.BackendTypeHTTP,
			Country:     "VN",
			Anonymity:   model.AnonymityElite,
			Status:      model.BackendStatusActive,
			Latency:     35,
			SuccessRate: 98,
		},
	}, RotationRoundRobin, 0)
	if err != nil {
		t.Fatalf("NewGatewayPoolFromBackends returned error: %v", err)
	}
	stats := pool.Stats()
	if stats.Total != 1 {
		t.Fatalf("unexpected pool size: got=%d want=1", stats.Total)
	}
	if stats.Nodes[0].Anonymity != model.AnonymityElite {
		t.Fatalf("unexpected anonymity: got=%q", stats.Nodes[0].Anonymity)
	}
}
