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

import "net/http"

// Headers that leak proxy hops and trigger anti-bot heuristics on VN platforms.
var eliteStripHeaders = []string{
	"X-Forwarded-For",
	"X-Forwarded-Proto",
	"X-Forwarded-Host",
	"X-Real-Ip",
	"Forwarded",
	"Via",
	"Proxy-Connection",
	"Proxy-Authorization",
	"Proxy-Authenticate",
}

const defaultEliteUserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

// SanitizeEliteRequest strips proxy fingerprints before traffic exits the gateway.
func SanitizeEliteRequest(r *http.Request) {
	for _, header := range eliteStripHeaders {
		r.Header.Del(header)
	}
	if r.Header.Get("User-Agent") == "" {
		r.Header.Set("User-Agent", defaultEliteUserAgent)
	}
}
