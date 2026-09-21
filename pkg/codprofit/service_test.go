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
	"testing"
	"time"
)

func TestServiceCreateAnalysis(t *testing.T) {
	svc := buildServiceForTest("free", MonthlyUsage{AnalysesCount: 1}, nil)
	req := CreateAnalysisRequest{
		WorkspaceID: "ws-1",
		UserID:      "u-1",
		Input:       validInput(),
	}
	record, err := svc.CreateAnalysis(context.Background(), req)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if record.ID == "" {
		t.Fatalf("expected generated ID")
	}
}

func TestServicePlanLimit(t *testing.T) {
	svc := buildServiceForTest("free", MonthlyUsage{AnalysesCount: 20}, nil)
	_, err := svc.CreateAnalysis(context.Background(), CreateAnalysisRequest{
		WorkspaceID: "ws-1",
		UserID:      "u-1",
		Input:       validInput(),
	})
	if !errors.Is(err, ErrPlanLimit) {
		t.Fatalf("expected plan limit, got %v", err)
	}
}

func TestServiceGetAnalysisNotFound(t *testing.T) {
	svc := buildServiceForTest("free", MonthlyUsage{}, nil)
	_, err := svc.GetAnalysis(context.Background(), "ws-1", "missing")
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("expected not found, got %v", err)
	}
}

func TestServiceExportAnalysis(t *testing.T) {
	svc := buildServiceForTest("growth", MonthlyUsage{AnalysesCount: 1}, nil)
	_, err := svc.CreateAnalysis(context.Background(), CreateAnalysisRequest{
		WorkspaceID: "ws-1",
		UserID:      "u-1",
		Input:       validInput(),
	})
	if err != nil {
		t.Fatalf("create analysis failed: %v", err)
	}

	artifact, err := svc.ExportAnalysis(context.Background(), ExportAnalysisRequest{
		WorkspaceID: "ws-1",
		AnalysisID:  "anl_123",
		Format:      "csv",
	})
	if err != nil {
		t.Fatalf("unexpected export error: %v", err)
	}
	if artifact.FileName != "anl_123.csv" {
		t.Fatalf("unexpected file name: %s", artifact.FileName)
	}
}

func TestServiceExportAnalysisBlockedByPlan(t *testing.T) {
	svc := buildServiceForTest("free", MonthlyUsage{AnalysesCount: 1}, nil)
	_, err := svc.ExportAnalysis(context.Background(), ExportAnalysisRequest{
		WorkspaceID: "ws-1",
		AnalysisID:  "anl_123",
		Format:      "csv",
	})
	if !errors.Is(err, ErrExportNotAllowed) {
		t.Fatalf("expected export blocked, got %v", err)
	}
}

type fakeAnalysisRepo struct {
	data      map[string]*AnalysisRecord
	createErr error
}

func (f *fakeAnalysisRepo) Create(_ context.Context, a *AnalysisRecord) error {
	if f.createErr != nil {
		return f.createErr
	}
	if f.data == nil {
		f.data = map[string]*AnalysisRecord{}
	}
	f.data[a.ID] = a
	return nil
}

func (f *fakeAnalysisRepo) GetByID(_ context.Context, analysisID, workspaceID string) (*AnalysisRecord, error) {
	record := f.data[analysisID]
	if record == nil || record.WorkspaceID != workspaceID {
		return nil, nil
	}
	return record, nil
}

type fakeBenchmarkRepo struct {
	aggregate *BenchmarkAggregate
}

func (f *fakeBenchmarkRepo) GetAggregate(_ context.Context, _ string, _ []string) (*BenchmarkAggregate, error) {
	return f.aggregate, nil
}

type fakeUsageRepo struct {
	usage MonthlyUsage
}

func (f *fakeUsageRepo) GetMonthly(_ context.Context, _, _ string) (*MonthlyUsage, error) {
	copy := f.usage
	return &copy, nil
}

func (f *fakeUsageRepo) IncrementAnalyses(_ context.Context, _, _ string, _ int) error {
	return nil
}

func (f *fakeUsageRepo) IncrementExports(_ context.Context, _, _ string, _ int) error {
	return nil
}

type fakePlanProvider struct{ plan string }

func (f fakePlanProvider) GetPlan(_ context.Context, _ string) (string, error) {
	return f.plan, nil
}

type fakeIDGen struct{}

func (fakeIDGen) NewID(prefix string) string {
	return prefix + "_123"
}

type fakeClock struct{}

func (fakeClock) Now() time.Time {
	return time.Date(2026, 7, 5, 10, 0, 0, 0, time.UTC)
}

func buildServiceForTest(plan string, usage MonthlyUsage, createErr error) *Service {
	return NewService(
		&fakeAnalysisRepo{createErr: createErr},
		&fakeBenchmarkRepo{
			aggregate: &BenchmarkAggregate{
				BaselineReturnRatePct: 10,
				CarrierDelayScore:     20,
				PriceBandRiskScore:    35,
			},
		},
		&fakeUsageRepo{usage: usage},
		fakePlanProvider{plan: plan},
		fakeIDGen{},
		fakeClock{},
		DefaultRuleConfig(),
	)
}
