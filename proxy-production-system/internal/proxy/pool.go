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
	"sync/atomic"
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
