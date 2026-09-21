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
	"encoding/csv"
	"fmt"
	"strings"
)

func buildCSV(record *AnalysisRecord) ([]byte, error) {
	buffer := &bytes.Buffer{}
	writer := csv.NewWriter(buffer)
	rows := [][]string{
		{"analysis_id", record.ID},
		{"created_at", record.CreatedAt.UTC().Format("2006-01-02T15:04:05Z")},
		{"risk_score", fmt.Sprintf("%.2f", record.Output.Risk.Score)},
		{"risk_level", record.Output.Risk.Level},
		{"net_profit_per_order_vnd", fmt.Sprintf("%.2f", record.Output.Profit.NetProfitPerOrder)},
		{"break_even_cpa_vnd", fmt.Sprintf("%.2f", record.Output.Profit.BreakEvenCPA)},
		{"decision_status", record.Output.Decision.Status},
		{"decision_message", record.Output.Decision.Message},
	}
	for _, row := range rows {
		if err := writer.Write(row); err != nil {
			return nil, err
		}
	}
	writer.Flush()
	return buffer.Bytes(), writer.Error()
}

func buildPseudoPDF(record *AnalysisRecord) ([]byte, error) {
	// Minimal PDF-like payload for MVP export without external dependencies.
	// It is intentionally simple and human-readable enough for early integration checks.
	content := []string{
		"CODPROFIT ANALYSIS REPORT",
		"ID: " + record.ID,
		"Risk Score: " + fmt.Sprintf("%.2f", record.Output.Risk.Score),
		"Risk Level: " + record.Output.Risk.Level,
		"Net Profit/Order: " + fmt.Sprintf("%.2f VND", record.Output.Profit.NetProfitPerOrder),
		"Break-even CPA: " + fmt.Sprintf("%.2f VND", record.Output.Profit.BreakEvenCPA),
		"Decision: " + record.Output.Decision.Status,
		"Message: " + record.Output.Decision.Message,
	}
	return []byte(strings.Join(content, "\n")), nil
}
