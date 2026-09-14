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
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"proxy-production-system/internal/model"
	"proxy-production-system/internal/store"
)

func TestAdminBackendCRUDAndHotReload(t *testing.T) {
	t.Helper()

	repo := store.NewMemoryRepository(nil)
	gateway, err := NewGateway(GatewayConfig{
		PoolEntries: []string{
			"http://127.0.0.1:18001|4g|VN|elite|40|99",
		},
		Rotation: RotationQuality,
	}, repo)
	if err != nil {
		t.Fatalf("NewGateway returned error: %v", err)
	}

	server := httptest.NewServer(gateway.AdminHandler())
	defer server.Close()

	createBody, _ := json.Marshal(model.ProxyBackend{
		IP:          "203.0.113.50",
		Port:        3128,
		Type:        model.BackendTypeHTTP,
		Country:     "VN",
		Anonymity:   model.AnonymityElite,
		Status:      model.BackendStatusActive,
		Latency:     20,
		SuccessRate: 99.9,
	})
	createResp, err := http.Post(server.URL+"/api/v1/backends", "application/json", bytes.NewReader(createBody))
	if err != nil {
		t.Fatalf("create backend failed: %v", err)
	}
	createResp.Body.Close()
	if createResp.StatusCode != http.StatusCreated {
		t.Fatalf("unexpected create status: got=%d", createResp.StatusCode)
	}

	listResp, err := http.Get(server.URL + "/api/v1/backends")
	if err != nil {
		t.Fatalf("list backends failed: %v", err)
	}
	defer listResp.Body.Close()

	var backends []model.ProxyBackend
	if err := json.NewDecoder(listResp.Body).Decode(&backends); err != nil {
		t.Fatalf("decode backends failed: %v", err)
	}
	if len(backends) < 2 {
		t.Fatalf("expected at least 2 backends after create, got=%d", len(backends))
	}

	stats := gateway.Manager().Stats()
	if stats.Total < 2 {
		t.Fatalf("pool not hot-reloaded after create: total=%d", stats.Total)
	}
}

func TestGatewayAdminStatsJSON(t *testing.T) {
	t.Helper()

	repo := store.NewMemoryRepository(nil)
	gateway, err := NewGateway(GatewayConfig{
		PoolEntries: []string{
			"http://127.0.0.1:18001|4g|VN-HCM",
			"http://127.0.0.1:18002|residential|VN-HN",
		},
		Rotation: RotationRoundRobin,
	}, repo)
	if err != nil {
		t.Fatalf("NewGateway returned error: %v", err)
	}

	server := httptest.NewServer(gateway.AdminHandler())
	defer server.Close()

	resp, err := http.Get(server.URL + "/api/v1/pool/stats")
	if err != nil {
		t.Fatalf("GET stats failed: %v", err)
	}
	defer resp.Body.Close()

	var stats PoolStats
	if err := json.NewDecoder(resp.Body).Decode(&stats); err != nil {
		t.Fatalf("failed to decode stats: %v", err)
	}
	if stats.Total != 2 {
		t.Fatalf("unexpected total nodes: got=%d want=2", stats.Total)
	}
}
