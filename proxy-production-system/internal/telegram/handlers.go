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
	"os"
	"strconv"
	"strings"

	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api/v5"

	"proxy-production-system/internal/model"
	"proxy-production-system/internal/store"
)

func (b *Bot) handleSubscribe(ctx context.Context, message *tgbotapi.Message) {
	username := ""
	displayName := message.Chat.Title
	if message.From != nil {
		username = message.From.UserName
		if displayName == "" {
			displayName = strings.TrimSpace(message.From.FirstName + " " + message.From.LastName)
		}
	}
	chat := model.TelegramChat{
		ChatID:      message.Chat.ID,
		Username:    username,
		DisplayName: displayName,
	}
	if err := b.chats.Subscribe(ctx, chat); err != nil {
		b.reply(message.Chat.ID, fmt.Sprintf("Loi subscribe: %v", err))
		return
	}
	b.reply(message.Chat.ID, "Da dang ky nhan canh bao proxy tu MongoDB.")
}

func (b *Bot) handleUnsubscribe(ctx context.Context, message *tgbotapi.Message) {
	if err := b.chats.Unsubscribe(ctx, message.Chat.ID); err != nil {
		if err == store.ErrNotFound {
			b.reply(message.Chat.ID, "Chat nay chua subscribe.")
			return
		}
		b.reply(message.Chat.ID, fmt.Sprintf("Loi unsubscribe: %v", err))
		return
	}
	b.reply(message.Chat.ID, "Da huy nhan canh bao.")
}

func (b *Bot) handleList(ctx context.Context, chatID int64) {
	backends, err := b.backends.List(ctx)
	if err != nil {
		b.reply(chatID, fmt.Sprintf("Loi doc MongoDB: %v", err))
		return
	}
	if len(backends) == 0 {
		b.reply(chatID, "Pool trong. Dung /add de them backend.")
		return
	}

	var lines []string
	lines = append(lines, fmt.Sprintf("*Backend pool* (%d)", len(backends)))
	for _, backend := range backends {
		lines = append(lines, formatBackendLine(backend))
	}
	b.reply(chatID, strings.Join(lines, "\n"))
}

func (b *Bot) handlePoolFiles(chatID int64) {
	const (
		hcmFile = "data/proxy-pool-vn-hcm.txt"
		hnFile  = "data/proxy-pool-vn-hn.txt"
	)
	hcmCount, err := countPoolFileLines(hcmFile)
	if err != nil {
		b.reply(chatID, fmt.Sprintf("Loi doc %s: %v", hcmFile, err))
		return
	}
	hnCount, err := countPoolFileLines(hnFile)
	if err != nil {
		b.reply(chatID, fmt.Sprintf("Loi doc %s: %v", hnFile, err))
		return
	}
	b.reply(chatID, fmt.Sprintf(
		"*Proxy pool files*\n%s: %d\n%s: %d\nTong: %d",
		hcmFile, hcmCount, hnFile, hnCount, hcmCount+hnCount,
	))
}

func countPoolFileLines(path string) (int, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return 0, err
	}
	count := 0
	for _, line := range strings.Split(string(content), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		count++
	}
	return count, nil
}

func (b *Bot) handleStats(ctx context.Context, chatID int64) {
	backends, err := b.backends.List(ctx)
	if err != nil {
		b.reply(chatID, fmt.Sprintf("Loi doc MongoDB: %v", err))
		return
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

	text := fmt.Sprintf(
		"*Pool stats*\nTotal: %d\nActive: %d\nTesting: %d\nDead: %d\nAvg latency: %dms",
		len(backends), active, testing, dead, avgLatency,
	)
	b.reply(chatID, text)
}

func (b *Bot) handleAdd(ctx context.Context, chatID int64, args string) {
	parts := strings.Fields(args)
	if len(parts) < 2 {
		b.reply(chatID, "Cu phap: /add ip port [type] [country]\nVi du: /add 203.0.113.1 3128 4g VN")
		return
	}

	port, err := strconv.Atoi(parts[1])
	if err != nil {
		b.reply(chatID, "Port khong hop le.")
		return
	}

	backend := model.ProxyBackend{
		IP:          parts[0],
		Port:        port,
		Type:        model.BackendType4G,
		Country:     "VN",
		Anonymity:   model.AnonymityElite,
		Status:      model.BackendStatusActive,
		SuccessRate: 100,
	}
	if len(parts) >= 3 {
		backend.Type = parts[2]
	}
	if len(parts) >= 4 {
		backend.Country = parts[3]
	}

	if err := b.backends.Create(ctx, &backend); err != nil {
		b.reply(chatID, fmt.Sprintf("Loi them backend: %v", err))
		return
	}
	b.reply(chatID, fmt.Sprintf("Da them backend vao MongoDB:\n%s", formatBackendLine(backend)))
}

func (b *Bot) handleDelete(ctx context.Context, chatID int64, id string) {
	if id == "" {
		b.reply(chatID, "Cu phap: /del backend_id")
		return
	}
	if err := b.backends.Delete(ctx, id); err != nil {
		if err == store.ErrNotFound {
			b.reply(chatID, "Khong tim thay backend.")
			return
		}
		b.reply(chatID, fmt.Sprintf("Loi xoa: %v", err))
		return
	}
	b.reply(chatID, fmt.Sprintf("Da xoa backend `%s` khoi MongoDB.", id))
}

func (b *Bot) handleSetStatus(ctx context.Context, chatID int64, args string) {
	parts := strings.Fields(args)
	if len(parts) != 2 {
		b.reply(chatID, "Cu phap: /status id active|dead|testing")
		return
	}

	backend, err := b.backends.Get(ctx, parts[0])
	if err != nil {
		if err == store.ErrNotFound {
			b.reply(chatID, "Khong tim thay backend.")
			return
		}
		b.reply(chatID, fmt.Sprintf("Loi doc backend: %v", err))
		return
	}

	switch strings.ToLower(parts[1]) {
	case model.BackendStatusActive, model.BackendStatusDead, model.BackendStatusTesting:
		backend.Status = strings.ToLower(parts[1])
	default:
		b.reply(chatID, "Status phai la active, dead hoac testing.")
		return
	}

	if err := b.backends.Update(ctx, backend); err != nil {
		b.reply(chatID, fmt.Sprintf("Loi cap nhat: %v", err))
		return
	}
	b.reply(chatID, fmt.Sprintf("Da cap nhat:\n%s", formatBackendLine(backend)))
}

func formatBackendLine(backend model.ProxyBackend) string {
	return fmt.Sprintf(
		"`%s` %s:%d | %s | %s | %dms | %.1f%% | score %.1f",
		shortID(backend.ID),
		backend.IP,
		backend.Port,
		backend.Type,
		backend.Status,
		backend.Latency,
		backend.SuccessRate,
		backend.QualityScore(),
	)
}

func shortID(id string) string {
	if len(id) <= 8 {
		return id
	}
	return id[:8]
}
