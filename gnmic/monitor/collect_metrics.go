package main

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/prometheus/client_model/go"
	"github.com/prometheus/common/expfmt"
	"github.com/prometheus/common/model"
)

// failTracker remembers, per (source, subscription), the last counter value and the time
// of the last increase.
type failTracker struct {
	data map[string]map[string]counterRecord // collector -> (source:subscription -> record)
}

type counterRecord struct {
	value         uint64
	lastIncrease  time.Time
}

func newFailTracker() *failTracker {
	return &failTracker{
		data: make(map[string]map[string]counterRecord),
	}
}

// parseMetrics parses Prometheus text exposition from `body` (use expfmt.TextParser) and returns issues
// for collector `collector`:
//  1. For every gnmic_target_up sample with value 0: Issue{Collector: collector, Target: <name label>,
//     Sub: "", Reason: "gNMI connection down (<STATE>)"} where STATE is the name of the matching
//     gnmic_target_connection_state value (UNKNOWN, IDLE, CONNECTING, READY, TRANSIENT_FAILURE, SHUTDOWN),
//     or "no state" if that metric is absent for the target.
//  2. For every failed-subscribe counter sample: compare with the value stored in `tr`.
//     The first time a key is seen only store it as a baseline (no issue, even if the value is > 0).
//     If the value increased compared with the stored one, record `now` as the last increase time.
//     While now - lastIncrease < 10 minutes return Issue{Collector: collector, Target: <source label>,
//     Sub: <subscription label>, Reason: "subscribe request failed (<value> total)"} (value as an integer).
// A body that cannot be parsed returns an error.
func parseMetrics(collector string, body io.Reader, now time.Time, tr *failTracker) ([]Issue, error) {
	parser := expfmt.NewTextParser(model.UTF8Validation)
	families, err := parser.TextToMetricFamilies(body)
	if err != nil {
		return nil, fmt.Errorf("parse metrics: %w", err)
	}

	var issues []Issue

	// Build lookup maps for the metrics
	targetUpMap := make(map[string]uint64)          // name -> value (0 or 1)
	connectionStateMap := make(map[string]uint64)   // name -> state value
	failedCounters := make(map[string]uint64)       // source:subscription -> value

	for _, family := range families {
		if family == nil || family.Name == nil {
			continue
		}

		metricName := *family.Name

		switch metricName {
		case "gnmic_target_up":
			for _, metric := range family.Metric {
				if metric == nil || metric.Gauge == nil {
					continue
				}
				// Get the "name" label
				name := getLabelValue(metric, "name")
				if name != "" {
					targetUpMap[name] = uint64(metric.Gauge.GetValue())
				}
			}

		case "gnmic_target_connection_state":
			for _, metric := range family.Metric {
				if metric == nil || metric.Gauge == nil {
					continue
				}
				// Get the "name" label
				name := getLabelValue(metric, "name")
				if name != "" {
					connectionStateMap[name] = uint64(metric.Gauge.GetValue())
				}
			}

		case "gnmic_subscribe_number_of_failed_subscribe_request_messages_total":
			for _, metric := range family.Metric {
				if metric == nil || metric.Counter == nil {
					continue
				}
				source := getLabelValue(metric, "source")
				subscription := getLabelValue(metric, "subscription")
				if source != "" && subscription != "" {
					key := source + ":" + subscription
					failedCounters[key] = uint64(metric.Counter.GetValue())
				}
			}
		}
	}

	// Initialize tracker data for this collector if needed
	if _, ok := tr.data[collector]; !ok {
		tr.data[collector] = make(map[string]counterRecord)
	}

	// Process gnmic_target_up metrics
	for name, value := range targetUpMap {
		if value == 0 {
			// Connection is down
			stateValue, hasState := connectionStateMap[name]
			var stateStr string
			if hasState {
				stateStr = getConnectionStateName(stateValue)
			}
			if stateStr == "" {
				stateStr = "no state"
			}
			issues = append(issues, Issue{
				Collector: collector,
				Target:    name,
				Sub:       "",
				Reason:    fmt.Sprintf("gNMI connection down (%s)", stateStr),
			})
		}
	}

	// Process failed subscribe counters
	for key, value := range failedCounters {
		record, exists := tr.data[collector][key]

		if !exists {
			// First time seeing this key, store as baseline (no issue)
			tr.data[collector][key] = counterRecord{
				value:        value,
				lastIncrease: time.Time{}, // Don't set lastIncrease yet
			}
		} else if value > record.value {
			// Counter increased - update record and report issue
			tr.data[collector][key] = counterRecord{
				value:        value,
				lastIncrease: now,
			}
			// Report issue on the parse where the increase was detected
			parts := splitKey(key)
			if len(parts) == 2 {
				issues = append(issues, Issue{
					Collector: collector,
					Target:    parts[0],
					Sub:       parts[1],
					Reason:    fmt.Sprintf("subscribe request failed (%d total)", value),
				})
			}
		} else {
			// Value didn't increase - update the counter value if needed
			// but keep lastIncrease only if within 10 minutes
			if !record.lastIncrease.IsZero() && now.Sub(record.lastIncrease) >= 10*time.Minute {
				// Clear lastIncrease if we've passed the 10-minute window
				tr.data[collector][key] = counterRecord{
					value:        value,
					lastIncrease: time.Time{},
				}
			} else {
				// Keep the record as-is
				tr.data[collector][key] = record
			}
		}
	}

	return issues, nil
}

