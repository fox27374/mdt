package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"sort"
	"time"
)

// parseTargets turns the body of GET /api/v1/targets into TargetConfig values owned by `owner`.
// Follow the real shape documented in testdata/README.md and visible in the fixtures.
// Name: the target's configured name, or its address if it has no name.
// Address: the target's address (the key / config address field, e.g. "172.24.80.240:57400").
// Owner: `owner`. Subs: one SubConfig per subscription, with Interval parsed from sample-interval.
// sample-interval may be a JSON number (nanoseconds, the Go default) or a duration string like "30s":
// accept both. A subscription without a sample-interval gets Interval 10s (gnmic's default).
func parseTargets(body []byte, owner string) ([]TargetConfig, error) {
	// Parse the JSON response
	var targetsMap map[string]interface{}
	if err := json.Unmarshal(body, &targetsMap); err != nil {
		return nil, fmt.Errorf("parse JSON: %w", err)
	}

	var targets []TargetConfig

	// Iterate over each target in the response
	for targetKey := range targetsMap {
		targetData, ok := targetsMap[targetKey].(map[string]interface{})
		if !ok {
			continue
		}

		configData, ok := targetData["config"].(map[string]interface{})
		if !ok {
			continue
		}

		// Extract target name and address
		targetName, _ := configData["name"].(string)
		targetAddress, _ := configData["address"].(string)

		// If name is empty, use address
		if targetName == "" {
			targetName = targetAddress
		}

		// Skip if we don't have an address
		if targetAddress == "" {
			continue
		}

		// Get the configured subscriptions list
		var configuredSubs []string
		if subsList, ok := configData["subscriptions"].([]interface{}); ok {
			for _, sub := range subsList {
				if subName, ok := sub.(string); ok {
					configuredSubs = append(configuredSubs, subName)
				}
			}
		}

		// Get the subscriptions details
		subscriptionsDetail, _ := targetData["subscriptions"].(map[string]interface{})

		// Build SubConfig for each configured subscription
		var subs []SubConfig
		if len(configuredSubs) > 0 {
			// Target has explicit subscriptions list
			for _, subName := range configuredSubs {
				if subDetail, ok := subscriptionsDetail[subName].(map[string]interface{}); ok {
					interval := parseInterval(subDetail["sample-interval"])
					subs = append(subs, SubConfig{
						Name:     subName,
						Interval: interval,
					})
				} else {
					// Subscription is configured but not in the detail map, set to default 10s
					subs = append(subs, SubConfig{
						Name:     subName,
						Interval: 10 * time.Second,
					})
				}
			}
		} else {
			// No explicit subscriptions list: use ALL subscriptions from detail (gnmic's rule)
			for subName, subDetail := range subscriptionsDetail {
				if subDetailMap, ok := subDetail.(map[string]interface{}); ok {
					interval := parseInterval(subDetailMap["sample-interval"])
					subs = append(subs, SubConfig{
						Name:     subName,
						Interval: interval,
					})
				}
			}
			// Sort by name for consistent ordering
			sort.Slice(subs, func(i, j int) bool {
				return subs[i].Name < subs[j].Name
			})
		}

		targets = append(targets, TargetConfig{
			Name:    targetName,
			Address: targetAddress,
			Owner:   owner,
			Subs:    subs,
		})
	}

	return targets, nil
}

// parseInterval converts sample-interval from either JSON number (nanoseconds) or string format.
// Returns 10s as default if the interval cannot be parsed or is missing.
func parseInterval(val interface{}) time.Duration {
	if val == nil {
		return 10 * time.Second
	}

	// Try parsing as a number (nanoseconds)
	if num, ok := val.(float64); ok {
		if num > 0 {
			return time.Duration(int64(num))
		}
		return 10 * time.Second
	}

	// Try parsing as a string (e.g., "30s")
	if str, ok := val.(string); ok {
		if dur, err := time.ParseDuration(str); err == nil && dur > 0 {
			return dur
		}
	}

	return 10 * time.Second
}

// RunAPI polls every collector every `every` (first poll immediately) until ctx is done.
// Per collector and poll: GET <URL>/api/v1/targets with a 5 second timeout.
//  success: st.SetConfig(c.Name, targets) and st.SetComponent(Component{Name: "collector " + c.Name, OK: true, Detail: "<n> targets"})
//  failure (network error, non-200, bad JSON): st.SetComponent(Component{Name: "collector " + c.Name, OK: false, Detail: err.Error()})
//           and do NOT call SetConfig (keep the previous data).
func RunAPI(ctx context.Context, st *Store, cols []Collector, every time.Duration) {
	ticker := time.NewTicker(every)
	defer ticker.Stop()

	// Poll immediately first
	for _, col := range cols {
		pollCollector(st, col)
	}

	// Then poll at the interval
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			for _, col := range cols {
				pollCollector(st, col)
			}
		}
	}
}

// pollCollector makes one API call to a collector
func pollCollector(st *Store, col Collector) {
	client := &http.Client{
		Timeout: 5 * time.Second,
	}

	url := col.URL + "/api/v1/targets"
	resp, err := client.Get(url)
	if err != nil {
		st.SetComponent(Component{
			Name:   "collector " + col.Name,
			OK:     false,
			Detail: err.Error(),
		})
		return
	}
	defer resp.Body.Close()

	// Check for non-200 status
	if resp.StatusCode != http.StatusOK {
		st.SetComponent(Component{
			Name:   "collector " + col.Name,
			OK:     false,
			Detail: fmt.Sprintf("HTTP %d", resp.StatusCode),
		})
		return
	}

	// Read the response body
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		st.SetComponent(Component{
			Name:   "collector " + col.Name,
			OK:     false,
			Detail: fmt.Sprintf("read response: %v", err),
		})
		return
	}

	// Parse the targets
	targets, err := parseTargets(body, col.Name)
	if err != nil {
		st.SetComponent(Component{
			Name:   "collector " + col.Name,
			OK:     false,
			Detail: err.Error(),
		})
		return
	}

	// Success: update the store with the config and component status
	st.SetConfig(col.Name, targets)
	st.SetComponent(Component{
		Name:   "collector " + col.Name,
		OK:     true,
		Detail: fmt.Sprintf("%d targets", len(targets)),
	})
}
