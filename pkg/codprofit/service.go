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
	"errors"
	"fmt"
	"time"
)

var (
	ErrNotFound  = errors.New("analysis not found")
	ErrPlanLimit = errors.New("plan limit reached")
)

type AnalysisRepository interface {
	Create(ctx context.Context, a *AnalysisRecord) error
	GetByID(ctx context.Context, analysisID, workspaceID string) (*AnalysisRecord, error)
}

type BenchmarkRepository interface {
	GetAggregate(ctx context.Context, category string, provinces []string) (*BenchmarkAggregate, error)
}

type UsageRepository interface {
	GetMonthly(ctx context.Context, workspaceID, monthKey string) (*MonthlyUsage, error)
	IncrementAnalyses(ctx context.Context, workspaceID, monthKey string, delta int) error
}

type WorkspacePlanProvider interface {
	GetPlan(ctx context.Context, workspaceID string) (string, error)
}

type IDGenerator interface {
	NewID(prefix string) string
}

type Clock interface {
	Now() time.Time
}

type Service struct {
	analysisRepo  AnalysisRepository
	benchmarkRepo BenchmarkRepository
	usageRepo     UsageRepository
	planProvider  WorkspacePlanProvider
	idGen         IDGenerator
	clock         Clock
	rules         RuleConfig
}

func NewService(
	analysisRepo AnalysisRepository,
	benchmarkRepo BenchmarkRepository,
	usageRepo UsageRepository,
	planProvider WorkspacePlanProvider,
	idGen IDGenerator,
	clock Clock,
	rules RuleConfig,
) *Service {
	return &Service{
		analysisRepo:  analysisRepo,
		benchmarkRepo: benchmarkRepo,
		usageRepo:     usageRepo,
		planProvider:  planProvider,
		idGen:         idGen,
		clock:         clock,
		rules:         rules,
	}
}

type CreateAnalysisRequest struct {
	WorkspaceID string
	UserID      string
	Input       Input
}

func (s *Service) CreateAnalysis(ctx context.Context, req CreateAnalysisRequest) (*AnalysisRecord, error) {
	plan, err := s.planProvider.GetPlan(ctx, req.WorkspaceID)
	if err != nil {
		return nil, fmt.Errorf("get plan: %w", err)
	}
	monthKey := s.clock.Now().Format("2006-01")
	usage, err := s.usageRepo.GetMonthly(ctx, req.WorkspaceID, monthKey)
	if err != nil {
		return nil, fmt.Errorf("get usage: %w", err)
	}
	if usage.AnalysesCount >= analysesLimit(plan) {
		return nil, ErrPlanLimit
	}
	bm, err := s.benchmarkRepo.GetAggregate(ctx, string(req.Input.Product.Category), req.Input.Market.PrimaryProvinces)
	if err != nil {
		return nil, fmt.Errorf("get benchmark: %w", err)
	}
	out, err := Calculate(req.Input, *bm, s.rules)
	if err != nil {
		return nil, err
	}
	record := &AnalysisRecord{
		ID:          s.idGen.NewID("anl"),
		WorkspaceID: req.WorkspaceID,
		CreatedBy:   req.UserID,
		Input:       req.Input,
		Output:      out,
		CreatedAt:   s.clock.Now(),
	}
	if err := s.analysisRepo.Create(ctx, record); err != nil {
		return nil, fmt.Errorf("create analysis: %w", err)
	}
	if err := s.usageRepo.IncrementAnalyses(ctx, req.WorkspaceID, monthKey, 1); err != nil {
		return nil, fmt.Errorf("increment usage: %w", err)
	}
	return record, nil
}

func (s *Service) GetAnalysis(ctx context.Context, workspaceID, analysisID string) (*AnalysisRecord, error) {
	record, err := s.analysisRepo.GetByID(ctx, analysisID, workspaceID)
	if err != nil {
		return nil, err
	}
	if record == nil {
		return nil, ErrNotFound
	}
	return record, nil
}

func analysesLimit(plan string) int {
	switch plan {
	case "free":
		return 20
	case "starter":
		return 300
	case "growth":
		return 2000
	case "team":
		return 10000
	default:
		return 20
	}
}
