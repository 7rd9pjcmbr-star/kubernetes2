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
	"bufio"
	"context"
	"io"
	"log"
	"net/http"
	"strings"
	"time"
)

// ForwardHTTPProxy serves HTTP/HTTPS traffic through the rotating gateway pool.
type ForwardHTTPProxy struct {
	Pool      PoolSelector
	Auth      GatewayAuth
	EliteMode bool
}

func (p *ForwardHTTPProxy) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	username, err := p.Auth.AuthorizeRequest(r)
	if err != nil {
		if strings.Contains(err.Error(), "whitelisted") {
			http.Error(w, err.Error(), http.StatusForbidden)
			return
		}
		w.Header().Set("Proxy-Authenticate", `Basic realm="proxy-gateway"`)
		http.Error(w, "proxy authentication required", http.StatusProxyAuthRequired)
		return
	}

	if p.EliteMode {
		SanitizeEliteRequest(r)
	}

	sessionID := ExtractSessionID(username)
	node, err := p.Pool.Select(sessionID)
	if err != nil {
		http.Error(w, "no healthy upstream proxy available", http.StatusBadGateway)
		return
	}

	if r.Method == http.MethodConnect {
		p.handleConnect(w, r, node)
		return
	}
	p.handleHTTP(w, r, node)
}

func (p *ForwardHTTPProxy) handleConnect(w http.ResponseWriter, r *http.Request, node *Node) {
	target := r.Host
	if !strings.Contains(target, ":") {
		target += ":443"
	}

	hijacker, ok := w.(http.Hijacker)
	if !ok {
		http.Error(w, "hijacking not supported", http.StatusInternalServerError)
		return
	}

	clientConn, _, err := hijacker.Hijack()
	if err != nil {
		http.Error(w, "failed to hijack connection", http.StatusInternalServerError)
		return
	}
	defer clientConn.Close()

	ctx, cancel := context.WithTimeout(context.Background(), dialTimeout)
	defer cancel()

	upstreamConn, err := dialViaNode(ctx, node, target)
	if err != nil {
		node.MarkFailure()
		log.Printf("connect upstream node=%s target=%s err=%v", node.ID(), target, err)
		_, _ = clientConn.Write([]byte("HTTP/1.1 502 Bad Gateway\r\n\r\n"))
		return
	}
	defer upstreamConn.Close()
	node.MarkSuccess()

	_, _ = clientConn.Write([]byte("HTTP/1.1 200 Connection Established\r\n\r\n"))
	relay(clientConn, upstreamConn)
}

func (p *ForwardHTTPProxy) handleHTTP(w http.ResponseWriter, r *http.Request, node *Node) {
	if !r.URL.IsAbs() {
		http.Error(w, "absolute URL required for non-CONNECT requests", http.StatusBadRequest)
		return
	}

	targetHost := r.URL.Host
	if !strings.Contains(targetHost, ":") {
		if r.URL.Scheme == "https" {
			targetHost += ":443"
		} else {
			targetHost += ":80"
		}
	}

	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()

	upstreamConn, err := dialViaNode(ctx, node, targetHost)
	if err != nil {
		node.MarkFailure()
		http.Error(w, "upstream unavailable", http.StatusBadGateway)
		return
	}
	defer upstreamConn.Close()
	node.MarkSuccess()

	req := r.Clone(ctx)
	req.RequestURI = ""
	if p.EliteMode {
		SanitizeEliteRequest(req)
	} else {
		req.Header.Del("Proxy-Authorization")
		req.Header.Del("Proxy-Connection")
	}

	if err := req.Write(upstreamConn); err != nil {
		http.Error(w, "failed to forward request", http.StatusBadGateway)
		return
	}

	resp, err := http.ReadResponse(bufio.NewReader(upstreamConn), req)
	if err != nil {
		http.Error(w, "failed to read upstream response", http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	copyHeader(w.Header(), resp.Header)
	w.WriteHeader(resp.StatusCode)
	_, _ = io.Copy(w, resp.Body)
}

func copyHeader(dst, src http.Header) {
	for key, values := range src {
		for _, value := range values {
			dst.Add(key, value)
		}
	}
}
