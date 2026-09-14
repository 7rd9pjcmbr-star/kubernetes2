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
	"os"
	"path/filepath"
	"testing"
)

func TestLoadPoolEntriesFromFiles(t *testing.T) {
	t.Helper()

	dir := t.TempDir()
	first := filepath.Join(dir, "a.txt")
	second := filepath.Join(dir, "b.txt")
	if err := os.WriteFile(first, []byte("http://127.0.0.1:31001|4g|VN-HCM|elite|40|99\n# comment\n"), 0o644); err != nil {
		t.Fatalf("write first file: %v", err)
	}
	if err := os.WriteFile(second, []byte("http://127.0.0.1:32001|residential|VN-HN|elite|35|98\n"), 0o644); err != nil {
		t.Fatalf("write second file: %v", err)
	}

	entries, err := LoadPoolEntriesFromFiles([]string{first, second})
	if err != nil {
		t.Fatalf("LoadPoolEntriesFromFiles failed: %v", err)
	}
	if len(entries) != 2 {
		t.Fatalf("expected 2 entries, got %d", len(entries))
	}
}
