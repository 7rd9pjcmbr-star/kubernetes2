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

func (b *Bot) sendPanelWithReply(chatID int64, text string, inline tgbotapi.InlineKeyboardMarkup, reply tgbotapi.ReplyKeyboardMarkup) {
	msg := tgbotapi.NewMessage(chatID, text)
	msg.ParseMode = tgbotapi.ModeMarkdown
	msg.ReplyMarkup = inline
	if _, err := b.api.Send(msg); err != nil {
		log.Printf("telegram panel send failed chat=%d err=%v", chatID, err)
	}
	replyMsg := tgbotapi.NewMessage(chatID, "👇 Menu nhanh — chọn nút hoặc dùng bảng inline phía trên")
	replyMsg.ReplyMarkup = reply
	if _, err := b.api.Send(replyMsg); err != nil {
		log.Printf("telegram reply keyboard failed chat=%d err=%v", chatID, err)
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
		tgbotapi.BotCommand{Command: "start", Description: "Mở bảng điều khiển"},
		tgbotapi.BotCommand{Command: "panel", Description: "Bảng điều khiển proxy"},
		tgbotapi.BotCommand{Command: "stats", Description: "Thống kê pool"},
		tgbotapi.BotCommand{Command: "list", Description: "Danh sách backend"},
		tgbotapi.BotCommand{Command: "help", Description: "Trợ giúp"},
	)
	if _, err := b.api.Request(commands); err != nil {
		log.Printf("set bot commands failed: %v", err)
	}
}
