package main

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"
)

// TestParseTargetsFixture tests parseTargets on real fixture files
func TestParseTargetsFixture(t *testing.T) {
	fixtures := []string{
		"testdata/api_targets_gnmic-1.json",
		"testdata/api_targets_gnmic-2.json",
	}

	for _, fixture := range fixtures {
		t.Run(fixture, func(t *testing.T) {
			body, err := os.ReadFile(fixture)
			if err != nil {
				t.Fatalf("failed to read fixture: %v", err)
			}

			targets, err := parseTargets(body, "test-owner")
			if err != nil {
				t.Fatalf("parseTargets failed: %v", err)
			}

			if len(targets) == 0 {
				t.Fatal("parseTargets returned no targets")
			}

			// Verify all targets have required fields
			for i, target := range targets {
				if target.Name == "" {
					t.Errorf("target %d: Name is empty", i)
				}
				if target.Address == "" {
					t.Errorf("target %d: Address is empty", i)
				}
				if target.Owner != "test-owner" {
					t.Errorf("target %d: Owner is %q, want %q", i, target.Owner, "test-owner")
				}

				// Verify all subscriptions have positive intervals
				for j, sub := range target.Subs {
					if sub.Interval <= 0 {
						t.Errorf("target %d, sub %d: Interval is %v, want > 0", i, j, sub.Interval)
					}
				}
			}
		})
	}
}

// TestParseTargetsIntervalFormats tests both numeric and string interval formats
func TestParseTargetsIntervalFormats(t *testing.T) {
	// Test numeric nanoseconds (30 seconds = 30000000000 ns)
	numericJSON := []byte(`{
		"test-target-1": {
			"config": {
				"name": "test-target-1",
				"address": "172.24.80.240:57400",
				"subscriptions": ["sub1"]
			},
			"subscriptions": {
				"sub1": {
					"name": "sub1",
					"sample-interval": 30000000000
				}
			}
		}
	}`)

	targets, err := parseTargets(numericJSON, "test-owner")
	if err != nil {
		t.Fatalf("parseTargets failed: %v", err)
	}
	if len(targets) != 1 || len(targets[0].Subs) != 1 {
		t.Fatalf("expected 1 target with 1 sub, got %d targets with %d subs", len(targets), len(targets[0].Subs))
	}
	if targets[0].Subs[0].Interval != 30*time.Second {
		t.Errorf("numeric interval: got %v, want %v", targets[0].Subs[0].Interval, 30*time.Second)
	}

	// Test string duration format
	stringJSON := []byte(`{
		"test-target-2": {
			"config": {
				"name": "test-target-2",
				"address": "172.24.80.241:57400",
				"subscriptions": ["sub2"]
			},
			"subscriptions": {
				"sub2": {
					"name": "sub2",
					"sample-interval": "30s"
				}
			}
		}
	}`)

	targets, err = parseTargets(stringJSON, "test-owner")
	if err != nil {
		t.Fatalf("parseTargets failed: %v", err)
	}
	if len(targets) != 1 || len(targets[0].Subs) != 1 {
		t.Fatalf("expected 1 target with 1 sub, got %d targets with %d subs", len(targets), len(targets[0].Subs))
	}
	if targets[0].Subs[0].Interval != 30*time.Second {
		t.Errorf("string interval: got %v, want %v", targets[0].Subs[0].Interval, 30*time.Second)
	}
}

// TestParseTargetsNoInterval tests default interval when sample-interval is missing
func TestParseTargetsNoInterval(t *testing.T) {
	noIntervalJSON := []byte(`{
		"test-target-3": {
			"config": {
				"name": "test-target-3",
				"address": "172.24.80.242:57400",
				"subscriptions": ["sub3"]
			},
			"subscriptions": {
				"sub3": {
					"name": "sub3"
				}
			}
		}
	}`)

	targets, err := parseTargets(noIntervalJSON, "test-owner")
	if err != nil {
		t.Fatalf("parseTargets failed: %v", err)
	}
	if len(targets) != 1 || len(targets[0].Subs) != 1 {
		t.Fatalf("expected 1 target with 1 sub, got %d targets with %d subs", len(targets), len(targets[0].Subs))
	}
	if targets[0].Subs[0].Interval != 10*time.Second {
		t.Errorf("default interval: got %v, want %v", targets[0].Subs[0].Interval, 10*time.Second)
	}
}

