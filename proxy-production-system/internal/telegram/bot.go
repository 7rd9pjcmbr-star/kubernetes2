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
	"log"
	"strings"
	"time"

	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api/v5"

	"proxy-production-system/internal/store"
)

const botUsername = "TondaithanhBot"

// Config controls @TondaithanhBot integration with MongoDB.
type Config struct {
	Token        string
	AdminChatIDs map[int64]struct{}
	AlertEvery   time.Duration
}

// Bot manages proxy backends in MongoDB via Telegram commands.
type Bot struct {
	api      *tgbotapi.BotAPI
	backends store.BackendRepository
	chats    *store.TelegramChatRepository
	cfg      Config
}

func NewBot(cfg Config, backends store.BackendRepository, chats *store.TelegramChatRepository) (*Bot, error) {
	if strings.TrimSpace(cfg.Token) == "" {
		return nil, fmt.Errorf("telegram bot token is required")
	}
	api, err := tgbotapi.NewBotAPI(cfg.Token)
	if err != nil {
		return nil, fmt.Errorf("init telegram bot: %w", err)
	}
	if cfg.AlertEvery <= 0 {
		cfg.AlertEvery = 30 * time.Second
	}
	return &Bot{
		api:      api,
		backends: backends,
		chats:    chats,
		cfg:      cfg,
	}, nil
}

func (b *Bot) Run(ctx context.Context) error {
	log.Printf("telegram bot @%s connected", botUsername)
	b.setupCommands()

	go b.runAlertMonitor(ctx)

	updates := b.api.GetUpdatesChan(tgbotapi.UpdateConfig{
		Timeout: 30,
	})

	for {
		select {
		case <-ctx.Done():
			return nil
		case update, ok := <-updates:
			if !ok {
				return nil
			}
			if update.CallbackQuery != nil {
				b.handleCallback(ctx, update.CallbackQuery)
				continue
			}
			if update.Message == nil {
				continue
			}
			b.handleMessage(ctx, update.Message)
		}
	}
}

func (b *Bot) handleMessage(ctx context.Context, message *tgbotapi.Message) {
	if !b.authorized(message) {
		b.reply(message.Chat.ID, "Ban khong co quyen dung bot quan tri proxy.")
		return
	}

	text := strings.TrimSpace(message.Text)
	if text == "" {
		return
	}

	switch {
	case text == "/start" || text == "/panel" || text == "🎛 Bảng điều khiển":
		b.showPanel(message.Chat.ID)
	case text == "/help":
		b.sendPanel(message.Chat.ID, helpText(), backHomeKeyboard())
	case text == "📊 Thống kê" || text == "/stats":
		b.sendPanel(message.Chat.ID, b.statsText(ctx), backHomeKeyboard())
	case text == "📋 Danh sách" || text == "/list":
		body, keyboard := b.listPage(ctx, 0)
		b.sendPanel(message.Chat.ID, body, keyboard)
	case text == "/subscribe":
		b.handleSubscribe(ctx, message)
	case text == "/unsubscribe":
		b.handleUnsubscribe(ctx, message)
	case strings.HasPrefix(text, "/add "):
		b.handleAdd(ctx, message.Chat.ID, strings.TrimPrefix(text, "/add "))
	case strings.HasPrefix(text, "/del "):
		b.handleDelete(ctx, message.Chat.ID, strings.TrimSpace(strings.TrimPrefix(text, "/del ")))
	case strings.HasPrefix(text, "/status "):
		b.handleSetStatus(ctx, message.Chat.ID, strings.TrimPrefix(text, "/status "))
	default:
		b.reply(message.Chat.ID, "Lenh khong hop le. Go /panel de mo bang dieu khien.")
	}
}

func (b *Bot) authorized(message *tgbotapi.Message) bool {
	return b.authorizedChat(message.Chat.ID)
}

func (b *Bot) authorizedChat(chatID int64) bool {
	if len(b.cfg.AdminChatIDs) == 0 {
		return true
	}
	_, ok := b.cfg.AdminChatIDs[chatID]
	return ok
}

func (b *Bot) reply(chatID int64, text string) {
	msg := tgbotapi.NewMessage(chatID, text)
	msg.ParseMode = tgbotapi.ModeMarkdown
	if _, err := b.api.Send(msg); err != nil {
		log.Printf("telegram send failed chat=%d err=%v", chatID, err)
	}
}

func (b *Bot) broadcast(ctx context.Context, text string) {
	subscribers, err := b.chats.List(ctx)
	if err != nil {
		log.Printf("list telegram subscribers failed: %v", err)
		return
	}
	for _, subscriber := range subscribers {
		b.reply(subscriber.ChatID, text)
	}
}

func helpText() string {
	return strings.TrimSpace(`
*❓ Trợ giúp @TondaithanhBot*

/panel — mở bảng điều khiển (nút bấm)
/stats — thống kê pool MongoDB
/list — danh sách backend (phân trang)

*Lệnh nâng cao:*
/add ip port type country
/del id
/status id active|dead|testing
/subscribe — bật cảnh báo dead
/unsubscribe — tắt cảnh báo
`)
}
