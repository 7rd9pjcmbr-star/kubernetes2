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

package model

import (
	"fmt"
	"net"
	"strings"
	"time"
)

const (
	BackendStatusActive  = "active"
	BackendStatusDead    = "dead"
	BackendStatusTesting = "testing"

	AnonymityElite       = "elite"
	AnonymityAnonymous   = "anonymous"
	AnonymityTransparent = "transparent"

	BackendTypeHTTP   = "http"
	BackendTypeHTTPS  = "https"
	BackendTypeSocks5 = "socks5"
	BackendType4G     = "4g"
)

// ProxyBackend describes one exit node stored in MongoDB and used by the gateway.
type ProxyBackend struct {
	ID            string    `bson:"_id,omitempty" json:"id"`
	IP            string    `bson:"ip" json:"ip"`
	Port          int       `bson:"port" json:"port"`
	Type          string    `bson:"type" json:"type"`
	Country       string    `bson:"country" json:"country"`
	Anonymity     string    `bson:"anonymity" json:"anonymity"`
	Status        string    `bson:"status" json:"status"`
	Latency       int       `bson:"latency" json:"latency"`
	SuccessRate   float64   `bson:"success_rate" json:"success_rate"`
	TotalRequests int64     `bson:"total_requests" json:"total_requests"`
	CreatedAt     time.Time `bson:"created_at" json:"created_at"`
	LastChecked   time.Time `bson:"last_checked" json:"last_checked"`
}

// UpstreamURL builds the scheme://host:port string consumed by the gateway dialer.
func (b ProxyBackend) UpstreamURL() string {
	scheme := BackendTypeHTTP
	switch strings.ToLower(strings.TrimSpace(b.Type)) {
	case BackendTypeSocks5, "socks5h":
		scheme = BackendTypeSocks5
	case BackendTypeHTTPS:
		scheme = BackendTypeHTTPS
	case BackendType4G, BackendTypeHTTP, "":
		scheme = BackendTypeHTTP
	default:
		scheme = BackendTypeHTTP
	}
	return fmt.Sprintf("%s://%s", scheme, net.JoinHostPort(b.IP, fmt.Sprintf("%d", b.Port)))
}

// NodeKey returns a stable routing key for sticky sessions.
func (b ProxyBackend) NodeKey() string {
	if b.ID != "" {
		return b.ID
	}
	return net.JoinHostPort(b.IP, fmt.Sprintf("%d", b.Port))
}

// Normalize fills defaults for records loaded from Mongo or env bootstrap.
func (b *ProxyBackend) Normalize(now time.Time) {
	if strings.TrimSpace(b.Country) == "" {
		b.Country = "VN"
	}
	if strings.TrimSpace(b.Anonymity) == "" {
		b.Anonymity = AnonymityElite
	}
	if strings.TrimSpace(b.Status) == "" {
		b.Status = BackendStatusActive
	}
	if strings.TrimSpace(b.Type) == "" {
		b.Type = BackendTypeHTTP
	}
	if b.SuccessRate <= 0 {
		b.SuccessRate = 100
	}
	if b.CreatedAt.IsZero() {
		b.CreatedAt = now
	}
	if b.LastChecked.IsZero() {
		b.LastChecked = now
	}
}

// AnonymityWeight ranks elite exits above anonymous/transparent nodes.
func AnonymityWeight(level string) float64 {
	switch strings.ToLower(strings.TrimSpace(level)) {
	case AnonymityElite:
		return 1.0
	case AnonymityAnonymous:
		return 0.7
	case AnonymityTransparent:
		return 0.3
	default:
		return 0.5
	}
}

// QualityScore combines success rate, latency, and anonymity for gateway routing.
func (b ProxyBackend) QualityScore() float64 {
	if b.Status == BackendStatusDead {
		return -1
	}
	latencyPenalty := float64(b.Latency) / 100.0
	statusBoost := 0.0
	if b.Status == BackendStatusActive {
		statusBoost = 10
	}
	return b.SuccessRate*AnonymityWeight(b.Anonymity) + statusBoost - latencyPenalty
}

// RecordRequest updates rolling success metrics after one proxied call.
func (b *ProxyBackend) RecordRequest(success bool, now time.Time) {
	b.TotalRequests++
	if b.TotalRequests == 1 {
		if success {
			b.SuccessRate = 100
		} else {
			b.SuccessRate = 0
		}
	} else {
		prevSuccess := b.SuccessRate * float64(b.TotalRequests-1) / 100
		if success {
			prevSuccess++
		}
		b.SuccessRate = prevSuccess / float64(b.TotalRequests) * 100
	}

	if success {
		if b.Status == BackendStatusTesting {
			b.Status = BackendStatusActive
		}
	} else if b.SuccessRate < 50 && b.TotalRequests >= 10 {
		b.Status = BackendStatusDead
	} else if !success {
		b.Status = BackendStatusTesting
	}
	b.LastChecked = now
}
