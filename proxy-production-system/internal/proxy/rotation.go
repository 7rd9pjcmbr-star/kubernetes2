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
	"strings"
)

// RotationMode controls how the gateway picks upstream exit nodes.
type RotationMode string

const (
	RotationRoundRobin RotationMode = "round_robin"
	RotationRandom     RotationMode = "random"
	RotationSticky     RotationMode = "sticky"
	RotationQuality    RotationMode = "quality"
)

// ParseRotationMode reads env-friendly rotation labels.
func ParseRotationMode(raw string) (RotationMode, error) {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "", string(RotationRoundRobin), "rr":
		return RotationRoundRobin, nil
	case string(RotationRandom), "rand":
		return RotationRandom, nil
	case string(RotationSticky), "session":
		return RotationSticky, nil
	case string(RotationQuality), "best", "score":
		return RotationQuality, nil
	default:
		return "", fmt.Errorf("unknown rotation mode %q", raw)
	}
}

// ExtractSessionID reads sticky session keys from gateway credentials.
// VN providers often encode session in username: user-session-abc123.
func ExtractSessionID(username string) string {
	username = strings.TrimSpace(username)
	if username == "" {
		return ""
	}

	parts := strings.Split(username, "-")
	for i := 0; i < len(parts)-1; i++ {
		if parts[i] == "session" && parts[i+1] != "" {
			return parts[i+1]
		}
	}
	return ""
}
