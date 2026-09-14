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
)

func TestMainPanelKeyboardHasControlButtons(t *testing.T) {
	t.Helper()
	keyboard := mainPanelKeyboard()
	if len(keyboard.InlineKeyboard) < 3 {
		t.Fatalf("expected at least 3 keyboard rows, got %d", len(keyboard.InlineKeyboard))
	}
}

func TestListPageKeyboardPagination(t *testing.T) {
	t.Helper()
	keyboard := listPageKeyboard(1, 5)
	if len(keyboard.InlineKeyboard) == 0 {
		t.Fatalf("expected pagination keyboard")
	}
	foundHome := false
	for _, row := range keyboard.InlineKeyboard {
		for _, button := range row {
			if button.CallbackData != nil && *button.CallbackData == callbackHome {
				foundHome = true
			}
		}
	}
	if !foundHome {
		t.Fatalf("expected home button in list pagination keyboard")
	}
}

func TestMainPanelTextMentionsControlPanel(t *testing.T) {
	t.Helper()
	if !strings.Contains(mainPanelText(), "Bảng điều khiển") {
		t.Fatalf("panel text should mention control panel")
	}
}
