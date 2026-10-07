package main

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

// TestParseMetricsFixtures tests that the two real fixtures parse without error
func TestParseMetricsFixtures(t *testing.T) {
	fixtures := []string{
		"testdata/metrics_gnmic-1.txt",
		"testdata/metrics_gnmic-2.txt",
	}

	for _, fixture := range fixtures {
		t.Run(fixture, func(t *testing.T) {
			body, err := loadTestFile(fixture)
			if err != nil {
				t.Fatalf("failed to load fixture: %v", err)
			}

			tr := newFailTracker()
			issues, err := parseMetrics("test-collector", bytes.NewReader(body), time.Now(), tr)
			if err != nil {
				t.Fatalf("parseMetrics failed: %v", err)
			}

			// Verify all issues have non-empty Target and Collector
			for _, issue := range issues {
				if issue.Target == "" {
					t.Errorf("issue has empty Target: %+v", issue)
				}
				if issue.Collector == "" {
					t.Errorf("issue has empty Collector: %+v", issue)
				}
			}
		})
	}
}

// TestParseMetricsTargetUp tests gnmic_target_up metric parsing
func TestParseMetricsTargetUp(t *testing.T) {
	tests := []struct {
		name       string
		metrics    string
		wantIssues int
		wantReason string
	}{
		{
			name: "target up with TRANSIENT_FAILURE state",
			metrics: `# HELP gnmic_target_up Has value 1 if the gNMI connection to the target is established; otherwise, 0.
# TYPE gnmic_target_up gauge
gnmic_target_up{name="sw1"} 0
# HELP gnmic_target_connection_state The current gRPC connection state to the target.
# TYPE gnmic_target_connection_state gauge
gnmic_target_connection_state{name="sw1"} 4
`,
			wantIssues: 1,
			wantReason: "gNMI connection down (TRANSIENT_FAILURE)",
		},
		{
			name: "target up with no state metric",
			metrics: `# HELP gnmic_target_up Has value 1 if the gNMI connection to the target is established; otherwise, 0.
# TYPE gnmic_target_up gauge
gnmic_target_up{name="sw1"} 0
`,
			wantIssues: 1,
			wantReason: "gNMI connection down (no state)",
		},
		{
			name: "target up returns no issue",
			metrics: `# HELP gnmic_target_up Has value 1 if the gNMI connection to the target is established; otherwise, 0.
# TYPE gnmic_target_up gauge
gnmic_target_up{name="sw1"} 1
`,
			wantIssues: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			tr := newFailTracker()
			issues, err := parseMetrics("test-col", bytes.NewReader([]byte(tt.metrics)), time.Now(), tr)
			if err != nil {
				t.Fatalf("parseMetrics failed: %v", err)
			}

			if len(issues) != tt.wantIssues {
				t.Errorf("got %d issues, want %d", len(issues), tt.wantIssues)
			}

			if tt.wantIssues > 0 && len(issues) > 0 {
				if issues[0].Reason != tt.wantReason {
					t.Errorf("got reason %q, want %q", issues[0].Reason, tt.wantReason)
				}
				if issues[0].Target != "sw1" {
					t.Errorf("got target %q, want %q", issues[0].Target, "sw1")
				}
				if issues[0].Sub != "" {
					t.Errorf("got sub %q, want empty", issues[0].Sub)
				}
			}
		})
	}
}

