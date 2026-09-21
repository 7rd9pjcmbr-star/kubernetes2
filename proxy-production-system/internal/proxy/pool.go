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
	"crypto/rand"
	"encoding/binary"
	"fmt"
	"strconv"
	"sync"
	"sync/atomic"
	"time"

	"proxy-production-system/internal/model"
)

type upstreamPool struct {
	upstreams []string
	nextIndex uint64
}

func newUpstreamPool(upstreams []string) *upstreamPool {
	copied := make([]string, len(upstreams))
	copy(copied, upstreams)
	return &upstreamPool{upstreams: copied}
}

func (p *upstreamPool) next() string {
	idx := atomic.AddUint64(&p.nextIndex, 1) - 1
	return p.upstreams[idx%uint64(len(p.upstreams))]
}

// GatewayPool manages upstream exit nodes for forward proxy traffic.
type GatewayPool struct {
	nodes        []*Node
	rotation     RotationMode
	stickyTTL    time.Duration
	nextIndex    uint64
	sticky       map[string]stickyEntry
	stickyMu     sync.RWMutex
}

type stickyEntry struct {
	nodeID    string
	expiresAt time.Time
}

// NewGatewayPool builds a pool from CSV entries: url|kind|region[|anonymity|latency|success_rate].
func NewGatewayPool(entries []string, rotation RotationMode, stickyTTL time.Duration) (*GatewayPool, error) {
	if len(entries) == 0 {
		return nil, fmt.Errorf("at least one PROXY_POOL entry is required")
	}
	if stickyTTL <= 0 {
		stickyTTL = 10 * time.Minute
	}

	nodes := make([]*Node, 0, len(entries))
	for _, entry := range entries {
		node, err := parsePoolEntry(entry)
		if err != nil {
			return nil, err
		}
		nodes = append(nodes, node)
	}
	return newGatewayPool(nodes, rotation, stickyTTL), nil
}

// NewGatewayPoolFromBackends builds a pool from Mongo-ready backend records.
func NewGatewayPoolFromBackends(backends []model.ProxyBackend, rotation RotationMode, stickyTTL time.Duration) (*GatewayPool, error) {
	if len(backends) == 0 {
		return nil, fmt.Errorf("at least one backend is required")
	}
	if stickyTTL <= 0 {
		stickyTTL = 10 * time.Minute
	}

	nodes := make([]*Node, 0, len(backends))
	for _, backend := range backends {
		node, err := newNodeFromBackend(backend)
		if err != nil {
			return nil, err
		}
		nodes = append(nodes, node)
	}
	return newGatewayPool(nodes, rotation, stickyTTL), nil
}

func newGatewayPool(nodes []*Node, rotation RotationMode, stickyTTL time.Duration) *GatewayPool {
	return &GatewayPool{
		nodes:     nodes,
		rotation:  rotation,
		stickyTTL: stickyTTL,
		sticky:    make(map[string]stickyEntry),
	}
}

func parsePoolEntry(entry string) (*Node, error) {
	parts := splitPipe(entry)
	if len(parts) == 0 || parts[0] == "" {
		return nil, fmt.Errorf("invalid pool entry %q", entry)
	}

	kind := "residential"
	region := "VN"
	anonymity := model.AnonymityElite
	latency := 0
	successRate := 100.0

	switch len(parts) {
	case 2:
		kind = parts[1]
	case 3:
		kind = parts[1]
		region = parts[2]
	case 4:
		kind = parts[1]
		region = parts[2]
		anonymity = parts[3]
	case 5:
		kind = parts[1]
		region = parts[2]
		anonymity = parts[3]
		if parsed, err := strconv.Atoi(parts[4]); err == nil {
			latency = parsed
		}
	case 6:
		kind = parts[1]
		region = parts[2]
		anonymity = parts[3]
		if parsed, err := strconv.Atoi(parts[4]); err == nil {
			latency = parsed
		}
		if parsed, err := strconv.ParseFloat(parts[5], 64); err == nil {
			successRate = parsed
		}
	}

	node, err := newNode(parts[0], kind, region)
	if err != nil {
		return nil, err
	}

	node.mu.Lock()
	node.backend.Anonymity = anonymity
	node.backend.Latency = latency
	node.backend.SuccessRate = successRate
	node.mu.Unlock()
	return node, nil
}

func splitPipe(value string) []string {
	raw := make([]string, 0, 3)
	for _, part := range splitTrim(value, "|") {
		raw = append(raw, part)
	}
	return raw
}

func splitTrim(value, sep string) []string {
	if value == "" {
		return nil
	}
	parts := make([]string, 0, 4)
	for _, part := range splitBySep(value, sep) {
		trimmed := trimSpace(part)
		if trimmed != "" {
			parts = append(parts, trimmed)
		}
	}
	return parts
}

