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

package telegram

import (
	"strings"
	"testing"

	"proxy-production-system/internal/model"
)

func TestFormatBackendLine(t *testing.T) {
	t.Helper()

	line := formatBackendLine(model.ProxyBackend{
		ID:          "abc12345",
		IP:          "203.0.113.1",
		Port:        3128,
		Type:        model.BackendType4G,
		Status:      model.BackendStatusActive,
		Latency:     40,
		SuccessRate: 99,
	})
	if !strings.Contains(line, "203.0.113.1:3128") {
		t.Fatalf("unexpected backend line: %q", line)
	}
}

func TestHelpTextMentionsBot(t *testing.T) {
	t.Helper()
	if !strings.Contains(helpText(), "TondaithanhBot") {
		t.Fatalf("help text should mention bot username")
	}
}
