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
	"encoding/json"
	"errors"
	"fmt"
	"strings"
)

type DBTX interface {
	QueryRowContext(ctx context.Context, query string, args ...interface{}) *sql.Row
	ExecContext(ctx context.Context, query string, args ...interface{}) (sql.Result, error)
}

type PostgresAnalysisRepository struct {
	db DBTX
}

func NewPostgresAnalysisRepository(db DBTX) *PostgresAnalysisRepository {
	return &PostgresAnalysisRepository{db: db}
}

func (r *PostgresAnalysisRepository) Create(ctx context.Context, record *AnalysisRecord) error {
	inputJSON, err := json.Marshal(record.Input)
	if err != nil {
		return fmt.Errorf("marshal input: %w", err)
	}
	outputJSON, err := json.Marshal(record.Output)
	if err != nil {
		return fmt.Errorf("marshal output: %w", err)
	}

	query := `
INSERT INTO codprofit_analyses (id, workspace_id, created_by, input_json, output_json, created_at)
VALUES ($1, $2, $3, $4, $5, $6)
`
	_, err = r.db.ExecContext(ctx, query, record.ID, record.WorkspaceID, record.CreatedBy, inputJSON, outputJSON, record.CreatedAt)
	if err != nil {
		return fmt.Errorf("insert analysis: %w", err)
	}
	return nil
}

func (r *PostgresAnalysisRepository) GetByID(ctx context.Context, analysisID, workspaceID string) (*AnalysisRecord, error) {
	query := `
SELECT id, workspace_id, created_by, input_json, output_json, created_at
FROM codprofit_analyses
WHERE id = $1 AND workspace_id = $2
`
	row := r.db.QueryRowContext(ctx, query, analysisID, workspaceID)
	record := &AnalysisRecord{}
	var inputJSON []byte
	var outputJSON []byte
	if err := row.Scan(&record.ID, &record.WorkspaceID, &record.CreatedBy, &inputJSON, &outputJSON, &record.CreatedAt); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, nil
		}
		return nil, fmt.Errorf("scan analysis: %w", err)
	}
	if err := json.Unmarshal(inputJSON, &record.Input); err != nil {
		return nil, fmt.Errorf("unmarshal input: %w", err)
	}
	if err := json.Unmarshal(outputJSON, &record.Output); err != nil {
		return nil, fmt.Errorf("unmarshal output: %w", err)
	}
	return record, nil
}

type PostgresBenchmarkRepository struct {
	db DBTX
}

func NewPostgresBenchmarkRepository(db DBTX) *PostgresBenchmarkRepository {
	return &PostgresBenchmarkRepository{db: db}
}

func (r *PostgresBenchmarkRepository) GetAggregate(ctx context.Context, category string, provinces []string) (*BenchmarkAggregate, error) {
	if len(provinces) == 0 {
		return nil, errors.New("provinces cannot be empty")
	}
	placeholders := make([]string, 0, len(provinces))
	args := make([]interface{}, 0, len(provinces)+1)
	args = append(args, category)
	for i, code := range provinces {
		placeholders = append(placeholders, fmt.Sprintf("$%d", i+2))
		args = append(args, code)
	}
	query := fmt.Sprintf(`
SELECT
	COALESCE(AVG(baseline_return_rate_pct), 0),
	COALESCE(AVG(carrier_delay_score), 0),
	COALESCE(AVG(price_band_risk_score), 0)
FROM codprofit_benchmarks
WHERE category = $1 AND province_code IN (%s)
`, strings.Join(placeholders, ", "))

	var aggregate BenchmarkAggregate
	if err := r.db.QueryRowContext(ctx, query, args...).Scan(&aggregate.BaselineReturnRatePct, &aggregate.CarrierDelayScore, &aggregate.PriceBandRiskScore); err != nil {
		return nil, fmt.Errorf("query benchmark aggregate: %w", err)
	}
	return &aggregate, nil
}

type PostgresUsageRepository struct {
	db DBTX
}

func NewPostgresUsageRepository(db DBTX) *PostgresUsageRepository {
	return &PostgresUsageRepository{db: db}
}

func (r *PostgresUsageRepository) GetMonthly(ctx context.Context, workspaceID, monthKey string) (*MonthlyUsage, error) {
	query := `
SELECT analyses_count, exports_count
FROM codprofit_usage_monthly
WHERE workspace_id = $1 AND month_key = $2
`
	var usage MonthlyUsage
	err := r.db.QueryRowContext(ctx, query, workspaceID, monthKey).Scan(&usage.AnalysesCount, &usage.ExportsCount)
	if errors.Is(err, sql.ErrNoRows) {
		return &MonthlyUsage{}, nil
	}
	if err != nil {
		return nil, fmt.Errorf("query usage: %w", err)
	}
	return &usage, nil
}

func (r *PostgresUsageRepository) IncrementAnalyses(ctx context.Context, workspaceID, monthKey string, delta int) error {
	query := `
INSERT INTO codprofit_usage_monthly (workspace_id, month_key, analyses_count, exports_count)
VALUES ($1, $2, $3, 0)
ON CONFLICT (workspace_id, month_key)
DO UPDATE SET analyses_count = codprofit_usage_monthly.analyses_count + EXCLUDED.analyses_count
`
	_, err := r.db.ExecContext(ctx, query, workspaceID, monthKey, delta)
	if err != nil {
		return fmt.Errorf("increment analyses usage: %w", err)
	}
	return nil
}
