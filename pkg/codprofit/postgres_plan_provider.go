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

package codprofit

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
)

type PostgresWorkspacePlanProvider struct {
	db DBTX
}

func NewPostgresWorkspacePlanProvider(db DBTX) *PostgresWorkspacePlanProvider {
	return &PostgresWorkspacePlanProvider{db: db}
}

func (p *PostgresWorkspacePlanProvider) GetPlan(ctx context.Context, workspaceID string) (string, error) {
	query := `SELECT plan FROM codprofit_workspaces WHERE id = $1`
	var plan string
	err := p.db.QueryRowContext(ctx, query, workspaceID).Scan(&plan)
	if errors.Is(err, sql.ErrNoRows) {
		return "", fmt.Errorf("workspace %q not found", workspaceID)
	}
	if err != nil {
		return "", fmt.Errorf("query workspace plan: %w", err)
	}
	return plan, nil
}
