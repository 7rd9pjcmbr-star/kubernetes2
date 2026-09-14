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

package telegram

import (
	"context"
	"fmt"
	"log"
	"time"

	"proxy-production-system/internal/model"
)

func (b *Bot) runAlertMonitor(ctx context.Context) {
	ticker := time.NewTicker(b.cfg.AlertEvery)
	defer ticker.Stop()

	lastStatus := make(map[string]string)
	for {
		b.checkBackendAlerts(ctx, lastStatus)
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (b *Bot) checkBackendAlerts(ctx context.Context, lastStatus map[string]string) {
	backends, err := b.backends.List(ctx)
	if err != nil {
		log.Printf("telegram monitor list backends failed: %v", err)
		return
	}

	for _, backend := range backends {
		key := backend.NodeKey()
		previous, seen := lastStatus[key]
		lastStatus[key] = backend.Status

		if !seen {
			continue
		}
		if previous == backend.Status {
			continue
		}
		if backend.Status != model.BackendStatusDead {
			continue
		}

		text := fmt.Sprintf(
			"*Canh bao @TondaithanhBot*\nBackend `%s` chuyen sang *dead*\n%s:%d | %s | latency %dms | success %.1f%%",
			shortID(backend.ID),
			backend.IP,
			backend.Port,
			backend.Type,
			backend.Latency,
			backend.SuccessRate,
		)
		b.broadcast(ctx, text)
	}
}
