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
	"sync"

	"proxy-production-system/internal/model"
)

// BackendStore is the persistence seam for MongoDB or other databases later.
type BackendStore interface {
	List() []model.ProxyBackend
	ReplaceAll(backends []model.ProxyBackend)
}

// MemoryBackendStore keeps backends in-process for bootstrap and tests.
type MemoryBackendStore struct {
	mu       sync.RWMutex
	backends []model.ProxyBackend
}

func NewMemoryBackendStore(backends []model.ProxyBackend) *MemoryBackendStore {
	copied := make([]model.ProxyBackend, len(backends))
	copy(copied, backends)
	return &MemoryBackendStore{backends: copied}
}

func (s *MemoryBackendStore) List() []model.ProxyBackend {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make([]model.ProxyBackend, len(s.backends))
	copy(out, s.backends)
	return out
}

func (s *MemoryBackendStore) ReplaceAll(backends []model.ProxyBackend) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.backends = make([]model.ProxyBackend, len(backends))
	copy(s.backends, backends)
}
