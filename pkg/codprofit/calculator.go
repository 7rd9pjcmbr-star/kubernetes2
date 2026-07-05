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
	"errors"
	"fmt"
	"math"
	"sort"
)

// Calculate computes risk, profit and suggestions from inputs.
func Calculate(in Input, bm BenchmarkAggregate, cfg RuleConfig) (Output, error) {
	if err := validateInput(in); err != nil {
		return Output{}, err
	}
	if err := validateBenchmark(bm); err != nil {
		return Output{}, err
	}
	if err := validateConfig(cfg); err != nil {
		return Output{}, err
	}

	effectiveReturnRate := bm.BaselineReturnRatePct
	if in.Market.HistoricalReturnRatePct != nil {
		effectiveReturnRate = *in.Market.HistoricalReturnRatePct
	}

	signalDistrict := clamp(effectiveReturnRate, 0, 100)
	signalCarrier := clamp(bm.CarrierDelayScore, 0, 100)
	signalCategory := categoryFragilityScore(in.Product.Category)
	signalPrice := priceBandRisk(in.Product.SellingPrice, in.Product.Category, bm.PriceBandRiskScore)
	signalNewCust := clamp(defaultIfZero(in.Ads.NewCustomerRatioPct, 100), 0, 100)
	signalMismatch := estimateMismatchRisk(in)

	components := []RiskComponent{
		{Key: "district_return_rate", Label: "District return rate", Points: weighted(signalDistrict, cfg.Weights["district_return_rate"])},
		{Key: "carrier_delay", Label: "Carrier delay", Points: weighted(signalCarrier, cfg.Weights["carrier_delay"])},
		{Key: "category_fragility", Label: "Category fragility", Points: weighted(signalCategory, cfg.Weights["category_fragility"])},
		{Key: "price_band_risk", Label: "Price band risk", Points: weighted(signalPrice, cfg.Weights["price_band_risk"])},
		{Key: "new_customer_ratio", Label: "New customer ratio", Points: weighted(signalNewCust, cfg.Weights["new_customer_ratio"])},
		{Key: "content_mismatch", Label: "Content mismatch risk", Points: weighted(signalMismatch, cfg.Weights["content_mismatch"])},
	}

	riskScore := 0.0
	for _, c := range components {
		riskScore += c.Points
	}
	riskScore = round2(clamp(riskScore, 0, 100))
	riskLevel := classifyRisk(riskScore, cfg.LowMax, cfg.MediumMax)

	platformFees := in.Product.SellingPrice * (in.Costs.PlatformFeePct + in.Costs.PaymentFeePct) / 100.0
	expectedReturnCost := (effectiveReturnRate / 100.0) * (in.Shipping.ForwardShipCost + in.Shipping.ReturnShipCost + in.Shipping.HandlingLossPerReturn)
	netProfit := in.Product.SellingPrice - in.Product.COGS - platformFees - in.Costs.VoucherCost - in.Shipping.ForwardShipCost - expectedReturnCost - in.Ads.ExpectedCPA
	breakEvenCPA := in.Product.SellingPrice - in.Product.COGS - platformFees - in.Costs.VoucherCost - in.Shipping.ForwardShipCost - expectedReturnCost

	netProfit = round2(netProfit)
	breakEvenCPA = round2(breakEvenCPA)

	decision := buildDecision(netProfit, riskLevel)
	suggestions := buildSuggestions(in, riskLevel, netProfit, breakEvenCPA, effectiveReturnRate, cfg)
	sort.SliceStable(suggestions, func(i, j int) bool {
		return suggestionPriority(suggestions[i].Impact) < suggestionPriority(suggestions[j].Impact)
	})

	return Output{
		Risk: RiskResult{
			Score:      riskScore,
			Level:      riskLevel,
			Components: components,
		},
		Profit: ProfitResult{
			NetProfitPerOrder: netProfit,
			BreakEvenCPA:      breakEvenCPA,
			Currency:          "VND",
		},
		Decision: decision,
		Breakdown: ProfitBreakdown{
			SellingPrice:       round2(in.Product.SellingPrice),
			COGS:               round2(in.Product.COGS),
			PlatformFees:       round2(platformFees),
			VoucherCost:        round2(in.Costs.VoucherCost),
			ShippingCost:       round2(in.Shipping.ForwardShipCost),
			ExpectedReturnCost: round2(expectedReturnCost),
			AdCost:             round2(in.Ads.ExpectedCPA),
			NetProfit:          netProfit,
		},
		Suggestions: suggestions,
	}, nil
}

