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
	"encoding/base64"
	"fmt"
	"net"
	"net/http"
	"strings"
)

// GatewayAuth enforces customer credentials and optional client IP whitelist.
type GatewayAuth struct {
	Username  string
	Password  string
	Whitelist map[string]struct{}
}

func NewGatewayAuth(username, password string, whitelist []string) GatewayAuth {
	allowed := make(map[string]struct{}, len(whitelist))
	for _, ip := range whitelist {
		ip = strings.TrimSpace(ip)
		if ip != "" {
			allowed[ip] = struct{}{}
		}
	}
	return GatewayAuth{
		Username:  strings.TrimSpace(username),
		Password:  password,
		Whitelist: allowed,
	}
}

func (a GatewayAuth) Enabled() bool {
	return a.Username != "" || a.Password != ""
}

func (a GatewayAuth) WhitelistEnabled() bool {
	return len(a.Whitelist) > 0
}

func (a GatewayAuth) AuthorizeRequest(r *http.Request) (string, error) {
	if err := a.checkWhitelist(clientIP(r)); err != nil {
		return "", err
	}
	if !a.Enabled() {
		return "", nil
	}

	username, password, ok := r.BasicAuth()
	if !ok {
		if header := r.Header.Get("Proxy-Authorization"); header != "" {
			username, password, ok = parseBasicAuth(header)
		}
	}
	if !ok || username != a.Username || password != a.Password {
		return "", fmt.Errorf("invalid proxy credentials")
	}
	return username, nil
}

func (a GatewayAuth) AuthorizeCredentials(username, password string, remoteIP string) (string, error) {
	if err := a.checkWhitelist(remoteIP); err != nil {
		return "", err
	}
	if !a.Enabled() {
		return username, nil
	}
	if username != a.Username || password != a.Password {
		return "", fmt.Errorf("invalid proxy credentials")
	}
	return username, nil
}

func (a GatewayAuth) checkWhitelist(remoteIP string) error {
	if !a.WhitelistEnabled() {
		return nil
	}
	ip := strings.TrimSpace(remoteIP)
	if _, ok := a.Whitelist[ip]; ok {
		return nil
	}
	return fmt.Errorf("client IP %q is not whitelisted", ip)
}

func clientIP(r *http.Request) string {
	if forwarded := r.Header.Get("X-Forwarded-For"); forwarded != "" {
		parts := strings.Split(forwarded, ",")
		return strings.TrimSpace(parts[0])
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}

func parseBasicAuth(header string) (username, password string, ok bool) {
	const prefix = "Basic "
	if !strings.HasPrefix(header, prefix) {
		return "", "", false
	}
	decoded, err := base64.StdEncoding.DecodeString(strings.TrimSpace(header[len(prefix):]))
	if err != nil {
		return "", "", false
	}
	parts := strings.SplitN(string(decoded), ":", 2)
	if len(parts) != 2 {
		return "", "", false
	}
	return parts[0], parts[1], true
}
