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

package model

import "time"

// TelegramChat stores alert subscribers for @TondaithanhBot in MongoDB.
type TelegramChat struct {
	ID           string    `bson:"_id" json:"id"`
	ChatID       int64     `bson:"chat_id" json:"chat_id"`
	Username     string    `bson:"username" json:"username"`
	DisplayName  string    `bson:"display_name" json:"display_name"`
	SubscribedAt time.Time `bson:"subscribed_at" json:"subscribed_at"`
}
