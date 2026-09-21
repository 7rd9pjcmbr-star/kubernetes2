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

package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"proxy-production-system/internal/store"
	"proxy-production-system/internal/telegram"
)

func main() {
	token := strings.TrimSpace(os.Getenv("TELEGRAM_BOT_TOKEN"))
	if token == "" {
		log.Fatal("TELEGRAM_BOT_TOKEN is required for @TondaithanhBot")
	}

	mongoURI := strings.TrimSpace(os.Getenv("MONGO_URI"))
	if mongoURI == "" {
		log.Fatal("MONGO_URI is required — bot reads/writes proxy backends in MongoDB")
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	mongoCfg := store.MongoConfig{
		URI:                mongoURI,
		Database:           envOr("MONGO_DATABASE", "proxy_gateway"),
		Collection:         envOr("MONGO_COLLECTION", "backends"),
		TelegramCollection: envOr("MONGO_TELEGRAM_COLLECTION", "telegram_chats"),
	}

	backends, err := store.NewMongoRepository(ctx, mongoCfg)
	if err != nil {
		log.Fatalf("failed to open backend repository: %v", err)
	}
	chats, err := store.NewTelegramChatRepository(ctx, mongoCfg)
	if err != nil {
		log.Fatalf("failed to open telegram chat repository: %v", err)
	}

	bot, err := telegram.NewBot(telegram.Config{
		Token:        token,
		AdminChatIDs: parseChatIDs(os.Getenv("TELEGRAM_ADMIN_CHAT_IDS")),
		AlertEvery:   parseDuration(os.Getenv("TELEGRAM_ALERT_INTERVAL"), 30*time.Second),
	}, backends, chats)
	if err != nil {
		log.Fatalf("failed to start @TondaithanhBot: %v", err)
	}

	go func() {
		signals := make(chan os.Signal, 1)
		signal.Notify(signals, syscall.SIGINT, syscall.SIGTERM)
		<-signals
		cancel()
	}()

	log.Println("@TondaithanhBot running — MongoDB backend control plane active")
	if err := bot.Run(ctx); err != nil {
		log.Fatalf("bot stopped with error: %v", err)
	}
}

func envOr(key, fallback string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	return value
}

func parseChatIDs(raw string) map[int64]struct{} {
	allowed := make(map[int64]struct{})
	for _, part := range strings.Split(raw, ",") {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		chatID, err := strconv.ParseInt(part, 10, 64)
		if err != nil {
			continue
		}
		allowed[chatID] = struct{}{}
	}
	return allowed
}

func parseDuration(raw string, fallback time.Duration) time.Duration {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return fallback
	}
	value, err := time.ParseDuration(raw)
	if err != nil || value <= 0 {
		return fallback
	}
	return value
}
