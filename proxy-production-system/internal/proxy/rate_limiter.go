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
	"sync"
	"time"
)

type rateLimiterStore struct {
	mu       sync.Mutex
	rate     float64
	burst    float64
	visitors map[string]*bucket
	now      func() time.Time
}

type bucket struct {
	tokens      float64
	lastRefill  time.Time
	lastTouched time.Time
}

func newRateLimiterStore(ratePerSecond, burst int) *rateLimiterStore {
	return &rateLimiterStore{
		rate:     float64(ratePerSecond),
		burst:    float64(burst),
		visitors: map[string]*bucket{},
		now:      time.Now,
	}
}

func (s *rateLimiterStore) Allow(key string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()

	now := s.now()
	s.pruneIdle(now)

	b, ok := s.visitors[key]
	if !ok {
		s.visitors[key] = &bucket{
			tokens:      s.burst - 1,
			lastRefill:  now,
			lastTouched: now,
		}
		return true
	}

	elapsedSeconds := now.Sub(b.lastRefill).Seconds()
	b.tokens += elapsedSeconds * s.rate
	if b.tokens > s.burst {
		b.tokens = s.burst
	}
	b.lastRefill = now
	b.lastTouched = now

	if b.tokens < 1 {
		return false
	}
	b.tokens--
	return true
}

func (s *rateLimiterStore) pruneIdle(now time.Time) {
	const ttl = 2 * time.Minute
	for key, visitor := range s.visitors {
		if now.Sub(visitor.lastTouched) > ttl {
			delete(s.visitors, key)
		}
	}
}
