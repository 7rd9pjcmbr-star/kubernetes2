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

import tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api/v5"

// Nhãn nút menu bàn phím nhanh Telegram (ReplyKeyboard).
const (
	btnPanel      = "🎛 Bảng điều khiển"
	btnStats      = "📊 Thống kê"
	btnList       = "📋 Danh sách"
	btnPoolFiles  = "📁 150 Proxy"
	btnDead       = "☠️ Node dead"
	btnSubscribe  = "🔔 Bật cảnh báo"
	btnUnsubscribe = "🔕 Tắt cảnh báo"
	btnHelp       = "❓ Trợ giúp"
	btnHideMenu   = "⌨️ Ẩn menu"
)

func replyMenuKeyboard() tgbotapi.ReplyKeyboardMarkup {
	keyboard := tgbotapi.NewReplyKeyboard(
		tgbotapi.NewKeyboardButtonRow(
			tgbotapi.NewKeyboardButton(btnPanel),
			tgbotapi.NewKeyboardButton(btnStats),
		),
		tgbotapi.NewKeyboardButtonRow(
			tgbotapi.NewKeyboardButton(btnList),
			tgbotapi.NewKeyboardButton(btnPoolFiles),
		),
		tgbotapi.NewKeyboardButtonRow(
			tgbotapi.NewKeyboardButton(btnDead),
			tgbotapi.NewKeyboardButton(btnSubscribe),
		),
		tgbotapi.NewKeyboardButtonRow(
			tgbotapi.NewKeyboardButton(btnUnsubscribe),
			tgbotapi.NewKeyboardButton(btnHelp),
		),
		tgbotapi.NewKeyboardButtonRow(
			tgbotapi.NewKeyboardButton(btnHideMenu),
		),
	)
	keyboard.ResizeKeyboard = true
	keyboard.OneTimeKeyboard = false
	keyboard.InputFieldPlaceholder = "Chọn menu nhanh hoặc gõ /panel"
	return keyboard
}

func removeMenuKeyboard() tgbotapi.ReplyKeyboardRemove {
	remove := tgbotapi.NewRemoveKeyboard(true)
	return remove
}