// TestParseTargetsInvalidJSON tests error handling for invalid JSON
func TestParseTargetsInvalidJSON(t *testing.T) {
	invalidJSON := []byte(`{invalid json}`)
	_, err := parseTargets(invalidJSON, "test-owner")
	if err == nil {
		t.Fatal("parseTargets should have returned an error for invalid JSON")
	}
}

// TestRunAPISuccess tests RunAPI with successful API response
func TestRunAPISuccess(t *testing.T) {
	// Load a real fixture for the response
	fixtureBody, err := os.ReadFile("testdata/api_targets_gnmic-1.json")
	if err != nil {
		t.Fatalf("failed to read fixture: %v", err)
	}

	// Create an httptest server that serves the fixture
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/targets" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write(fixtureBody)
	}))
	defer server.Close()

	// Create a store and run the poller
	st := NewStore(time.Now())
	col := Collector{Name: "gnmic-1", URL: server.URL}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Run for one poll cycle
	go RunAPI(ctx, st, []Collector{col}, 50*time.Millisecond)

	// Wait for the first poll
	time.Sleep(100 * time.Millisecond)

	// Check that the store has the targets and component status
	snap := st.Snapshot(time.Now())

	// Check component
	var foundComponent *Component
	for i := range snap.Components {
		if snap.Components[i].Name == "collector gnmic-1" {
			foundComponent = &snap.Components[i]
			break
		}
	}

	if foundComponent == nil {
		t.Fatal("component 'collector gnmic-1' not found")
	}
	if !foundComponent.OK {
		t.Errorf("component OK: got false, want true")
	}

	// Check targets are in the snapshot
	if len(snap.Targets) == 0 {
		t.Fatal("no targets in snapshot")
	}

	// Cancel and wait for goroutine to finish
	cancel()
	time.Sleep(100 * time.Millisecond)
}

// TestRunAPIError tests RunAPI with HTTP error response
func TestRunAPIError(t *testing.T) {
	// Create an httptest server that returns HTTP 500
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	// Create a store and run the poller
	st := NewStore(time.Now())
	col := Collector{Name: "gnmic-2", URL: server.URL}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Run for one poll cycle
	go RunAPI(ctx, st, []Collector{col}, 50*time.Millisecond)

	// Wait for the first poll
	time.Sleep(100 * time.Millisecond)

	// Check that the component has OK=false
	snap := st.Snapshot(time.Now())

	var foundComponent *Component
	for i := range snap.Components {
		if snap.Components[i].Name == "collector gnmic-2" {
			foundComponent = &snap.Components[i]
			break
		}
	}

	if foundComponent == nil {
		t.Fatal("component 'collector gnmic-2' not found")
	}
	if foundComponent.OK {
		t.Errorf("component OK: got true, want false")
	}

	// Check that no targets are in the snapshot (SetConfig should not have been called)
	if len(snap.Targets) > 0 {
		t.Errorf("targets should be empty after error, but got %d", len(snap.Targets))
	}

	// Cancel and wait for goroutine to finish
	cancel()
	time.Sleep(100 * time.Millisecond)
}

