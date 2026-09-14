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
	"fmt"
	"sync"
	"time"

	"proxy-production-system/internal/model"
)

// PoolSelector is the runtime surface used by HTTP/SOCKS5 handlers and health checks.
type PoolSelector interface {
	Select(sessionID string) (*Node, error)
	Stats() PoolStats
	AllNodes() []*Node
}

// PoolManager hot-swaps gateway pools while preserving in-flight node telemetry.
type PoolManager struct {
	mu        sync.RWMutex
	pool      *GatewayPool
	rotation  RotationMode
	stickyTTL time.Duration
}

func NewPoolManager(rotation RotationMode, stickyTTL time.Duration) *PoolManager {
	return &PoolManager{
		rotation:  rotation,
		stickyTTL: stickyTTL,
	}
}

func (m *PoolManager) Reload(backends []model.ProxyBackend) error {
	if len(backends) == 0 {
		return fmt.Errorf("cannot reload empty backend set")
	}

	nextPool, err := NewGatewayPoolFromBackends(backends, m.rotation, m.stickyTTL)
	if err != nil {
		return err
	}

	m.mu.Lock()
	defer m.mu.Unlock()
	if m.pool != nil {
		mergeRuntimeState(m.pool, nextPool)
	}
	m.pool = nextPool
	return nil
}

func mergeRuntimeState(oldPool, newPool *GatewayPool) {
	oldByID := make(map[string]*Node, len(oldPool.AllNodes()))
	for _, node := range oldPool.AllNodes() {
		oldByID[node.ID()] = node
	}
	for _, node := range newPool.AllNodes() {
		oldNode, ok := oldByID[node.ID()]
		if !ok {
			continue
		}
		snapshot := oldNode.BackendSnapshot()
		node.mu.Lock()
		node.backend.Latency = snapshot.Latency
		node.backend.SuccessRate = snapshot.SuccessRate
		node.backend.TotalRequests = snapshot.TotalRequests
		node.backend.Status = snapshot.Status
		node.backend.LastChecked = snapshot.LastChecked
		node.mu.Unlock()
		node.consecutiveFailures.Store(oldNode.consecutiveFailures.Load())
	}
}

func (m *PoolManager) current() *GatewayPool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.pool
}

func (m *PoolManager) Select(sessionID string) (*Node, error) {
	pool := m.current()
	if pool == nil {
		return nil, fmt.Errorf("gateway pool is not initialized")
	}
	return pool.Select(sessionID)
}

func (m *PoolManager) Stats() PoolStats {
	pool := m.current()
	if pool == nil {
		return PoolStats{}
	}
	return pool.Stats()
}

func (m *PoolManager) AllNodes() []*Node {
	pool := m.current()
	if pool == nil {
		return nil
	}
	return pool.AllNodes()
}
