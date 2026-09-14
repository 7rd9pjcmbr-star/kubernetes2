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
	Token           string
	AdminChatIDs    map[int64]struct{}
	AlertEvery      time.Duration
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
	case text == "/start" || text == "/help":
		b.reply(message.Chat.ID, helpText())
	case text == "/subscribe":
		b.handleSubscribe(ctx, message)
	case text == "/unsubscribe":
		b.handleUnsubscribe(ctx, message)
	case text == "/list":
		b.handleList(ctx, message.Chat.ID)
	case text == "/stats":
		b.handleStats(ctx, message.Chat.ID)
	case text == "/poolfiles":
		b.handlePoolFiles(message.Chat.ID)
	case strings.HasPrefix(text, "/add "):
		b.handleAdd(ctx, message.Chat.ID, strings.TrimPrefix(text, "/add "))
	case strings.HasPrefix(text, "/del "):
		b.handleDelete(ctx, message.Chat.ID, strings.TrimSpace(strings.TrimPrefix(text, "/del ")))
	case strings.HasPrefix(text, "/status "):
		b.handleSetStatus(ctx, message.Chat.ID, strings.TrimPrefix(text, "/status "))
	default:
		b.reply(message.Chat.ID, "Lenh khong hop le. Go /help de xem danh sach.")
	}
}

func (b *Bot) authorized(message *tgbotapi.Message) bool {
	if len(b.cfg.AdminChatIDs) == 0 {
		return true
	}
	if _, ok := b.cfg.AdminChatIDs[message.Chat.ID]; ok {
		return true
	}
	if message.From != nil && message.From.UserName == botUsername {
		return true
	}
	return false
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
*@TondaithanhBot* — quan tri proxy pool (MongoDB)

/subscribe — nhan canh bao node dead
/unsubscribe — tat canh bao
/list — danh sach backend
/stats — thong ke pool
/poolfiles — dem 150 proxy trong 2 file data
/add ip port type country — them node (vd: /add 203.0.113.1 3128 4g VN)
/del id — xoa backend
/status id active|dead|testing — doi trang thai
`)
}
