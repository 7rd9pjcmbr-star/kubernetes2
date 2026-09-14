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
	"strconv"

	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api/v5"
)

const (
	callbackHome       = "panel:home"
	callbackStats      = "panel:stats"
	callbackList       = "panel:list:"
	callbackPoolFiles  = "panel:poolfiles"
	callbackSubscribe  = "panel:subscribe"
	callbackUnsub      = "panel:unsub"
	callbackDead       = "panel:dead"
	callbackHelp       = "panel:help"
	listPageSize       = 8
)

func mainPanelText() string {
	return "*🎛 Bảng điều khiển @TondaithanhBot*\n\n" +
		"Quản lý 150 proxy (MongoDB) — chọn nút bên dưới:"
}

func mainPanelKeyboard() tgbotapi.InlineKeyboardMarkup {
	return tgbotapi.NewInlineKeyboardMarkup(
		tgbotapi.NewInlineKeyboardRow(
			tgbotapi.NewInlineKeyboardButtonData("📊 Thống kê", callbackStats),
			tgbotapi.NewInlineKeyboardButtonData("📋 Danh sách", callbackList+"0"),
		),
		tgbotapi.NewInlineKeyboardRow(
			tgbotapi.NewInlineKeyboardButtonData("📁 150 Proxy files", callbackPoolFiles),
			tgbotapi.NewInlineKeyboardButtonData("☠️ Node dead", callbackDead),
		),
		tgbotapi.NewInlineKeyboardRow(
			tgbotapi.NewInlineKeyboardButtonData("🔔 Bật cảnh báo", callbackSubscribe),
			tgbotapi.NewInlineKeyboardButtonData("🔕 Tắt cảnh báo", callbackUnsub),
		),
		tgbotapi.NewInlineKeyboardRow(
			tgbotapi.NewInlineKeyboardButtonData("❓ Trợ giúp", callbackHelp),
		),
	)
}

func backHomeKeyboard() tgbotapi.InlineKeyboardMarkup {
	return tgbotapi.NewInlineKeyboardMarkup(
		tgbotapi.NewInlineKeyboardRow(
			tgbotapi.NewInlineKeyboardButtonData("⬅️ Về bảng điều khiển", callbackHome),
		),
	)
}

func listPageKeyboard(page, totalPages int) tgbotapi.InlineKeyboardMarkup {
	rows := make([][]tgbotapi.InlineKeyboardButton, 0, 2)
	nav := make([]tgbotapi.InlineKeyboardButton, 0, 2)
	if page > 0 {
		nav = append(nav, tgbotapi.NewInlineKeyboardButtonData("◀️ Trước", callbackList+strconv.Itoa(page-1)))
	}
	if page+1 < totalPages {
		nav = append(nav, tgbotapi.NewInlineKeyboardButtonData("▶️ Sau", callbackList+strconv.Itoa(page+1)))
	}
	if len(nav) > 0 {
		rows = append(rows, nav)
	}
	rows = append(rows, []tgbotapi.InlineKeyboardButton{
		tgbotapi.NewInlineKeyboardButtonData("⬅️ Về bảng điều khiển", callbackHome),
	})
	return tgbotapi.InlineKeyboardMarkup{InlineKeyboard: rows}
}

