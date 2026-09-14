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
	"testing"
)

func TestEncodeBasicAuth(t *testing.T) {
	got := encodeBasicAuth("user:secret")
	want := "Basic " + base64.StdEncoding.EncodeToString([]byte("user:secret"))
	if got != want {
		t.Fatalf("unexpected basic auth header: got=%q want=%q", got, want)
	}
	if encodeBasicAuth("  ") != "" {
		t.Fatalf("empty basic auth should return empty header")
	}
}

func TestSingleJoiningSlash(t *testing.T) {
	cases := []struct {
		a, b, want string
	}{
		{"/Main/", "Login.aspx", "/Main/Login.aspx"},
		{"/Main", "/Login.aspx", "/Main/Login.aspx"},
		{"/Main/", "/Login.aspx", "/Main/Login.aspx"},
	}
	for _, tc := range cases {
		got := singleJoiningSlash(tc.a, tc.b)
		if got != tc.want {
			t.Fatalf("singleJoiningSlash(%q,%q)=%q want=%q", tc.a, tc.b, got, tc.want)
		}
	}
}