// getConnectionStateName returns the name of the connection state
func getConnectionStateName(state uint64) string {
	switch state {
	case 0:
		return "UNKNOWN"
	case 1:
		return "IDLE"
	case 2:
		return "CONNECTING"
	case 3:
		return "READY"
	case 4:
		return "TRANSIENT_FAILURE"
	case 5:
		return "SHUTDOWN"
	default:
		return ""
	}
}

// getLabelValue returns the value of a label from a metric
func getLabelValue(metric *io_prometheus_client.Metric, labelName string) string {
	if metric == nil || metric.Label == nil {
		return ""
	}
	for _, label := range metric.Label {
		if label != nil && label.Name != nil && *label.Name == labelName && label.Value != nil {
			return *label.Value
		}
	}
	return ""
}

// splitKey splits "source:subscription" into [source, subscription]
func splitKey(key string) []string {
	var parts []string
	var current string
	for _, ch := range key {
		if ch == ':' {
			parts = append(parts, current)
			current = ""
		} else {
			current += string(ch)
		}
	}
	if current != "" {
		parts = append(parts, current)
	}
	return parts
}

// RunMetrics scrapes <URL>/metrics of every collector every `every` (first scrape immediately, 5 second
// timeout per request) until ctx is done, and after each round calls st.SetIssues("metrics", all)
// with the issues of all collectors that were scraped successfully in THIS round plus nothing for failed
// ones (an unreachable collector contributes no issues; the API poller already reports it as down).
func RunMetrics(ctx context.Context, st *Store, cols []Collector, every time.Duration) {
	tr := newFailTracker()
	ticker := time.NewTicker(every)
	defer ticker.Stop()

	// Scrape immediately first
	scrapeMetrics(st, cols, tr)

	// Then scrape at the interval
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			scrapeMetrics(st, cols, tr)
		}
	}
}

// scrapeMetrics makes one round of metrics calls to all collectors
func scrapeMetrics(st *Store, cols []Collector, tr *failTracker) {
	now := time.Now()
	var allIssues []Issue

	for _, col := range cols {
		client := &http.Client{
			Timeout: 5 * time.Second,
		}

		url := col.URL + "/metrics"
		resp, err := client.Get(url)
		if err != nil {
			// Failed to scrape, contribute no issues
			continue
		}
		defer resp.Body.Close()

		// Check for non-200 status
		if resp.StatusCode != http.StatusOK {
			continue
		}

		// Parse the metrics
		issues, err := parseMetrics(col.Name, resp.Body, now, tr)
		if err != nil {
			// Failed to parse, contribute no issues
			continue
		}

		allIssues = append(allIssues, issues...)
	}

	// Update the store with all issues from successful scrapes
	st.SetIssues("metrics", allIssues)
}
