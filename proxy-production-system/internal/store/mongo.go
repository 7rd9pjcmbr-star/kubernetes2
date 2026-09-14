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
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"

	"proxy-production-system/internal/model"
)

// MongoRepository stores backends in MongoDB for multi-instance gateway sync.
type MongoRepository struct {
	collection *mongo.Collection
}

type MongoConfig struct {
	URI                string
	Database           string
	Collection         string
	TelegramCollection string
}

func NewMongoRepository(ctx context.Context, cfg MongoConfig) (*MongoRepository, error) {
	if cfg.URI == "" {
		return nil, fmt.Errorf("mongo uri is required")
	}
	if cfg.Database == "" {
		cfg.Database = "proxy_gateway"
	}
	if cfg.Collection == "" {
		cfg.Collection = "backends"
	}

	client, err := mongo.Connect(ctx, options.Client().ApplyURI(cfg.URI))
	if err != nil {
		return nil, fmt.Errorf("connect mongo: %w", err)
	}
	if err := client.Ping(ctx, nil); err != nil {
		return nil, fmt.Errorf("ping mongo: %w", err)
	}

	collection := client.Database(cfg.Database).Collection(cfg.Collection)
	_, _ = collection.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "status", Value: 1}, {Key: "success_rate", Value: -1}},
		Options: options.Index().SetName("status_success_rate"),
	})

	return &MongoRepository{collection: collection}, nil
}

func (r *MongoRepository) List(ctx context.Context) ([]model.ProxyBackend, error) {
	cursor, err := r.collection.Find(ctx, bson.M{})
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	backends := make([]model.ProxyBackend, 0)
	for cursor.Next(ctx) {
		var backend model.ProxyBackend
		if err := cursor.Decode(&backend); err != nil {
			return nil, err
		}
		backends = append(backends, backend)
	}
	return backends, cursor.Err()
}

func (r *MongoRepository) Get(ctx context.Context, id string) (model.ProxyBackend, error) {
	var backend model.ProxyBackend
	err := r.collection.FindOne(ctx, bson.M{"_id": id}).Decode(&backend)
	if err == mongo.ErrNoDocuments {
		return model.ProxyBackend{}, ErrNotFound
	}
	if err != nil {
		return model.ProxyBackend{}, err
	}
	return backend, nil
}

func (r *MongoRepository) Create(ctx context.Context, backend *model.ProxyBackend) error {
	now := time.Now()
	backend.Normalize(now)
	if backend.ID == "" {
		backend.ID = primitive.NewObjectID().Hex()
	}
	_, err := r.collection.InsertOne(ctx, backend)
	return err
}

func (r *MongoRepository) Update(ctx context.Context, backend model.ProxyBackend) error {
	backend.Normalize(time.Now())
	result, err := r.collection.ReplaceOne(ctx, bson.M{"_id": backend.ID}, backend)
	if err != nil {
		return err
	}
	if result.MatchedCount == 0 {
		return ErrNotFound
	}
	return nil
}

func (r *MongoRepository) Delete(ctx context.Context, id string) error {
	result, err := r.collection.DeleteOne(ctx, bson.M{"_id": id})
	if err != nil {
		return err
	}
	if result.DeletedCount == 0 {
		return ErrNotFound
	}
	return nil
}

func (r *MongoRepository) SaveMetrics(ctx context.Context, backend model.ProxyBackend) error {
	update := bson.M{
		"$set": bson.M{
			"latency":        backend.Latency,
			"success_rate":   backend.SuccessRate,
			"total_requests": backend.TotalRequests,
			"status":         backend.Status,
			"last_checked":   backend.LastChecked,
		},
	}
	result, err := r.collection.UpdateByID(ctx, backend.ID, update)
	if err != nil {
		return err
	}
	if result.MatchedCount == 0 {
		return ErrNotFound
	}
	return nil
}
