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
	"net"
	"time"
)

// HealthChecker periodically probes upstream nodes so dead exits drop out fast.
type HealthChecker struct {
	Pool     PoolSelector
	Interval time.Duration
}

func (h *HealthChecker) Run(ctx context.Context) {
	if h.Interval <= 0 {
		h.Interval = 30 * time.Second
	}
	ticker := time.NewTicker(h.Interval)
	defer ticker.Stop()

	for {
		h.checkAll()
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (h *HealthChecker) checkAll() {
	for _, node := range h.Pool.AllNodes() {
		latencyMS, err := probeNode(node)
		checkedAt := time.Now()
		if err != nil {
			node.SetProbeResult(false, latencyMS, checkedAt)
			log.Printf("health probe failed node=%s err=%v", node.ID(), err)
			continue
		}
		node.SetProbeResult(true, latencyMS, checkedAt)
	}
}

func probeNode(node *Node) (int, error) {
	start := time.Now()
	conn, err := net.DialTimeout("tcp", node.URL.Host, 5*time.Second)
	latencyMS := int(time.Since(start).Milliseconds())
	if err != nil {
		return latencyMS, err
	}
	return latencyMS, conn.Close()
}
