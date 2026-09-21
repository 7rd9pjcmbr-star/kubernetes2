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
	"context"
	"fmt"
	"io"
	"log"
	"net"
	"strings"
)

// Socks5Server exposes the gateway pool over SOCKS5 for browser/tool clients.
type Socks5Server struct {
	Addr string
	Pool PoolSelector
	Auth GatewayAuth
}

func (s *Socks5Server) ListenAndServe(ctx context.Context) error {
	ln, err := net.Listen("tcp", s.Addr)
	if err != nil {
		return fmt.Errorf("listen socks5 %s: %w", s.Addr, err)
	}
	defer ln.Close()

	go func() {
		<-ctx.Done()
		_ = ln.Close()
	}()

	log.Printf("socks5 gateway listening addr=%s", s.Addr)
	for {
		conn, err := ln.Accept()
		if err != nil {
			select {
			case <-ctx.Done():
				return nil
			default:
				return fmt.Errorf("accept socks5 connection: %w", err)
			}
		}
		go s.handleConn(conn)
	}
}

func (s *Socks5Server) handleConn(conn net.Conn) {
	defer conn.Close()

	remoteIP := conn.RemoteAddr().String()
	if host, _, err := net.SplitHostPort(remoteIP); err == nil {
		remoteIP = host
	}

	username, err := s.negotiate(conn, remoteIP)
	if err != nil {
		log.Printf("socks5 handshake failed remote=%s err=%v", remoteIP, err)
		return
	}

	target, err := s.readConnectRequest(conn)
	if err != nil {
		log.Printf("socks5 connect request failed remote=%s err=%v", remoteIP, err)
		return
	}

	sessionID := ExtractSessionID(username)
	node, err := s.Pool.Select(sessionID)
	if err != nil {
		_, _ = conn.Write([]byte{0x05, 0x01, 0x00, 0x01, 0, 0, 0, 0, 0, 0})
		return
	}

	ctx, cancel := context.WithTimeout(context.Background(), dialTimeout)
	defer cancel()

	upstreamConn, err := dialViaNode(ctx, node, target)
	if err != nil {
		node.MarkFailure()
		_, _ = conn.Write([]byte{0x05, 0x05, 0x00, 0x01, 0, 0, 0, 0, 0, 0})
		return
	}
	defer upstreamConn.Close()
	node.MarkSuccess()

	if _, err := conn.Write([]byte{0x05, 0x00, 0x00, 0x01, 0, 0, 0, 0, 0, 0}); err != nil {
		return
	}
	relay(conn, upstreamConn)
}

func (s *Socks5Server) negotiate(conn net.Conn, remoteIP string) (string, error) {
	header := make([]byte, 2)
	if _, err := io.ReadFull(conn, header); err != nil {
		return "", err
	}
	if header[0] != 0x05 {
		return "", fmt.Errorf("unsupported socks version %d", header[0])
	}

	methods := make([]byte, int(header[1]))
	if _, err := io.ReadFull(conn, methods); err != nil {
		return "", err
	}

	supportsNoAuth := false
	supportsUserPass := false
	for _, method := range methods {
		switch method {
		case 0x00:
			supportsNoAuth = true
		case 0x02:
			supportsUserPass = true
		}
	}

	if s.Auth.Enabled() {
		if !supportsUserPass {
			_, _ = conn.Write([]byte{0x05, 0xFF})
			return "", fmt.Errorf("client does not support username/password auth")
		}
		_, _ = conn.Write([]byte{0x05, 0x02})
		return s.authenticate(conn, remoteIP)
	}

	if !supportsNoAuth {
		_, _ = conn.Write([]byte{0x05, 0xFF})
		return "", fmt.Errorf("client does not support no-auth method")
	}
	if err := s.Auth.checkWhitelist(remoteIP); err != nil {
		return "", err
	}
	_, _ = conn.Write([]byte{0x05, 0x00})
	return "", nil
}

func (s *Socks5Server) authenticate(conn net.Conn, remoteIP string) (string, error) {
	version := make([]byte, 1)
	if _, err := io.ReadFull(conn, version); err != nil {
		return "", err
	}
	if version[0] != 0x01 {
		return "", fmt.Errorf("unsupported auth version %d", version[0])
	}

	userLen := make([]byte, 1)
	if _, err := io.ReadFull(conn, userLen); err != nil {
		return "", err
	}
	userBuf := make([]byte, int(userLen[0]))
	if _, err := io.ReadFull(conn, userBuf); err != nil {
		return "", err
	}

	passLen := make([]byte, 1)
	if _, err := io.ReadFull(conn, passLen); err != nil {
		return "", err
	}
	passBuf := make([]byte, int(passLen[0]))
	if _, err := io.ReadFull(conn, passBuf); err != nil {
		return "", err
	}

	username := string(userBuf)
	password := string(passBuf)
	if _, err := s.Auth.AuthorizeCredentials(username, password, remoteIP); err != nil {
		_, _ = conn.Write([]byte{0x01, 0x01})
		return "", err
	}
	_, _ = conn.Write([]byte{0x01, 0x00})
	return username, nil
}

func (s *Socks5Server) readConnectRequest(conn net.Conn) (string, error) {
	header := make([]byte, 4)
	if _, err := io.ReadFull(conn, header); err != nil {
		return "", err
	}
	if header[0] != 0x05 || header[1] != 0x01 {
		return "", fmt.Errorf("only CONNECT command is supported")
	}

	var host string
	switch header[3] {
	case 0x01:
		addr := make([]byte, 4)
		if _, err := io.ReadFull(conn, addr); err != nil {
			return "", err
		}
		host = net.IP(addr).String()
	case 0x03:
		lenBuf := make([]byte, 1)
		if _, err := io.ReadFull(conn, lenBuf); err != nil {
			return "", err
		}
		name := make([]byte, int(lenBuf[0]))
		if _, err := io.ReadFull(conn, name); err != nil {
			return "", err
		}
		host = string(name)
	case 0x04:
		addr := make([]byte, 16)
		if _, err := io.ReadFull(conn, addr); err != nil {
			return "", err
		}
		host = net.IP(addr).String()
	default:
		return "", fmt.Errorf("unsupported address type %d", header[3])
	}

	portBuf := make([]byte, 2)
	if _, err := io.ReadFull(conn, portBuf); err != nil {
		return "", err
	}
	port := int(portBuf[0])<<8 | int(portBuf[1])
	if strings.Contains(host, ":") {
		return fmt.Sprintf("[%s]:%d", host, port), nil
	}
	return fmt.Sprintf("%s:%d", host, port), nil
}