// TestParseMetricsFailedCounter tests the failed subscribe counter tracking
func TestParseMetricsFailedCounter(t *testing.T) {
	tr := newFailTracker()
	now := time.Now()

	// First parse with value 3 returns no issue (baseline)
	metrics1 := `# HELP gnmic_subscribe_number_of_failed_subscribe_request_messages_total Total number of failed subscribe requests
# TYPE gnmic_subscribe_number_of_failed_subscribe_request_messages_total counter
gnmic_subscribe_number_of_failed_subscribe_request_messages_total{source="target1",subscription="sub1"} 3
`

	issues, err := parseMetrics("col1", bytes.NewReader([]byte(metrics1)), now, tr)
	if err != nil {
		t.Fatalf("parseMetrics failed: %v", err)
	}
	if len(issues) != 0 {
		t.Errorf("first parse: got %d issues, want 0", len(issues))
	}

	// Second parse a minute later with value 4 returns one issue
	now2 := now.Add(time.Minute)
	metrics2 := `# HELP gnmic_subscribe_number_of_failed_subscribe_request_messages_total Total number of failed subscribe requests
# TYPE gnmic_subscribe_number_of_failed_subscribe_request_messages_total counter
gnmic_subscribe_number_of_failed_subscribe_request_messages_total{source="target1",subscription="sub1"} 4
`

	issues, err = parseMetrics("col1", bytes.NewReader([]byte(metrics2)), now2, tr)
	if err != nil {
		t.Fatalf("parseMetrics failed: %v", err)
	}
	if len(issues) != 1 {
		t.Errorf("second parse: got %d issues, want 1", len(issues))
	}
	if issues[0].Reason != "subscribe request failed (4 total)" {
		t.Errorf("got reason %q, want %q", issues[0].Reason, "subscribe request failed (4 total)")
	}

	// Third parse 11 minutes after the increase with value 4 returns none
	now3 := now.Add(11 * time.Minute)
	issues, err = parseMetrics("col1", bytes.NewReader([]byte(metrics2)), now3, tr)
	if err != nil {
		t.Fatalf("parseMetrics failed: %v", err)
	}
	if len(issues) != 0 {
		t.Errorf("third parse (11 min after increase): got %d issues, want 0", len(issues))
	}

	// Parse with unchanged value returns none
	issues, err = parseMetrics("col1", bytes.NewReader([]byte(metrics2)), now2.Add(5*time.Minute), tr)
	if err != nil {
		t.Fatalf("parseMetrics failed: %v", err)
	}
	if len(issues) != 0 {
		t.Errorf("parse with unchanged value: got %d issues, want 0", len(issues))
	}
}

// TestParseMetricsGarbageInput tests that garbage input returns an error
func TestParseMetricsGarbageInput(t *testing.T) {
	tr := newFailTracker()
	metrics := "this is not valid exposition text"

	_, err := parseMetrics("col1", bytes.NewReader([]byte(metrics)), time.Now(), tr)
	if err == nil {
		t.Errorf("parseMetrics should fail on garbage input")
	}
}

// TestRunMetrics tests RunMetrics against an httptest.Server
func TestRunMetrics(t *testing.T) {
	// Create a test server that serves metrics
	metricsBody := `# HELP gnmic_target_up Has value 1 if the gNMI connection to the target is established; otherwise, 0.
# TYPE gnmic_target_up gauge
gnmic_target_up{name="sw1"} 0
# HELP gnmic_target_connection_state The current gRPC connection state to the target.
# TYPE gnmic_target_connection_state gauge
gnmic_target_connection_state{name="sw1"} 4
`

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/metrics" {
			w.Header().Set("Content-Type", "text/plain; version=0.0.4")
			w.Write([]byte(metricsBody))
		} else {
			http.NotFound(w, r)
		}
	}))
	defer server.Close()

	// Create a store and set config
	st := NewStore(time.Now().Add(-time.Hour))
	st.SetConfig("gnmic-1", []TargetConfig{
		{
			Name:    "sw1",
			Address: "192.168.1.1:830",
			Owner:   "gnmic-1",
		},
	})

	// Create collector pointing to test server
	cols := []Collector{
		{
			Name: "gnmic-1",
			URL:  server.URL,
		},
	}

	// Run metrics with a short interval
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	go RunMetrics(ctx, st, cols, 100*time.Millisecond)

	// Wait for first scrape to complete
	time.Sleep(200 * time.Millisecond)

	// Check the snapshot
	snap := st.Snapshot(time.Now())

	// Find the target
	var targetFound bool
	for _, target := range snap.Targets {
		if target.Name == "sw1" {
			targetFound = true
			if target.Status != StatusError {
				t.Errorf("target should have ErrorStatus, got %s", target.Status)
			}
			if !strings.Contains(target.Reason, "gNMI connection down") {
				t.Errorf("reason should contain 'gNMI connection down', got %q", target.Reason)
			}
		}
	}

	if !targetFound {
		t.Errorf("target sw1 not found in snapshot")
	}
}

// loadTestFile loads a test fixture file
func loadTestFile(name string) ([]byte, error) {
	// In test context, read the actual file
	return os.ReadFile(name)
}