// TestRunAPIMultiplePollsAndCancel tests that RunAPI stops when context is cancelled
func TestRunAPIMultiplePollsAndCancel(t *testing.T) {
	callCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{}`))
	}))
	defer server.Close()

	st := NewStore(time.Now())
	col := Collector{Name: "gnmic-test", URL: server.URL}

	ctx, cancel := context.WithTimeout(context.Background(), 150*time.Millisecond)
	defer cancel()

	RunAPI(ctx, st, []Collector{col}, 50*time.Millisecond)

	// Should have been called multiple times (immediate + at least 2 intervals within the timeout)
	if callCount < 2 {
		t.Errorf("expected at least 2 polls, got %d", callCount)
	}
}

// TestTargetNameFallback tests that target name falls back to address if name is empty
func TestTargetNameFallback(t *testing.T) {
	jsonBody := []byte(`{
		"target-addr": {
			"config": {
				"name": "",
				"address": "192.168.1.1:9339",
				"subscriptions": []
			},
			"subscriptions": {}
		}
	}`)

	targets, err := parseTargets(jsonBody, "test-owner")
	if err != nil {
		t.Fatalf("parseTargets failed: %v", err)
	}

	if len(targets) != 1 {
		t.Fatalf("expected 1 target, got %d", len(targets))
	}

	if targets[0].Name != "192.168.1.1:9339" {
		t.Errorf("target name: got %q, want %q", targets[0].Name, "192.168.1.1:9339")
	}
}

// TestParseInterval tests the parseInterval function directly
func TestParseInterval(t *testing.T) {
	tests := []struct {
		name     string
		input    interface{}
		expected time.Duration
	}{
		{"nil", nil, 10 * time.Second},
		{"numeric nanoseconds", 60000000000.0, 60 * time.Second},
		{"string duration", "45s", 45 * time.Second},
		{"invalid string", "invalid", 10 * time.Second},
		{"zero", 0.0, 10 * time.Second},
		{"negative", -1000.0, 10 * time.Second},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := parseInterval(tt.input)
			if result != tt.expected {
				t.Errorf("got %v, want %v", result, tt.expected)
			}
		})
	}
}

// TestParseTargetsWithMultipleSubs tests a target with multiple subscriptions
func TestParseTargetsWithMultipleSubs(t *testing.T) {
	jsonBody := []byte(`{
		"multi-sub-target": {
			"config": {
				"name": "multi-sub-target",
				"address": "10.0.0.1:9339",
				"subscriptions": ["sub1", "sub2", "sub3"]
			},
			"subscriptions": {
				"sub1": {"name": "sub1", "sample-interval": 10000000000},
				"sub2": {"name": "sub2", "sample-interval": "20s"},
				"sub3": {"name": "sub3"}
			}
		}
	}`)

	targets, err := parseTargets(jsonBody, "test-owner")
	if err != nil {
		t.Fatalf("parseTargets failed: %v", err)
	}

	if len(targets) != 1 {
		t.Fatalf("expected 1 target, got %d", len(targets))
	}

	target := targets[0]
	if len(target.Subs) != 3 {
		t.Fatalf("expected 3 subscriptions, got %d", len(target.Subs))
	}

	// Check each subscription's interval
	if target.Subs[0].Interval != 10*time.Second {
		t.Errorf("sub1 interval: got %v, want %v", target.Subs[0].Interval, 10*time.Second)
	}
	if target.Subs[1].Interval != 20*time.Second {
		t.Errorf("sub2 interval: got %v, want %v", target.Subs[1].Interval, 20*time.Second)
	}
	if target.Subs[2].Interval != 10*time.Second {
		t.Errorf("sub3 interval (default): got %v, want %v", target.Subs[2].Interval, 10*time.Second)
	}
}

// TestParseTargetsNoSubscriptionsListUsesAll tests that targets without explicit subscriptions
// use all available subscriptions (gnmic's rule)
func TestParseTargetsNoSubscriptionsListUsesAll(t *testing.T) {
	jsonBody := []byte(`{
		"multi-sub-target": {
			"config": {
				"name": "multi-sub-target",
				"address": "10.0.0.1:9339",
				"subscriptions": []
			},
			"subscriptions": {
				"sub1": {"name": "sub1", "sample-interval": 10000000000},
				"sub2": {"name": "sub2", "sample-interval": "20s"},
				"sub3": {"name": "sub3"}
			}
		}
	}`)

	targets, err := parseTargets(jsonBody, "test-owner")
	if err != nil {
		t.Fatalf("parseTargets failed: %v", err)
	}

	if len(targets) != 1 {
		t.Fatalf("expected 1 target, got %d", len(targets))
	}

	target := targets[0]
	if len(target.Subs) != 3 {
		t.Fatalf("expected 3 subscriptions, got %d", len(target.Subs))
	}

	// Check that all subscriptions are present
	subNames := make(map[string]bool)
	for _, sub := range target.Subs {
		subNames[sub.Name] = true
	}
	for _, name := range []string{"sub1", "sub2", "sub3"} {
		if !subNames[name] {
			t.Errorf("missing subscription %s", name)
		}
	}
}

// BenchmarkParseTargets benchmarks the parseTargets function with a fixture
func BenchmarkParseTargets(b *testing.B) {
	body, err := os.ReadFile("testdata/api_targets_gnmic-1.json")
	if err != nil {
		b.Fatalf("failed to read fixture: %v", err)
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, _ = parseTargets(bytes.Clone(body), "owner")
	}
}
