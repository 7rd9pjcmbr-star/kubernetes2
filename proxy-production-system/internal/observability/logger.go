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

package observability

import (
	"log/slog"
	"os"
	"strings"
)

func ConfigureLogger(format string) {
	level := new(slog.LevelVar)
	level.Set(slog.LevelInfo)

	var handler slog.Handler
	options := &slog.HandlerOptions{Level: level}
	if strings.EqualFold(format, "text") {
		handler = slog.NewTextHandler(os.Stdout, options)
	} else {
		handler = slog.NewJSONHandler(os.Stdout, options)
	}
	slog.SetDefault(slog.New(handler))
}
