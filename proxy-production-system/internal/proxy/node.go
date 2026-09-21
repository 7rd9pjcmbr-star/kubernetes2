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
	"net/url"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"proxy-production-system/internal/model"
)

// NodeKind labels upstream quality tier for VN automation workloads.
type NodeKind string

const (
	NodeKindResidential NodeKind = "residential"
	NodeKindMobile4G    NodeKind = "4g"
	NodeKindISP         NodeKind = "isp"
	NodeKindDatacenter  NodeKind = "datacenter"
)

// Node is one upstream exit IP exposed through the gateway.
type Node struct {
	URL                 *url.URL
	mu                  sync.RWMutex
	backend             model.ProxyBackend
	consecutiveFailures atomic.Uint64
}

func newNodeFromBackend(backend model.ProxyBackend) (*Node, error) {
	now := time.Now()
	backend.Normalize(now)

	rawURL := backend.UpstreamURL()
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return nil, fmt.Errorf("parse upstream %q: %w", rawURL, err)
	}
	if parsed.Scheme == "" || parsed.Host == "" {
		return nil, fmt.Errorf("upstream %q must include scheme and host", rawURL)
	}

	return &Node{
		URL:     parsed,
		backend: backend,
	}, nil
}

func newNode(rawURL, kind, region string) (*Node, error) {
	parsed, err := url.Parse(strings.TrimSpace(rawURL))
	if err != nil {
		return nil, fmt.Errorf("parse upstream %q: %w", rawURL, err)
	}
	if parsed.Scheme == "" || parsed.Host == "" {
		return nil, fmt.Errorf("upstream %q must include scheme and host", rawURL)
	}

	host, portStr, splitErr := splitHostPort(parsed.Host)
	if splitErr != nil {
		return nil, splitErr
	}
	port := 0
	if _, err := fmt.Sscanf(portStr, "%d", &port); err != nil {
		return nil, fmt.Errorf("parse port from %q: %w", parsed.Host, err)
	}

	backend := model.ProxyBackend{
		ID:     parsed.Host,
		IP:     host,
		Port:   port,
		Type:   parsed.Scheme,
		Country: strings.TrimSpace(region),
	}
	if kind != "" {
		backend.Type = strings.ToLower(strings.TrimSpace(kind))
	}
	return newNodeFromBackend(backend)
}

func splitHostPort(hostport string) (host, port string, err error) {
	if strings.HasPrefix(hostport, "[") {
		end := strings.Index(hostport, "]")
		if end < 0 {
			return "", "", fmt.Errorf("invalid hostport %q", hostport)
		}
		host = hostport[1:end]
		rest := hostport[end+1:]
		if rest == "" {
			return host, "80", nil
		}
		if !strings.HasPrefix(rest, ":") {
			return "", "", fmt.Errorf("invalid hostport %q", hostport)
		}
		return host, rest[1:], nil
	}

	parts := strings.Split(hostport, ":")
	if len(parts) == 1 {
		return parts[0], "80", nil
	}
	return strings.Join(parts[:len(parts)-1], ":"), parts[len(parts)-1], nil
}

func (n *Node) ID() string {
	n.mu.RLock()
	defer n.mu.RUnlock()
	return n.backend.NodeKey()
}

func (n *Node) Healthy() bool {
	n.mu.RLock()
	defer n.mu.RUnlock()
	if n.backend.Status == model.BackendStatusDead {
		return false
	}
	return n.consecutiveFailures.Load() < 3
}

func (n *Node) MarkSuccess() {
	n.consecutiveFailures.Store(0)
	n.recordOutcome(true)
}

func (n *Node) MarkFailure() {
	n.consecutiveFailures.Add(1)
	n.recordOutcome(false)
}

func (n *Node) recordOutcome(success bool) {
	n.mu.Lock()
	defer n.mu.Unlock()
	n.backend.RecordRequest(success, time.Now())
}

func (n *Node) SetProbeResult(success bool, latencyMS int, checkedAt time.Time) {
	n.mu.Lock()
	defer n.mu.Unlock()
	n.backend.Latency = latencyMS
	n.backend.LastChecked = checkedAt
	if success {
		n.consecutiveFailures.Store(0)
		if n.backend.Status == model.BackendStatusDead && n.backend.SuccessRate >= 50 {
			n.backend.Status = model.BackendStatusTesting
		}
	} else {
		n.backend.Status = model.BackendStatusTesting
	}
}

func (n *Node) BackendSnapshot() model.ProxyBackend {
	n.mu.RLock()
	defer n.mu.RUnlock()
	return n.backend
}

func (n *Node) Stats() NodeStats {
	backend := n.BackendSnapshot()
	return NodeStats{
		ID:            backend.NodeKey(),
		Kind:          backend.Type,
		Region:        backend.Country,
		Anonymity:     backend.Anonymity,
		Status:        backend.Status,
		Latency:       backend.Latency,
		SuccessRate:   backend.SuccessRate,
		TotalRequests: backend.TotalRequests,
		QualityScore:  backend.QualityScore(),
		Healthy:       n.Healthy(),
		Failures:      n.consecutiveFailures.Load(),
		LastChecked:   backend.LastChecked,
	}
}

// NodeStats is a snapshot for the admin API.
type NodeStats struct {
	ID            string    `json:"id"`
	Kind          string    `json:"kind"`
	Region        string    `json:"region"`
	Anonymity     string    `json:"anonymity"`
	Status        string    `json:"status"`
	Latency       int       `json:"latency"`
	SuccessRate   float64   `json:"success_rate"`
	TotalRequests int64     `json:"total_requests"`
	QualityScore  float64   `json:"quality_score"`
	Healthy       bool      `json:"healthy"`
	Failures      uint64    `json:"failures"`
	LastChecked   time.Time `json:"last_checked"`
}
