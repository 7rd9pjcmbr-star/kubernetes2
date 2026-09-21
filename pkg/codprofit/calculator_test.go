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
	"strings"
	"testing"
)

func TestCalculateValidationErrors(t *testing.T) {
	cfg := DefaultRuleConfig()
	bm := validBenchmark()
	in := validInput()
	tests := []struct {
		name    string
		mutate  func(*Input)
		wantErr string
	}{
		{
			name: "selling price too low",
			mutate: func(i *Input) {
				i.Product.SellingPrice = 999
			},
			wantErr: "sellingPrice",
		},
		{
			name: "cogs greater than selling price",
			mutate: func(i *Input) {
				i.Product.COGS = i.Product.SellingPrice + 1
			},
			wantErr: "cannot exceed",
		},
		{
			name: "invalid fee",
			mutate: func(i *Input) {
				i.Costs.PlatformFeePct = 101
			},
			wantErr: "platformFeePct",
		},
		{
			name: "missing province",
			mutate: func(i *Input) {
				i.Market.PrimaryProvinces = nil
			},
			wantErr: "primaryProvinces",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			input := in
			tc.mutate(&input)
			_, err := Calculate(input, bm, cfg)
			if err == nil {
				t.Fatalf("expected error, got nil")
			}
			if !strings.Contains(err.Error(), tc.wantErr) {
				t.Fatalf("expected error containing %q, got %q", tc.wantErr, err.Error())
			}
		})
	}
}

func TestCalculateUsesHistoricalReturnRate(t *testing.T) {
	cfg := DefaultRuleConfig()
	in := validInput()
	bm := validBenchmark()
	outA, err := Calculate(in, bm, cfg)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	historical := 30.0
	in.Market.HistoricalReturnRatePct = &historical
	outB, err := Calculate(in, bm, cfg)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if outB.Risk.Score <= outA.Risk.Score {
		t.Fatalf("expected risk score to increase, got base=%v and hist=%v", outA.Risk.Score, outB.Risk.Score)
	}
}

func TestCalculateProfitMath(t *testing.T) {
	cfg := DefaultRuleConfig()
	in := validInput()
	bm := validBenchmark()
	out, err := Calculate(in, bm, cfg)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	assertAlmostEqual(t, out.Breakdown.PlatformFees, 29900)
	assertAlmostEqual(t, out.Breakdown.ExpectedReturnCost, 6000)
	assertAlmostEqual(t, out.Profit.NetProfitPerOrder, 44100)
	assertAlmostEqual(t, out.Profit.BreakEvenCPA, 106100)
}

func TestCalculateDecisionAndSuggestions(t *testing.T) {
	cfg := DefaultRuleConfig()
	in := validInput()
	highHist := 30.0
	in.Market.HistoricalReturnRatePct = &highHist
	in.Ads.ExpectedCPA = 110000
	out, err := Calculate(in, validBenchmark(), cfg)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if out.Decision.Status != "stop" {
		t.Fatalf("expected stop when profit is negative, got %s", out.Decision.Status)
	}
	found := false
	for _, suggestion := range out.Suggestions {
		if suggestion.ID == "reduce-cpa" {
			found = true
		}
	}
	if !found {
		t.Fatalf("expected reduce-cpa suggestion when CPA > break-even")
	}
}

func validInput() Input {
	return Input{
		Mode: "quick",
		Product: ProductInput{
			Name:         "Kem chong nang SPF50",
			Category:     CategoryBeauty,
			SellingPrice: 299000,
			COGS:         115000,
		},
		Costs: CostsInput{
			PlatformFeePct: 8,
			PaymentFeePct:  2,
			VoucherCost:    20000,
		},
		Shipping: ShippingInput{
			ForwardShipCost:       22000,
			ReturnShipCost:        28000,
			HandlingLossPerReturn: 10000,
		},
		Ads: AdsInput{
			ExpectedCPA:         62000,
			NewCustomerRatioPct: 80,
		},
		Market: MarketInput{
			PrimaryProvinces: []string{"HCM"},
		},
	}
}

func validBenchmark() BenchmarkAggregate {
	return BenchmarkAggregate{
		BaselineReturnRatePct: 10,
		CarrierDelayScore:     20,
		PriceBandRiskScore:    35,
	}
}

func assertAlmostEqual(t *testing.T, got, want float64) {
	t.Helper()
	const eps = 0.001
	if got-want > eps || want-got > eps {
		t.Fatalf("expected %v, got %v", want, got)
	}
}
