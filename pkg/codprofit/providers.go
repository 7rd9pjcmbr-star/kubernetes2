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

package codprofit

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"time"
)

type RealClock struct{}

func (RealClock) Now() time.Time {
	return time.Now().UTC()
}

type RandomIDGenerator struct{}

func (RandomIDGenerator) NewID(prefix string) string {
	buf := make([]byte, 6)
	if _, err := rand.Read(buf); err != nil {
		// Fallback to timestamp-derived bytes on entropy failure.
		return fmt.Sprintf("%s_%d", prefix, time.Now().UnixNano())
	}
	return fmt.Sprintf("%s_%s", prefix, hex.EncodeToString(buf))
}

// StaticPlanProvider is useful for local runs before workspace-plan plumbing exists.
type StaticPlanProvider struct {
	DefaultPlan string
}

func (s StaticPlanProvider) GetPlan(_ context.Context, _ string) (string, error) {
	if s.DefaultPlan == "" {
		return "free", nil
	}
	return s.DefaultPlan, nil
}
