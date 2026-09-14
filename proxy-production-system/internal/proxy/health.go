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
	Pool     *GatewayPool
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
		if err := probeNode(node); err != nil {
			node.MarkFailure()
			log.Printf("health probe failed node=%s err=%v", node.ID, err)
			continue
		}
		node.MarkSuccess()
	}
}

func probeNode(node *Node) error {
	conn, err := net.DialTimeout("tcp", node.URL.Host, 5*time.Second)
	if err != nil {
		return err
	}
	return conn.Close()
}
