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

package store

import (
	"context"
	"fmt"
	"sync"
	"time"

	"proxy-production-system/internal/model"
)

// MemoryRepository is an in-process backend store for tests and local bootstrap.
type MemoryRepository struct {
	mu       sync.RWMutex
	backends map[string]model.ProxyBackend
}

func NewMemoryRepository(seed []model.ProxyBackend) *MemoryRepository {
	repo := &MemoryRepository{backends: make(map[string]model.ProxyBackend)}
	now := time.Now()
	for i := range seed {
		backend := seed[i]
		backend.Normalize(now)
		if backend.ID == "" {
			backend.ID = fmt.Sprintf("mem-%d", i+1)
		}
		repo.backends[backend.ID] = backend
	}
	return repo
}

func (r *MemoryRepository) List(_ context.Context) ([]model.ProxyBackend, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	out := make([]model.ProxyBackend, 0, len(r.backends))
	for _, backend := range r.backends {
		out = append(out, backend)
	}
	return out, nil
}

func (r *MemoryRepository) Get(_ context.Context, id string) (model.ProxyBackend, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	backend, ok := r.backends[id]
	if !ok {
		return model.ProxyBackend{}, ErrNotFound
	}
	return backend, nil
}

func (r *MemoryRepository) Create(_ context.Context, backend *model.ProxyBackend) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	backend.Normalize(time.Now())
	if backend.ID == "" {
		backend.ID = fmt.Sprintf("mem-%d", len(r.backends)+1)
	}
	if _, exists := r.backends[backend.ID]; exists {
		return fmt.Errorf("backend %q already exists", backend.ID)
	}
	r.backends[backend.ID] = *backend
	return nil
}

func (r *MemoryRepository) Update(_ context.Context, backend model.ProxyBackend) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if _, ok := r.backends[backend.ID]; !ok {
		return ErrNotFound
	}
	backend.Normalize(time.Now())
	r.backends[backend.ID] = backend
	return nil
}

func (r *MemoryRepository) Delete(_ context.Context, id string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if _, ok := r.backends[id]; !ok {
		return ErrNotFound
	}
	delete(r.backends, id)
	return nil
}

func (r *MemoryRepository) SaveMetrics(_ context.Context, backend model.ProxyBackend) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	current, ok := r.backends[backend.ID]
	if !ok {
		return ErrNotFound
	}
	current.Latency = backend.Latency
	current.SuccessRate = backend.SuccessRate
	current.TotalRequests = backend.TotalRequests
	current.Status = backend.Status
	current.LastChecked = backend.LastChecked
	r.backends[backend.ID] = current
	return nil
}