func splitBySep(value, sep string) []string {
	out := make([]string, 0, 4)
	start := 0
	for i := 0; i <= len(value)-len(sep); i++ {
		if value[i:i+len(sep)] == sep {
			out = append(out, value[start:i])
			start = i + len(sep)
			i += len(sep) - 1
		}
	}
	out = append(out, value[start:])
	return out
}

func trimSpace(value string) string {
	start := 0
	end := len(value)
	for start < end && (value[start] == ' ' || value[start] == '\t') {
		start++
	}
	for end > start && (value[end-1] == ' ' || value[end-1] == '\t') {
		end--
	}
	return value[start:end]
}

// Select returns an upstream node for a client request.
func (p *GatewayPool) Select(sessionID string) (*Node, error) {
	healthy := p.healthyNodes()
	if len(healthy) == 0 {
		return nil, fmt.Errorf("no healthy upstream nodes available")
	}

	switch p.rotation {
	case RotationSticky:
		if sessionID != "" {
			if node := p.stickyNode(sessionID, healthy); node != nil {
				return node, nil
			}
		}
		node := p.pickRoundRobin(healthy)
		if sessionID != "" {
			p.rememberSticky(sessionID, node)
		}
		return node, nil
	case RotationRandom:
		return p.pickRandom(healthy), nil
	case RotationQuality:
		return p.pickBestQuality(healthy), nil
	default:
		return p.pickRoundRobin(healthy), nil
	}
}

func (p *GatewayPool) pickBestQuality(nodes []*Node) *Node {
	best := nodes[0]
	bestScore := best.BackendSnapshot().QualityScore()
	for _, node := range nodes[1:] {
		score := node.BackendSnapshot().QualityScore()
		if score > bestScore {
			best = node
			bestScore = score
		}
	}
	return best
}

func (p *GatewayPool) healthyNodes() []*Node {
	out := make([]*Node, 0, len(p.nodes))
	for _, node := range p.nodes {
		if node.Healthy() {
			out = append(out, node)
		}
	}
	return out
}

func (p *GatewayPool) pickRoundRobin(nodes []*Node) *Node {
	idx := atomic.AddUint64(&p.nextIndex, 1) - 1
	return nodes[idx%uint64(len(nodes))]
}

func (p *GatewayPool) pickRandom(nodes []*Node) *Node {
	var buf [8]byte
	if _, err := rand.Read(buf[:]); err != nil {
		return nodes[0]
	}
	idx := binary.BigEndian.Uint64(buf[:]) % uint64(len(nodes))
	return nodes[idx]
}

func (p *GatewayPool) stickyNode(sessionID string, healthy []*Node) *Node {
	now := time.Now()
	p.stickyMu.RLock()
	entry, ok := p.sticky[sessionID]
	p.stickyMu.RUnlock()
	if !ok || now.After(entry.expiresAt) {
		p.stickyMu.Lock()
		delete(p.sticky, sessionID)
		p.stickyMu.Unlock()
		return nil
	}

	for _, node := range healthy {
		if node.ID() == entry.nodeID {
			return node
		}
	}
	return nil
}

func (p *GatewayPool) rememberSticky(sessionID string, node *Node) {
	p.stickyMu.Lock()
	p.sticky[sessionID] = stickyEntry{
		nodeID:    node.ID(),
		expiresAt: time.Now().Add(p.stickyTTL),
	}
	p.stickyMu.Unlock()
}

// Stats returns pool-level telemetry for operators.
func (p *GatewayPool) Stats() PoolStats {
	nodes := make([]NodeStats, 0, len(p.nodes))
	healthyCount := 0
	for _, node := range p.nodes {
		stats := node.Stats()
		nodes = append(nodes, stats)
		if stats.Healthy {
			healthyCount++
		}
	}
	return PoolStats{
		Total:        len(p.nodes),
		Healthy:      healthyCount,
		Rotation:     string(p.rotation),
		StickyTTL:    p.stickyTTL.String(),
		Nodes:        nodes,
	}
}

// PoolStats is returned by the admin API.
type PoolStats struct {
	Total     int         `json:"total"`
	Healthy   int         `json:"healthy"`
	Rotation  string      `json:"rotation"`
	StickyTTL string      `json:"sticky_ttl"`
	Nodes     []NodeStats `json:"nodes"`
}

// AllNodes exposes nodes for health checks.
func (p *GatewayPool) AllNodes() []*Node {
	out := make([]*Node, len(p.nodes))
	copy(out, p.nodes)
	return out
}
