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
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

const dialTimeout = 15 * time.Second

func dialViaNode(ctx context.Context, node *Node, targetAddr string) (net.Conn, error) {
	switch strings.ToLower(node.URL.Scheme) {
	case "socks5", "socks5h":
		return dialSocks5(node.URL, targetAddr)
	default:
		return dialHTTPConnect(ctx, node.URL, targetAddr)
	}
}

func dialHTTPConnect(ctx context.Context, upstream *url.URL, targetAddr string) (net.Conn, error) {
	dialer := &net.Dialer{Timeout: dialTimeout}
	conn, err := dialer.DialContext(ctx, "tcp", upstream.Host)
	if err != nil {
		return nil, fmt.Errorf("connect upstream %s: %w", upstream.Host, err)
	}

	connectReq := &http.Request{
		Method: http.MethodConnect,
		URL:    &url.URL{Opaque: targetAddr},
		Host:   targetAddr,
		Header: make(http.Header),
	}
	if upstream.User != nil {
		password, _ := upstream.User.Password()
		connectReq.SetBasicAuth(upstream.User.Username(), password)
	}

	if err := connectReq.Write(conn); err != nil {
		_ = conn.Close()
		return nil, fmt.Errorf("write CONNECT to upstream: %w", err)
	}

	br := bufio.NewReader(conn)
	resp, err := http.ReadResponse(br, connectReq)
	if err != nil {
		_ = conn.Close()
		return nil, fmt.Errorf("read CONNECT response: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		_ = conn.Close()
		return nil, fmt.Errorf("upstream CONNECT failed: %s", resp.Status)
	}

	if br.Buffered() > 0 {
		return &bufferedConn{Conn: conn, r: br}, nil
	}
	return conn, nil
}

type bufferedConn struct {
	net.Conn
	r *bufio.Reader
}

func (c *bufferedConn) Read(p []byte) (int, error) {
	return c.r.Read(p)
}

func dialSocks5(upstream *url.URL, targetAddr string) (net.Conn, error) {
	conn, err := net.DialTimeout("tcp", upstream.Host, dialTimeout)
	if err != nil {
		return nil, fmt.Errorf("connect socks upstream %s: %w", upstream.Host, err)
	}

	username := ""
	password := ""
	if upstream.User != nil {
		username = upstream.User.Username()
		password, _ = upstream.User.Password()
	}

	if err := socks5Handshake(conn, username, password); err != nil {
		_ = conn.Close()
		return nil, err
	}
	if err := socks5Connect(conn, targetAddr); err != nil {
		_ = conn.Close()
		return nil, err
	}
	return conn, nil
}

func socks5Handshake(conn net.Conn, username, password string) error {
	methods := []byte{0x05, 0x01, 0x00}
	if username != "" || password != "" {
		methods = []byte{0x05, 0x01, 0x02}
	}
	if _, err := conn.Write(methods); err != nil {
		return fmt.Errorf("write socks greeting: %w", err)
	}

	resp := make([]byte, 2)
	if _, err := io.ReadFull(conn, resp); err != nil {
		return fmt.Errorf("read socks method: %w", err)
	}
	if resp[0] != 0x05 {
		return fmt.Errorf("unsupported socks version %d", resp[0])
	}

	switch resp[1] {
	case 0x00:
		return nil
	case 0x02:
		userBytes := []byte(username)
		passBytes := []byte(password)
		auth := make([]byte, 0, 3+len(userBytes)+len(passBytes))
		auth = append(auth, 0x01, byte(len(userBytes)))
		auth = append(auth, userBytes...)
		auth = append(auth, byte(len(passBytes)))
		auth = append(auth, passBytes...)
		if _, err := conn.Write(auth); err != nil {
			return fmt.Errorf("write socks auth: %w", err)
		}
		authResp := make([]byte, 2)
		if _, err := io.ReadFull(conn, authResp); err != nil {
			return fmt.Errorf("read socks auth response: %w", err)
		}
		if authResp[1] != 0x00 {
			return fmt.Errorf("socks auth rejected")
		}
		return nil
	default:
		return fmt.Errorf("socks auth method %d not supported", resp[1])
	}
}

func socks5Connect(conn net.Conn, targetAddr string) error {
	host, port, err := net.SplitHostPort(targetAddr)
	if err != nil {
		return fmt.Errorf("invalid target address %q: %w", targetAddr, err)
	}

	req := []byte{0x05, 0x01, 0x00, 0x03, byte(len(host))}
	req = append(req, []byte(host)...)
	portNum := 0
	if _, err := fmt.Sscanf(port, "%d", &portNum); err != nil {
		return fmt.Errorf("parse port %q: %w", port, err)
	}
	req = append(req, byte(portNum>>8), byte(portNum))

	if _, err := conn.Write(req); err != nil {
		return fmt.Errorf("write socks connect: %w", err)
	}

	header := make([]byte, 4)
	if _, err := io.ReadFull(conn, header); err != nil {
		return fmt.Errorf("read socks connect header: %w", err)
	}
	if header[1] != 0x00 {
		return fmt.Errorf("socks connect failed with code %d", header[1])
	}

	switch header[3] {
	case 0x01:
		discard := make([]byte, 4+2)
		_, _ = io.ReadFull(conn, discard)
	case 0x03:
		lenBuf := make([]byte, 1)
		if _, err := io.ReadFull(conn, lenBuf); err != nil {
			return err
		}
		discard := make([]byte, int(lenBuf[0])+2)
		_, _ = io.ReadFull(conn, discard)
	case 0x04:
		discard := make([]byte, 16+2)
		_, _ = io.ReadFull(conn, discard)
	}
	return nil
}

func relay(left, right net.Conn) {
	defer left.Close()
	defer right.Close()
	done := make(chan struct{}, 2)
	go func() {
		_, _ = io.Copy(left, right)
		done <- struct{}{}
	}()
	go func() {
		_, _ = io.Copy(right, left)
		done <- struct{}{}
	}()
	<-done
}
