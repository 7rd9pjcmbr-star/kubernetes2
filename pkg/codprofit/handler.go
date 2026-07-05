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
	"encoding/json"
	"errors"
	"net/http"
	"strings"
)

type analysisUsecase interface {
	CreateAnalysis(ctx context.Context, req CreateAnalysisRequest) (*AnalysisRecord, error)
	GetAnalysis(ctx context.Context, workspaceID, analysisID string) (*AnalysisRecord, error)
}

type AnalysisHandler struct {
	svc analysisUsecase
}

func NewAnalysisHandler(svc analysisUsecase) *AnalysisHandler {
	return &AnalysisHandler{svc: svc}
}

func (h *AnalysisHandler) CreateCodProfitAnalysis(w http.ResponseWriter, r *http.Request) {
	userID, ok := userIDFromContext(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", "Access token is missing or invalid.", "", "")
		return
	}

	var req createAnalysisRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "Invalid JSON body.", "", "Check request format and field types.")
		return
	}

	record, err := h.svc.CreateAnalysis(r.Context(), req.toAppRequest(userID))
	if err != nil {
		h.handleAppError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, record.toResponse())
}

func (h *AnalysisHandler) GetCodProfitAnalysis(w http.ResponseWriter, r *http.Request) {
	workspaceID, ok := workspaceIDFromHeader(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", "Workspace context is missing.", "", "Provide X-Workspace-Id header.")
		return
	}
	analysisID := analysisIDFromPath(r.URL.Path)
	if analysisID == "" {
		writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", "analysisId is required.", "analysisId", "")
		return
	}
	record, err := h.svc.GetAnalysis(r.Context(), workspaceID, analysisID)
	if err != nil {
		h.handleAppError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, record.toResponse())
}

func (h *AnalysisHandler) handleAppError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, ErrPlanLimit):
		writeError(w, http.StatusTooManyRequests, "PLAN_LIMIT_REACHED", "Ban da dat gioi han phan tich thang nay.", "", "Nang cap goi de tiep tuc.")
	case errors.Is(err, ErrNotFound):
		writeError(w, http.StatusNotFound, "NOT_FOUND", "Analysis not found.", "", "")
	default:
		if looksLikeValidationError(err) {
			writeError(w, http.StatusBadRequest, "VALIDATION_ERROR", err.Error(), "", "")
			return
		}
		writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "Unexpected server error.", "", "")
	}
}

type createAnalysisRequest struct {
	WorkspaceID string `json:"workspaceId"`
	Mode        string `json:"mode"`
	Product     struct {
		Name         string  `json:"name"`
		Category     string  `json:"category"`
		SellingPrice float64 `json:"sellingPrice"`
		Cogs         float64 `json:"cogs"`
	} `json:"product"`
	Costs struct {
		PlatformFeePct float64 `json:"platformFeePct"`
		PaymentFeePct  float64 `json:"paymentFeePct"`
		VoucherCost    float64 `json:"voucherCost"`
	} `json:"costs"`
	Shipping struct {
		ForwardShipCost       float64 `json:"forwardShipCost"`
		ReturnShipCost        float64 `json:"returnShipCost"`
		HandlingLossPerReturn float64 `json:"handlingLossPerReturn"`
	} `json:"shipping"`
	Ads struct {
		ExpectedCpa         float64 `json:"expectedCpa"`
		NewCustomerRatioPct float64 `json:"newCustomerRatioPct"`
	} `json:"ads"`
	Market struct {
		PrimaryProvinces        []string `json:"primaryProvinces"`
		HistoricalReturnRatePct *float64 `json:"historicalReturnRatePct"`
		ContentMismatchScore    *float64 `json:"contentMismatchScore"`
	} `json:"market"`
}

func (r *createAnalysisRequest) toAppRequest(userID string) CreateAnalysisRequest {
	return CreateAnalysisRequest{
		WorkspaceID: r.WorkspaceID,
		UserID:      userID,
		Input: Input{
			Mode: r.Mode,
			Product: ProductInput{
				Name:         r.Product.Name,
				Category:     Category(r.Product.Category),
				SellingPrice: r.Product.SellingPrice,
				COGS:         r.Product.Cogs,
			},
			Costs: CostsInput{
				PlatformFeePct: r.Costs.PlatformFeePct,
				PaymentFeePct:  r.Costs.PaymentFeePct,
				VoucherCost:    r.Costs.VoucherCost,
			},
			Shipping: ShippingInput{
				ForwardShipCost:       r.Shipping.ForwardShipCost,
				ReturnShipCost:        r.Shipping.ReturnShipCost,
				HandlingLossPerReturn: r.Shipping.HandlingLossPerReturn,
			},
			Ads: AdsInput{
				ExpectedCPA:         r.Ads.ExpectedCpa,
				NewCustomerRatioPct: r.Ads.NewCustomerRatioPct,
			},
			Market: MarketInput{
				PrimaryProvinces:        r.Market.PrimaryProvinces,
				HistoricalReturnRatePct: r.Market.HistoricalReturnRatePct,
				ContentMismatchScore:    r.Market.ContentMismatchScore,
			},
		},
	}
}

type analysisResponse struct {
	AnalysisID  string          `json:"analysisId"`
	CreatedAt   string          `json:"createdAt"`
	Risk        RiskResult      `json:"risk"`
	Profit      ProfitResult    `json:"profit"`
	Decision    Decision        `json:"decision"`
	Breakdown   ProfitBreakdown `json:"breakdown"`
	Suggestions []Suggestion    `json:"suggestions"`
}

func (r *AnalysisRecord) toResponse() analysisResponse {
	return analysisResponse{
		AnalysisID:  r.ID,
		CreatedAt:   r.CreatedAt.UTC().Format("2006-01-02T15:04:05Z"),
		Risk:        r.Output.Risk,
		Profit:      r.Output.Profit,
		Decision:    r.Output.Decision,
		Breakdown:   r.Output.Breakdown,
		Suggestions: r.Output.Suggestions,
	}
}

type errorEnvelope struct {
	Error struct {
		Code    string `json:"code"`
		Message string `json:"message"`
		Field   string `json:"field,omitempty"`
		Hint    string `json:"hint,omitempty"`
	} `json:"error"`
}

func writeJSON(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, code, message, field, hint string) {
	var envelope errorEnvelope
	envelope.Error.Code = code
	envelope.Error.Message = message
	envelope.Error.Field = field
	envelope.Error.Hint = hint
	writeJSON(w, status, envelope)
}

func looksLikeValidationError(err error) bool {
	msg := strings.ToLower(err.Error())
	markers := []string{"required", "must be", "invalid", "cannot", "category", "sellingprice", "primaryprovinces"}
	for _, marker := range markers {
		if strings.Contains(msg, marker) {
			return true
		}
	}
	return false
}

func userIDFromContext(r *http.Request) (string, bool) {
	v := r.Header.Get("X-User-Id")
	return v, v != ""
}

func workspaceIDFromHeader(r *http.Request) (string, bool) {
	v := r.Header.Get("X-Workspace-Id")
	return v, v != ""
}

func analysisIDFromPath(path string) string {
	parts := strings.Split(strings.Trim(path, "/"), "/")
	if len(parts) >= 4 && parts[2] == "analysis" {
		return parts[3]
	}
	return ""
}
