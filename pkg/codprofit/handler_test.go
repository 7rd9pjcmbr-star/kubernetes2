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
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

type fakeService struct {
	createFn func(ctx context.Context, req CreateAnalysisRequest) (*AnalysisRecord, error)
	getFn    func(ctx context.Context, workspaceID, analysisID string) (*AnalysisRecord, error)
	exportFn func(ctx context.Context, req ExportAnalysisRequest) (*ExportArtifact, error)
}

func (f fakeService) CreateAnalysis(ctx context.Context, req CreateAnalysisRequest) (*AnalysisRecord, error) {
	return f.createFn(ctx, req)
}

func (f fakeService) GetAnalysis(ctx context.Context, workspaceID, analysisID string) (*AnalysisRecord, error) {
	return f.getFn(ctx, workspaceID, analysisID)
}

func (f fakeService) ExportAnalysis(ctx context.Context, req ExportAnalysisRequest) (*ExportArtifact, error) {
	return f.exportFn(ctx, req)
}

func TestCreateCodProfitAnalysis201(t *testing.T) {
	handler := NewAnalysisHandler(fakeService{
		createFn: func(_ context.Context, req CreateAnalysisRequest) (*AnalysisRecord, error) {
			return &AnalysisRecord{
				ID:          "anl_1",
				WorkspaceID: req.WorkspaceID,
				CreatedBy:   req.UserID,
				Input:       req.Input,
				Output: Output{
					Risk: RiskResult{Score: 50, Level: "medium"},
					Profit: ProfitResult{
						NetProfitPerOrder: 10000,
						BreakEvenCPA:      60000,
						Currency:          "VND",
					},
					Decision: Decision{Status: "caution", Message: "ok"},
				},
				CreatedAt: time.Date(2026, 7, 5, 10, 0, 0, 0, time.UTC),
			}, nil
		},
		getFn: nil,
	})

	body := map[string]interface{}{
		"workspaceId": "ws-1",
		"mode":        "quick",
		"product": map[string]interface{}{
			"name":         "Kem",
			"category":     "beauty",
			"sellingPrice": 299000,
			"cogs":         115000,
		},
		"costs": map[string]interface{}{
			"platformFeePct": 8,
			"paymentFeePct":  2,
			"voucherCost":    20000,
		},
		"shipping": map[string]interface{}{
			"forwardShipCost":       22000,
			"returnShipCost":        28000,
			"handlingLossPerReturn": 10000,
		},
		"ads": map[string]interface{}{
			"expectedCpa":         62000,
			"newCustomerRatioPct": 80,
		},
		"market": map[string]interface{}{
			"primaryProvinces": []string{"HCM"},
		},
	}
	rawBody, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/analysis/cod-profit", bytes.NewReader(rawBody))
	req.Header.Set("X-User-Id", "u-1")

	recorder := httptest.NewRecorder()
	handler.CreateCodProfitAnalysis(recorder, req)

	if recorder.Code != http.StatusCreated {
		t.Fatalf("expected status 201, got %d with body %s", recorder.Code, recorder.Body.String())
	}
}

func TestCreateCodProfitAnalysis429(t *testing.T) {
	handler := NewAnalysisHandler(fakeService{
		createFn: func(_ context.Context, _ CreateAnalysisRequest) (*AnalysisRecord, error) {
			return nil, ErrPlanLimit
		},
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/analysis/cod-profit", bytes.NewBufferString(`{}`))
	req.Header.Set("X-User-Id", "u-1")

	recorder := httptest.NewRecorder()
	handler.CreateCodProfitAnalysis(recorder, req)
	if recorder.Code != http.StatusTooManyRequests {
		t.Fatalf("expected 429, got %d", recorder.Code)
	}
}

func TestGetCodProfitAnalysis404(t *testing.T) {
	handler := NewAnalysisHandler(fakeService{
		getFn: func(_ context.Context, _, _ string) (*AnalysisRecord, error) {
			return nil, ErrNotFound
		},
	})
	req := httptest.NewRequest(http.MethodGet, "/api/v1/analysis/anl-missing", nil)
	req.Header.Set("X-Workspace-Id", "ws-1")

	recorder := httptest.NewRecorder()
	handler.GetCodProfitAnalysis(recorder, req)
	if recorder.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", recorder.Code)
	}
}

func TestGetCodProfitAnalysis500(t *testing.T) {
	handler := NewAnalysisHandler(fakeService{
		getFn: func(_ context.Context, _, _ string) (*AnalysisRecord, error) {
			return nil, errors.New("db error")
		},
	})
	req := httptest.NewRequest(http.MethodGet, "/api/v1/analysis/anl-1", nil)
	req.Header.Set("X-Workspace-Id", "ws-1")

	recorder := httptest.NewRecorder()
	handler.GetCodProfitAnalysis(recorder, req)
	if recorder.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500, got %d", recorder.Code)
	}
}

func TestExportCodProfitAnalysis200(t *testing.T) {
	handler := NewAnalysisHandler(fakeService{
		exportFn: func(_ context.Context, _ ExportAnalysisRequest) (*ExportArtifact, error) {
			return &ExportArtifact{
				ContentType: "text/csv; charset=utf-8",
				FileName:    "anl.csv",
				Data:        []byte("analysis_id,anl_1\n"),
			}, nil
		},
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/analysis/anl-1", bytes.NewBufferString(`{"format":"csv"}`))
	req.Header.Set("X-Workspace-Id", "ws-1")
	recorder := httptest.NewRecorder()
	handler.ExportCodProfitAnalysis(recorder, req)
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", recorder.Code)
	}
}

func TestExportCodProfitAnalysis402(t *testing.T) {
	handler := NewAnalysisHandler(fakeService{
		exportFn: func(_ context.Context, _ ExportAnalysisRequest) (*ExportArtifact, error) {
			return nil, ErrExportNotAllowed
		},
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/analysis/anl-1", bytes.NewBufferString(`{"format":"csv"}`))
	req.Header.Set("X-Workspace-Id", "ws-1")
	recorder := httptest.NewRecorder()
	handler.ExportCodProfitAnalysis(recorder, req)
	if recorder.Code != http.StatusPaymentRequired {
		t.Fatalf("expected 402, got %d", recorder.Code)
	}
}
