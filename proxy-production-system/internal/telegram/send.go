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
	"log"

	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api/v5"
)

func (b *Bot) sendPanel(chatID int64, text string, keyboard tgbotapi.InlineKeyboardMarkup) {
	msg := tgbotapi.NewMessage(chatID, text)
	msg.ParseMode = tgbotapi.ModeMarkdown
	msg.ReplyMarkup = keyboard
	if _, err := b.api.Send(msg); err != nil {
		log.Printf("telegram panel send failed chat=%d err=%v", chatID, err)
	}
}

func (b *Bot) showPanel(chatID int64) {
	text := mainPanelText() + "\n\n_👇 Dùng menu bàn phím nhanh bên dưới ô chat_"
	b.sendPanel(chatID, text, mainPanelKeyboard())
	b.ensureQuickMenu(chatID)
}

func (b *Bot) ensureQuickMenu(chatID int64) {
	menu := replyMenuKeyboard()
	msg := tgbotapi.NewMessage(chatID, "⌨️ Menu nhanh đã sẵn sàng — chọn nút bên dưới.")
	msg.ReplyMarkup = menu
	if _, err := b.api.Send(msg); err != nil {
		log.Printf("telegram quick menu failed chat=%d err=%v", chatID, err)
	}
}

func (b *Bot) hideQuickMenu(chatID int64) {
	msg := tgbotapi.NewMessage(chatID, "Đã ẩn menu bàn phím. Gõ /panel để mở lại.")
	msg.ReplyMarkup = removeMenuKeyboard()
	if _, err := b.api.Send(msg); err != nil {
		log.Printf("telegram hide menu failed chat=%d err=%v", chatID, err)
	}
}

func (b *Bot) editPanel(chatID int64, messageID int, text string, keyboard tgbotapi.InlineKeyboardMarkup) {
	edit := tgbotapi.NewEditMessageText(chatID, messageID, text)
	edit.ParseMode = tgbotapi.ModeMarkdown
	edit.ReplyMarkup = &keyboard
	if _, err := b.api.Send(edit); err != nil {
		log.Printf("telegram panel edit failed chat=%d err=%v", chatID, err)
		b.sendPanel(chatID, text, keyboard)
	}
}

func (b *Bot) answerCallback(callbackID, text string) {
	callback := tgbotapi.NewCallback(callbackID, text)
	if _, err := b.api.Request(callback); err != nil {
		log.Printf("telegram callback answer failed: %v", err)
	}
}

func (b *Bot) setupCommands() {
	commands := tgbotapi.NewSetMyCommands(
		tgbotapi.BotCommand{Command: "start", Description: "Mở bảng điều khiển + menu nhanh"},
		tgbotapi.BotCommand{Command: "panel", Description: "Bảng điều khiển proxy"},
		tgbotapi.BotCommand{Command: "menu", Description: "Hiện menu bàn phím nhanh"},
		tgbotapi.BotCommand{Command: "stats", Description: "Thống kê pool"},
		tgbotapi.BotCommand{Command: "list", Description: "Danh sách backend"},
		tgbotapi.BotCommand{Command: "help", Description: "Trợ giúp"},
	)
	if _, err := b.api.Request(commands); err != nil {
		log.Printf("set bot commands failed: %v", err)
	}
}