func validateInput(in Input) error {
	if in.Product.Name == "" {
		return errors.New("product.name is required")
	}
	if in.Product.SellingPrice < 1000 {
		return errors.New("product.sellingPrice must be >= 1000")
	}
	if in.Product.COGS < 0 {
		return errors.New("product.cogs must be >= 0")
	}
	if in.Product.COGS > in.Product.SellingPrice {
		return errors.New("product.cogs cannot exceed product.sellingPrice")
	}
	if in.Costs.PlatformFeePct < 0 || in.Costs.PlatformFeePct > 100 {
		return errors.New("costs.platformFeePct must be in [0,100]")
	}
	if in.Costs.PaymentFeePct < 0 || in.Costs.PaymentFeePct > 100 {
		return errors.New("costs.paymentFeePct must be in [0,100]")
	}
	if in.Costs.VoucherCost < 0 {
		return errors.New("costs.voucherCost must be >= 0")
	}
	if in.Shipping.ForwardShipCost < 0 || in.Shipping.ReturnShipCost < 0 || in.Shipping.HandlingLossPerReturn < 0 {
		return errors.New("shipping costs must be >= 0")
	}
	if in.Ads.ExpectedCPA < 0 {
		return errors.New("ads.expectedCpa must be >= 0")
	}
	if in.Ads.NewCustomerRatioPct < 0 || in.Ads.NewCustomerRatioPct > 100 {
		return errors.New("ads.newCustomerRatioPct must be in [0,100]")
	}
	if len(in.Market.PrimaryProvinces) == 0 {
		return errors.New("market.primaryProvinces must have at least one province")
	}
	if in.Market.HistoricalReturnRatePct != nil {
		v := *in.Market.HistoricalReturnRatePct
		if v < 0 || v > 100 {
			return errors.New("market.historicalReturnRatePct must be in [0,100]")
		}
	}
	if in.Market.ContentMismatchScore != nil {
		v := *in.Market.ContentMismatchScore
		if v < 0 || v > 100 {
			return errors.New("market.contentMismatchScore must be in [0,100]")
		}
	}
	switch in.Product.Category {
	case CategoryBeauty, CategoryFashion, CategoryHome, CategoryMotherBaby, CategoryOther:
	default:
		return fmt.Errorf("product.category is invalid: %s", in.Product.Category)
	}
	return nil
}

func validateBenchmark(bm BenchmarkAggregate) error {
	if bm.BaselineReturnRatePct < 0 || bm.BaselineReturnRatePct > 100 {
		return errors.New("benchmark.baselineReturnRatePct must be in [0,100]")
	}
	if bm.CarrierDelayScore < 0 || bm.CarrierDelayScore > 100 {
		return errors.New("benchmark.carrierDelayScore must be in [0,100]")
	}
	if bm.PriceBandRiskScore < 0 || bm.PriceBandRiskScore > 100 {
		return errors.New("benchmark.priceBandRiskScore must be in [0,100]")
	}
	return nil
}

func validateConfig(cfg RuleConfig) error {
	required := []string{"district_return_rate", "carrier_delay", "category_fragility", "price_band_risk", "new_customer_ratio", "content_mismatch"}
	sum := 0.0
	for _, key := range required {
		v, ok := cfg.Weights[key]
		if !ok {
			return fmt.Errorf("missing weight: %s", key)
		}
		if v < 0 || v > 1 {
			return fmt.Errorf("weight %s must be in [0,1]", key)
		}
		sum += v
	}
	if math.Abs(sum-1.0) > 0.001 {
		return fmt.Errorf("weights must sum to 1.0, got %.3f", sum)
	}
	if cfg.LowMax < 0 || cfg.MediumMax < cfg.LowMax || cfg.MediumMax > 100 {
		return errors.New("invalid risk thresholds")
	}
	return nil
}

