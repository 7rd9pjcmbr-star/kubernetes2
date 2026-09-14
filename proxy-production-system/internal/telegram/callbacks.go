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
	"context"
	"fmt"
	"strconv"
	"strings"

	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api/v5"

	"proxy-production-system/internal/model"
)

func (b *Bot) handleCallback(ctx context.Context, query *tgbotapi.CallbackQuery) {
	if query.Message == nil {
		return
	}
	chatID := query.Message.Chat.ID
	if !b.authorizedChat(chatID) {
		b.answerCallback(query.ID, "Không có quyền truy cập.")
		return
	}

	data := strings.TrimSpace(query.Data)
	switch {
	case data == callbackHome:
		b.sendPanel(chatID, mainPanelText(), mainPanelKeyboard())
	case data == callbackStats:
		text := b.statsText(ctx)
		b.editPanel(chatID, query.Message.MessageID, text, backHomeKeyboard())
	case data == callbackPoolFiles:
		text := b.poolFilesText()
		b.editPanel(chatID, query.Message.MessageID, text, backHomeKeyboard())
	case data == callbackSubscribe:
		b.handleSubscribeCallback(ctx, query)
	case data == callbackUnsub:
		b.handleUnsubscribeCallback(ctx, query)
	case data == callbackDead:
		text := b.deadBackendsText(ctx)
		b.editPanel(chatID, query.Message.MessageID, text, backHomeKeyboard())
	case data == callbackHelp:
		b.editPanel(chatID, query.Message.MessageID, helpText(), backHomeKeyboard())
	case strings.HasPrefix(data, callbackList):
		page, _ := strconv.Atoi(strings.TrimPrefix(data, callbackList))
		text, keyboard := b.listPage(ctx, page)
		b.editPanel(chatID, query.Message.MessageID, text, keyboard)
	default:
		b.answerCallback(query.ID, "Nút không hợp lệ.")
		return
	}
	b.answerCallback(query.ID, "")
}

func (b *Bot) handleSubscribeCallback(ctx context.Context, query *tgbotapi.CallbackQuery) {
	message := query.Message
	fake := &tgbotapi.Message{
		Chat: message.Chat,
		From: query.From,
	}
	b.handleSubscribe(ctx, fake)
	b.answerCallback(query.ID, "Đã bật cảnh báo.")
}

func (b *Bot) handleUnsubscribeCallback(ctx context.Context, query *tgbotapi.CallbackQuery) {
	message := query.Message
	fake := &tgbotapi.Message{Chat: message.Chat}
	b.handleUnsubscribe(ctx, fake)
	b.answerCallback(query.ID, "Đã tắt cảnh báo.")
}

func (b *Bot) statsText(ctx context.Context) string {
	backends, err := b.backends.List(ctx)
	if err != nil {
		return fmt.Sprintf("Lỗi MongoDB: %v", err)
	}
	active, dead, testing := 0, 0, 0
	totalLatency := 0
	for _, backend := range backends {
		switch backend.Status {
		case model.BackendStatusDead:
			dead++
		case model.BackendStatusTesting:
			testing++
		default:
			active++
		}
		totalLatency += backend.Latency
	}
	avgLatency := 0
	if len(backends) > 0 {
		avgLatency = totalLatency / len(backends)
	}
	return fmt.Sprintf(
		"*📊 Thống kê pool*\n\nTotal: *%d*\n✅ Active: *%d*\n🔄 Testing: *%d*\n☠️ Dead: *%d*\n⚡ Avg latency: *%dms*",
		len(backends), active, testing, dead, avgLatency,
	)
}

func (b *Bot) poolFilesText() string {
	const (
		hcmFile = "data/proxy-pool-vn-hcm.txt"
		hnFile  = "data/proxy-pool-vn-hn.txt"
	)
	hcmCount, err := countPoolFileLines(hcmFile)
	if err != nil {
		return fmt.Sprintf("Lỗi đọc %s: %v", hcmFile, err)
	}
	hnCount, err := countPoolFileLines(hnFile)
	if err != nil {
		return fmt.Sprintf("Lỗi đọc %s: %v", hnFile, err)
	}
	return fmt.Sprintf(
		"*📁 Proxy pool files*\n\n🇻🇳 HCM (4G): *%d*\n🇻🇳 HN (residential): *%d*\n\n📦 Tổng: *%d* proxy",
		hcmCount, hnCount, hcmCount+hnCount,
	)
}

func (b *Bot) deadBackendsText(ctx context.Context) string {
	backends, err := b.backends.List(ctx)
	if err != nil {
		return fmt.Sprintf("Lỗi MongoDB: %v", err)
	}
	dead := make([]model.ProxyBackend, 0)
	for _, backend := range backends {
		if backend.Status == model.BackendStatusDead {
			dead = append(dead, backend)
		}
	}
	if len(dead) == 0 {
		return "*☠️ Node dead*\n\nKhông có backend dead. Pool ổn định ✅"
	}
	lines := []string{fmt.Sprintf("*☠️ Node dead* (%d)", len(dead))}
	for i, backend := range dead {
		if i >= 10 {
			lines = append(lines, fmt.Sprintf("... và %d node khác", len(dead)-10))
			break
		}
		lines = append(lines, formatBackendLine(backend))
	}
	return strings.Join(lines, "\n")
}

func (b *Bot) listPage(ctx context.Context, page int) (string, tgbotapi.InlineKeyboardMarkup) {
	backends, err := b.backends.List(ctx)
	if err != nil {
		return fmt.Sprintf("Lỗi MongoDB: %v", err), backHomeKeyboard()
	}
	if len(backends) == 0 {
		return "*📋 Danh sách backend*\n\nPool trống.", backHomeKeyboard()
	}
	if page < 0 {
		page = 0
	}
	totalPages := (len(backends) + listPageSize - 1) / listPageSize
	if page >= totalPages {
		page = totalPages - 1
	}
	start := page * listPageSize
	end := start + listPageSize
	if end > len(backends) {
		end = len(backends)
	}

	lines := []string{
		fmt.Sprintf("*📋 Danh sách backend* — trang %d/%d", page+1, totalPages),
		fmt.Sprintf("_Hiển thị %d–%d / %d_\n", start+1, end, len(backends)),
	}
	for _, backend := range backends[start:end] {
		lines = append(lines, formatBackendLine(backend))
	}
	return strings.Join(lines, "\n"), listPageKeyboard(page, totalPages)
}

