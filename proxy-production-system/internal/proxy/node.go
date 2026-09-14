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
	"sync/atomic"
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
	ID       string
	URL      *url.URL
	Kind     NodeKind
	Region   string
	healthy  atomic.Bool
	failures atomic.Uint64
	success  atomic.Uint64
}

func newNode(rawURL, kind, region string) (*Node, error) {
	parsed, err := url.Parse(strings.TrimSpace(rawURL))
	if err != nil {
		return nil, fmt.Errorf("parse upstream %q: %w", rawURL, err)
	}
	if parsed.Scheme == "" || parsed.Host == "" {
		return nil, fmt.Errorf("upstream %q must include scheme and host", rawURL)
	}

	nodeKind, err := parseNodeKind(kind)
	if err != nil {
		return nil, err
	}

	node := &Node{
		ID:     parsed.Host,
		URL:    parsed,
		Kind:   nodeKind,
		Region: strings.TrimSpace(region),
	}
	node.healthy.Store(true)
	return node, nil
}

func parseNodeKind(raw string) (NodeKind, error) {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "", "residential", "resi":
		return NodeKindResidential, nil
	case "4g", "mobile", "lte":
		return NodeKindMobile4G, nil
	case "isp", "static":
		return NodeKindISP, nil
	case "datacenter", "dc", "server":
		return NodeKindDatacenter, nil
	default:
		return "", fmt.Errorf("unknown node kind %q", raw)
	}
}

func (n *Node) Healthy() bool {
	return n.healthy.Load()
}

func (n *Node) MarkSuccess() {
	n.success.Add(1)
	n.failures.Store(0)
	n.healthy.Store(true)
}

func (n *Node) MarkFailure() {
	n.failures.Add(1)
	if n.failures.Load() >= 3 {
		n.healthy.Store(false)
	}
}

func (n *Node) Stats() NodeStats {
	return NodeStats{
		ID:       n.ID,
		Kind:     string(n.Kind),
		Region:   n.Region,
		Healthy:  n.Healthy(),
		Failures: n.failures.Load(),
		Success:  n.success.Load(),
	}
}

// NodeStats is a snapshot for the admin API.
type NodeStats struct {
	ID       string `json:"id"`
	Kind     string `json:"kind"`
	Region   string `json:"region"`
	Healthy  bool   `json:"healthy"`
	Failures uint64 `json:"failures"`
	Success  uint64 `json:"success"`
}