func categoryFragilityScore(c Category) float64 {
	switch c {
	case CategoryFashion:
		return 75
	case CategoryBeauty:
		return 68
	case CategoryMotherBaby:
		return 62
	case CategoryOther:
		return 55
	case CategoryHome:
		return 50
	default:
		return 55
	}
}

func priceBandRisk(price float64, c Category, benchmarkScore float64) float64 {
	base := benchmarkScore
	switch {
	case price < 99000:
		base += 12
	case price < 199000:
		base += 6
	case price > 699000:
		base += 8
	default:
		base += 3
	}
	if c == CategoryFashion {
		base += 4
	}
	if c == CategoryHome {
		base -= 2
	}
	return clamp(base, 0, 100)
}

func estimateMismatchRisk(in Input) float64 {
	if in.Market.ContentMismatchScore != nil {
		return clamp(*in.Market.ContentMismatchScore, 0, 100)
	}
	switch in.Product.Category {
	case CategoryFashion:
		return 50
	case CategoryBeauty:
		return 45
	default:
		return 40
	}
}

func classifyRisk(score, lowMax, mediumMax float64) string {
	if score <= lowMax {
		return "low"
	}
	if score <= mediumMax {
		return "medium"
	}
	return "high"
}

func buildDecision(netProfit float64, riskLevel string) Decision {
	if netProfit <= 0 {
		return Decision{
			Status:  "stop",
			Message: "Net profit is negative. Fix price/cost before scaling.",
		}
	}
	switch riskLevel {
	case "high":
		return Decision{
			Status:  "caution",
			Message: "High return risk. Run a small test and block high-risk areas.",
		}
	case "medium":
		return Decision{
			Status:  "caution",
			Message: "Run with controls. Monitor CPA and return rate daily.",
		}
	default:
		return Decision{
			Status:  "go",
			Message: "Model looks healthy. Scale only while CPA stays under break-even.",
		}
	}
}

func buildSuggestions(in Input, riskLevel string, netProfit, breakEvenCPA, effectiveReturnRate float64, cfg RuleConfig) []Suggestion {
	out := make([]Suggestion, 0, 4)
	if riskLevel == "high" {
		out = append(out, Suggestion{
			ID:     "block-high-risk-areas",
			Title:  "Block high-risk areas",
			Impact: "high",
			Action: "Exclude top districts/provinces with high COD return rates from scaling campaigns.",
		})
	}
	if in.Ads.ExpectedCPA > breakEvenCPA {
		out = append(out, Suggestion{
			ID:     "reduce-cpa",
			Title:  "Expected CPA is above break-even",
			Impact: "high",
			Action: "Lower bid, improve creative CTR/CVR, or pause scale until CPA drops below break-even.",
		})
	}
	minProfit := cfg.MinProfitThresholdVND[in.Product.Category]
	if netProfit > 0 && netProfit < minProfit {
		out = append(out, Suggestion{
			ID:     "thin-margin",
			Title:  "Margin is thin for this category",
			Impact: "medium",
			Action: "Increase price slightly or reduce voucher to protect contribution margin.",
		})
	}
	if effectiveReturnRate >= 12 {
		out = append(out, Suggestion{
			ID:     "improve-qualification",
			Title:  "Return rate risk is elevated",
			Impact: "medium",
			Action: "Add clearer product specs, shipping ETA, and qualification copy to reduce mismatch returns.",
		})
	}
	if len(out) == 0 {
		out = append(out, Suggestion{
			ID:     "keep-monitoring",
			Title:  "Keep monitoring",
			Impact: "low",
			Action: "Track CPA and return rate daily; alert if CPA exceeds break-even for 3 consecutive days.",
		})
	}
	return out
}

func weighted(signal, weight float64) float64 {
	return round2(clamp(signal, 0, 100) * weight)
}

func suggestionPriority(impact string) int {
	switch impact {
	case "high":
		return 1
	case "medium":
		return 2
	default:
		return 3
	}
}

func clamp(v, min, max float64) float64 {
	if v < min {
		return min
	}
	if v > max {
		return max
	}
	return v
}

func round2(v float64) float64 {
	return math.Round(v*100) / 100
}

func defaultIfZero(v, fallback float64) float64 {
	if v == 0 {
		return fallback
	}
	return v
}
