package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestStatusHandler(t *testing.T) {
	// Build a store with one target and one component
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	st := NewStore(now)

	// Add a target
	st.SetConfig("gnmic-1", []TargetConfig{
		{
			Name:    "test-target",
			Address: "10.0.0.1:57400",
			Owner:   "gnmic-1",
			Subs: []SubConfig{
				{Name: "sub1", Interval: 30 * time.Second},
			},
		},
	})

	// Add a component
	st.SetComponent(Component{
		Name:   "collector gnmic-1",
		OK:     true,
		Detail: "1 target",
	})

	// Create request and response recorder
	req := httptest.NewRequest("GET", "/api/status", nil)
	rec := httptest.NewRecorder()

	// Call handler
	handler := statusHandler(st)
	handler(rec, req)

	// Check response status
	if rec.Code != http.StatusOK {
		t.Errorf("status code = %d, want 200", rec.Code)
	}

	// Check content type
	ct := rec.Header().Get("Content-Type")
	if ct != "application/json" {
		t.Errorf("content type = %q, want %q", ct, "application/json")
	}

	// Decode JSON
	var snap Snapshot
	if err := json.Unmarshal(rec.Body.Bytes(), &snap); err != nil {
		t.Fatalf("decode JSON: %v", err)
	}

	// Verify snapshot contains expected fields
	if len(snap.Targets) < 1 {
		t.Errorf("targets array length = %d, want >= 1", len(snap.Targets))
	}

	// Verify target name
	found := false
	for _, tgt := range snap.Targets {
		if tgt.Name == "test-target" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("target name %q not found in snapshot", "test-target")
	}

	// Verify components
	if len(snap.Components) < 1 {
		t.Errorf("components array length = %d, want >= 1", len(snap.Components))
	}
}

func TestEnv(t *testing.T) {
	// Test unset variable returns default
	t.Setenv("UNSET_VAR", "")
	val := env("UNSET_VAR", "default-value")
	if val != "default-value" {
		t.Errorf("env(%q, %q) = %q, want %q", "UNSET_VAR", "default-value", val, "default-value")
	}

	// Test set variable returns value
	t.Setenv("SET_VAR", "actual-value")
	val = env("SET_VAR", "default-value")
	if val != "actual-value" {
		t.Errorf("env(%q, %q) = %q, want %q", "SET_VAR", "default-value", val, "actual-value")
	}
}

func TestEmptyStore(t *testing.T) {
	// Empty store should give empty targets and components arrays
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	st := NewStore(now)

	snap := st.Snapshot(now)

	// Check targets is empty array, not null
	if snap.Targets == nil {
		t.Errorf("targets is nil, want empty array")
	}
	if len(snap.Targets) != 0 {
		t.Errorf("targets length = %d, want 0", len(snap.Targets))
	}

	// Check components is empty array, not null
	if snap.Components == nil {
		t.Errorf("components is nil, want empty array")
	}
	if len(snap.Components) != 0 {
		t.Errorf("components length = %d, want 0", len(snap.Components))
	}
}
