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

package store

import (
	"context"
	"fmt"
	"strconv"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"

	"proxy-production-system/internal/model"
)

const defaultTelegramCollection = "telegram_chats"

// TelegramChatRepository persists @TondaithanhBot subscribers in MongoDB.
type TelegramChatRepository struct {
	collection *mongo.Collection
}

func NewTelegramChatRepository(ctx context.Context, cfg MongoConfig) (*TelegramChatRepository, error) {
	if cfg.URI == "" {
		return nil, fmt.Errorf("mongo uri is required")
	}
	if cfg.Database == "" {
		cfg.Database = "proxy_gateway"
	}
	collectionName := cfg.TelegramCollection
	if collectionName == "" {
		collectionName = defaultTelegramCollection
	}

	client, err := mongo.Connect(ctx, options.Client().ApplyURI(cfg.URI))
	if err != nil {
		return nil, fmt.Errorf("connect mongo: %w", err)
	}
	if err := client.Ping(ctx, nil); err != nil {
		return nil, fmt.Errorf("ping mongo: %w", err)
	}

	collection := client.Database(cfg.Database).Collection(collectionName)
	return &TelegramChatRepository{collection: collection}, nil
}

func (r *TelegramChatRepository) Subscribe(ctx context.Context, chat model.TelegramChat) error {
	chat.SubscribedAt = time.Now()
	if chat.ID == "" {
		chat.ID = strconv.FormatInt(chat.ChatID, 10)
	}
	opts := options.Replace().SetUpsert(true)
	_, err := r.collection.ReplaceOne(ctx, bson.M{"_id": chat.ID}, chat, opts)
	return err
}

func (r *TelegramChatRepository) Unsubscribe(ctx context.Context, chatID int64) error {
	result, err := r.collection.DeleteOne(ctx, bson.M{"chat_id": chatID})
	if err != nil {
		return err
	}
	if result.DeletedCount == 0 {
		return ErrNotFound
	}
	return nil
}

func (r *TelegramChatRepository) List(ctx context.Context) ([]model.TelegramChat, error) {
	cursor, err := r.collection.Find(ctx, bson.M{})
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	chats := make([]model.TelegramChat, 0)
	for cursor.Next(ctx) {
		var chat model.TelegramChat
		if err := cursor.Decode(&chat); err != nil {
			return nil, err
		}
		chats = append(chats, chat)
	}
	return chats, cursor.Err()
}
