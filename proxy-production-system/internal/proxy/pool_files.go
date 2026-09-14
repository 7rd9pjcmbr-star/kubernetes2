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
	"fmt"
	"os"
	"strings"
)

// LoadPoolEntriesFromFiles reads one proxy entry per line from pool list files.
func LoadPoolEntriesFromFiles(paths []string) ([]string, error) {
	entries := make([]string, 0)
	for _, path := range paths {
		path = strings.TrimSpace(path)
		if path == "" {
			continue
		}
		fileEntries, err := readPoolFile(path)
		if err != nil {
			return nil, fmt.Errorf("read pool file %q: %w", path, err)
		}
		entries = append(entries, fileEntries...)
	}
	return entries, nil
}

func readPoolFile(path string) ([]string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	entries := make([]string, 0, 128)
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		entries = append(entries, line)
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}
	return entries, nil
}
