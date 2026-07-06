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

import "time"

// Category identifies product domain risk profile.
type Category string

const (
	CategoryBeauty     Category = "beauty"
	CategoryFashion    Category = "fashion"
	CategoryHome       Category = "home"
	CategoryMotherBaby Category = "mother_baby"
	CategoryOther      Category = "other"
)

// Input is the top-level calculator request payload.
type Input struct {
	Product  ProductInput  `json:"product"`
	Costs    CostsInput    `json:"costs"`
	Shipping ShippingInput `json:"shipping"`
	Ads      AdsInput      `json:"ads"`
	Market   MarketInput   `json:"market"`
	Mode     string        `json:"mode"`
}

type ProductInput struct {
	Name         string   `json:"name"`
	Category     Category `json:"category"`
	SellingPrice float64  `json:"sellingPrice"`
	COGS         float64  `json:"cogs"`
}

type CostsInput struct {
	PlatformFeePct float64 `json:"platformFeePct"`
	PaymentFeePct  float64 `json:"paymentFeePct"`
	VoucherCost    float64 `json:"voucherCost"`
}

type ShippingInput struct {
	ForwardShipCost       float64 `json:"forwardShipCost"`
	ReturnShipCost        float64 `json:"returnShipCost"`
	HandlingLossPerReturn float64 `json:"handlingLossPerReturn"`
}

type AdsInput struct {
	ExpectedCPA         float64 `json:"expectedCpa"`
	NewCustomerRatioPct float64 `json:"newCustomerRatioPct"`
}

type MarketInput struct {
	PrimaryProvinces        []string `json:"primaryProvinces"`
	HistoricalReturnRatePct *float64 `json:"historicalReturnRatePct,omitempty"`
	ContentMismatchScore    *float64 `json:"contentMismatchScore,omitempty"`
}

// BenchmarkAggregate is the fallback signal when user data is missing.
type BenchmarkAggregate struct {
	BaselineReturnRatePct float64 `json:"baselineReturnRatePct"`
	CarrierDelayScore     float64 `json:"carrierDelayScore"`
	PriceBandRiskScore    float64 `json:"priceBandRiskScore"`
}

// RuleConfig controls risk weights and decision thresholds.
type RuleConfig struct {
	Weights               map[string]float64
	LowMax                float64
	MediumMax             float64
	MinProfitThresholdVND map[Category]float64
}

func DefaultRuleConfig() RuleConfig {
	return RuleConfig{
		Weights: map[string]float64{
			"district_return_rate": 0.30,
			"carrier_delay":        0.15,
			"category_fragility":   0.15,
			"price_band_risk":      0.15,
			"new_customer_ratio":   0.15,
			"content_mismatch":     0.10,
		},
		LowMax:    39.99,
		MediumMax: 69.99,
		MinProfitThresholdVND: map[Category]float64{
			CategoryBeauty:     15000,
			CategoryFashion:    12000,
			CategoryHome:       20000,
			CategoryMotherBaby: 18000,
			CategoryOther:      15000,
		},
	}
}

type Output struct {
	Risk        RiskResult      `json:"risk"`
	Profit      ProfitResult    `json:"profit"`
	Decision    Decision        `json:"decision"`
	Breakdown   ProfitBreakdown `json:"breakdown"`
	Suggestions []Suggestion    `json:"suggestions"`
}

type RiskResult struct {
	Score      float64         `json:"score"`
	Level      string          `json:"level"`
	Components []RiskComponent `json:"components"`
}

type RiskComponent struct {
	Key    string  `json:"key"`
	Label  string  `json:"label"`
	Points float64 `json:"points"`
}

type ProfitResult struct {
	NetProfitPerOrder float64 `json:"netProfitPerOrder"`
	BreakEvenCPA      float64 `json:"breakEvenCpa"`
	Currency          string  `json:"currency"`
}

type Decision struct {
	Status  string `json:"status"`
	Message string `json:"message"`
}

type ProfitBreakdown struct {
	SellingPrice       float64 `json:"sellingPrice"`
	COGS               float64 `json:"cogs"`
	PlatformFees       float64 `json:"platformFees"`
	VoucherCost        float64 `json:"voucherCost"`
	ShippingCost       float64 `json:"shippingCost"`
	ExpectedReturnCost float64 `json:"expectedReturnCost"`
	AdCost             float64 `json:"adCost"`
	NetProfit          float64 `json:"netProfit"`
}

type Suggestion struct {
	ID     string `json:"id"`
	Title  string `json:"title"`
	Impact string `json:"impact"`
	Action string `json:"action"`
}

// AnalysisRecord models persisted analysis data.
type AnalysisRecord struct {
	ID          string    `json:"analysisId"`
	WorkspaceID string    `json:"workspaceId"`
	CreatedBy   string    `json:"createdBy"`
	Input       Input     `json:"input"`
	Output      Output    `json:"output"`
	CreatedAt   time.Time `json:"createdAt"`
}

type MonthlyUsage struct {
	AnalysesCount int
	ExportsCount  int
}
