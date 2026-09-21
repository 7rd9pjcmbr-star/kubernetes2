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
	"context"
	"log"
	"time"

	"proxy-production-system/internal/model"
	"proxy-production-system/internal/store"
)

// BackendSyncService keeps the runtime pool aligned with persistent storage.
type BackendSyncService struct {
	repo          store.BackendRepository
	manager       *PoolManager
	syncEvery     time.Duration
	metricsEvery  time.Duration
}

func NewBackendSyncService(repo store.BackendRepository, manager *PoolManager, syncEvery, metricsEvery time.Duration) *BackendSyncService {
	if syncEvery <= 0 {
		syncEvery = 10 * time.Second
	}
	if metricsEvery <= 0 {
		metricsEvery = 30 * time.Second
	}
	return &BackendSyncService{
		repo:         repo,
		manager:      manager,
		syncEvery:    syncEvery,
		metricsEvery: metricsEvery,
	}
}

func (s *BackendSyncService) InitialLoad(ctx context.Context, bootstrapEntries, bootstrapFiles []string) error {
	fileEntries, err := LoadPoolEntriesFromFiles(bootstrapFiles)
	if err != nil {
		return err
	}
	allBootstrap := append(append([]string{}, bootstrapEntries...), fileEntries...)

	backends, err := s.repo.List(ctx)
	if err != nil {
		return err
	}
	if len(backends) == 0 && len(allBootstrap) > 0 {
		if err := s.seedFromEntries(ctx, allBootstrap); err != nil {
			return err
		}
		backends, err = s.repo.List(ctx)
		if err != nil {
			return err
		}
	}
	if len(backends) == 0 {
		return nil
	}
	return s.manager.Reload(backends)
}

func (s *BackendSyncService) seedFromEntries(ctx context.Context, entries []string) error {
	for _, entry := range entries {
		node, err := parsePoolEntry(entry)
		if err != nil {
			return err
		}
		backend := node.BackendSnapshot()
		if err := s.repo.Create(ctx, &backend); err != nil {
			return err
		}
	}
	return nil
}

func (s *BackendSyncService) ReloadNow(ctx context.Context) error {
	backends, err := s.repo.List(ctx)
	if err != nil {
		return err
	}
	if len(backends) == 0 {
		return nil
	}
	return s.manager.Reload(backends)
}

func (s *BackendSyncService) Run(ctx context.Context) {
	syncTicker := time.NewTicker(s.syncEvery)
	metricsTicker := time.NewTicker(s.metricsEvery)
	defer syncTicker.Stop()
	defer metricsTicker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-syncTicker.C:
			if err := s.ReloadNow(ctx); err != nil {
				log.Printf("backend sync reload failed: %v", err)
			}
		case <-metricsTicker.C:
			if err := s.flushMetrics(ctx); err != nil {
				log.Printf("backend metrics flush failed: %v", err)
			}
		}
	}
}

func (s *BackendSyncService) flushMetrics(ctx context.Context) error {
	for _, node := range s.manager.AllNodes() {
		backend := node.BackendSnapshot()
		if backend.ID == "" {
			continue
		}
		if err := s.repo.SaveMetrics(ctx, backend); err != nil {
			log.Printf("save metrics backend=%s err=%v", backend.ID, err)
		}
	}
	return nil
}

func (s *BackendSyncService) Repository() store.BackendRepository {
	return s.repo
}

func filterActiveBackends(backends []model.ProxyBackend) []model.ProxyBackend {
	out := make([]model.ProxyBackend, 0, len(backends))
	for _, backend := range backends {
		if backend.Status != model.BackendStatusDead {
			out = append(out, backend)
		}
	}
	return out
}
