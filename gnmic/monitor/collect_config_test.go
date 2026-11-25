package main

import (
	"context"
	"os"
	"testing"
	"time"
)

func TestParseConfigInlineYAML(t *testing.T) {
	yaml := `
targets:
  172.24.88.157:9339:
    name: "test-fw"
    subscriptions:
      - sub-with-interval
      - sub-without-interval
      - sub-undefined

subscriptions:
  sub-with-interval:
    sample-interval: 1h
  sub-without-interval:
    sample-interval: null
`

	targets, err := ParseConfig([]byte(yaml))
	if err != nil {
		t.Fatalf("ParseConfig failed: %v", err)
	}

	if len(targets) != 1 {
		t.Fatalf("expected 1 target, got %d", len(targets))
	}

	target := targets[0]
	if target.Name != "test-fw" {
		t.Errorf("expected Name 'test-fw', got %q", target.Name)
	}
	if target.Address != "172.24.88.157:9339" {
		t.Errorf("expected Address '172.24.88.157:9339', got %q", target.Address)
	}
	if target.Owner != "" {
		t.Errorf("expected empty Owner, got %q", target.Owner)
	}

	if len(target.Subs) != 3 {
		t.Fatalf("expected 3 subs, got %d", len(target.Subs))
	}

	// Check subscriptions and their intervals
	if target.Subs[0].Name != "sub-with-interval" {
		t.Errorf("sub[0].Name: expected 'sub-with-interval', got %q", target.Subs[0].Name)
	}
	if target.Subs[0].Interval != 1*time.Hour {
		t.Errorf("sub[0].Interval: expected 1h, got %v", target.Subs[0].Interval)
	}

	if target.Subs[1].Name != "sub-without-interval" {
		t.Errorf("sub[1].Name: expected 'sub-without-interval', got %q", target.Subs[1].Name)
	}
	if target.Subs[1].Interval != 10*time.Second {
		t.Errorf("sub[1].Interval: expected 10s, got %v", target.Subs[1].Interval)
	}

	if target.Subs[2].Name != "sub-undefined" {
		t.Errorf("sub[2].Name: expected 'sub-undefined', got %q", target.Subs[2].Name)
	}
	if target.Subs[2].Interval != 0 {
		t.Errorf("sub[2].Interval: expected 0, got %v", target.Subs[2].Interval)
	}
}

func TestParseConfigTargetWithoutName(t *testing.T) {
	yaml := `
targets:
  192.168.1.1:57400:
    subscriptions:
      - sub1

subscriptions:
  sub1:
    sample-interval: 30s
`

	targets, err := ParseConfig([]byte(yaml))
	if err != nil {
		t.Fatalf("ParseConfig failed: %v", err)
	}

	if len(targets) != 1 {
		t.Fatalf("expected 1 target, got %d", len(targets))
	}

	target := targets[0]
	if target.Name != "192.168.1.1:57400" {
		t.Errorf("expected Name to be address '192.168.1.1:57400', got %q", target.Name)
	}
	if target.Address != "192.168.1.1:57400" {
		t.Errorf("expected Address '192.168.1.1:57400', got %q", target.Address)
	}
}

func TestParseConfigInvalidYAML(t *testing.T) {
	yaml := `
invalid: yaml: content: [
`

	_, err := ParseConfig([]byte(yaml))
	if err == nil {
		t.Fatalf("expected error for invalid YAML, got nil")
	}
}

func TestParseConfigUnparsableSampleInterval(t *testing.T) {
	yaml := `
targets:
  172.24.88.157:9339:
    subscriptions:
      - sub1

subscriptions:
  sub1:
    sample-interval: "not a duration"
`

	_, err := ParseConfig([]byte(yaml))
	if err == nil {
		t.Fatalf("expected error for unparsable sample-interval, got nil")
	}
}

func TestParseConfigRealFile(t *testing.T) {
	data, err := os.ReadFile("../config/mdt.yaml")
	if err != nil {
		t.Skipf("real config file not found: %v", err)
	}

	targets, err := ParseConfig(data)
	if err != nil {
		t.Fatalf("ParseConfig failed: %v", err)
	}

	// The static list keeps only devices not in NetBox (the WLCs); the rest come from the NetBox loader.
	var wlc *TargetConfig
	for i := range targets {
		if targets[i].Name == "nk-home-ewlc01" {
			wlc = &targets[i]
			break
		}
	}
	if wlc == nil {
		t.Fatalf("target 'nk-home-ewlc01' not found")
	}
	if len(wlc.Subs) != 7 {
		t.Errorf("nk-home-ewlc01: expected 7 subs, got %d", len(wlc.Subs))
	}
	for _, sub := range wlc.Subs {
		if sub.Interval <= 0 {
			t.Errorf("nk-home-ewlc01.%s: expected Interval > 0, got %v", sub.Name, sub.Interval)
		}
	}
}

func TestParseConfigNoSubscriptionsListUsesAll(t *testing.T) {
	// Target without explicit subscriptions list should use ALL defined subscriptions
	yaml := `
targets:
  10.0.0.1:57400:
    name: target-1
subscriptions:
  sub1:
    sample-interval: 10s
  sub2:
    sample-interval: 20s
  sub3:
    sample-interval: 30s
`
	targets, err := ParseConfig([]byte(yaml))
	if err != nil {
		t.Fatalf("ParseConfig failed: %v", err)
	}
	if len(targets) != 1 {
		t.Fatalf("expected 1 target, got %d", len(targets))
	}

	// Should have all 3 subscriptions
	if len(targets[0].Subs) != 3 {
		t.Errorf("subscriptions count = %d, want 3", len(targets[0].Subs))
	}

	// Verify names
	subNames := make(map[string]bool)
	for _, sub := range targets[0].Subs {
		subNames[sub.Name] = true
	}
	for i := 1; i <= 3; i++ {
		subName := "sub" + string('0'+byte(i))
		if !subNames[subName] {
			t.Errorf("missing subscription %s", subName)
		}
	}
}

func TestRunConfig(t *testing.T) {
	// Create a temporary file
	yaml := `
targets:
  172.24.88.157:9339:
    name: "test-fw"
    subscriptions:
      - sub1

subscriptions:
  sub1:
    sample-interval: 30s
`

	tmpFile, err := os.CreateTemp("", "test-config-*.yaml")
	if err != nil {
		t.Fatalf("failed to create temp file: %v", err)
	}
	defer os.Remove(tmpFile.Name())

	if _, err := tmpFile.Write([]byte(yaml)); err != nil {
		t.Fatalf("failed to write temp file: %v", err)
	}
	if err := tmpFile.Close(); err != nil {
		t.Fatalf("failed to close temp file: %v", err)
	}

	// Create a store and run config with a short interval
	st := NewStore(time.Now())
	ctx, cancel := context.WithCancel(context.Background())

	// Start RunConfig in a goroutine
	go RunConfig(ctx, st, tmpFile.Name(), 10*time.Millisecond)

	// Wait a moment for initial read
	time.Sleep(50 * time.Millisecond)

	// Get a snapshot
	snap := st.Snapshot(time.Now())
	if len(snap.Targets) != 1 {
		t.Errorf("expected 1 target in snapshot, got %d", len(snap.Targets))
	}
	if len(snap.Targets) > 0 && snap.Targets[0].Name != "test-fw" {
		t.Errorf("expected target name 'test-fw', got %q", snap.Targets[0].Name)
	}

	// Cancel context
	cancel()

	// Wait a moment for goroutine to exit
	time.Sleep(50 * time.Millisecond)
}

// NetBox mode: mdt.yaml has no `targets:`, so the intended targets are the ones the collectors loaded.
func TestRunConfigNetBoxModeUsesCollectorTargets(t *testing.T) {
	yaml := `
subscriptions:
  sub1:
    sample-interval: 30s
`
	tmpFile, err := os.CreateTemp("", "test-config-netbox-*.yaml")
	if err != nil {
		t.Fatalf("failed to create temp file: %v", err)
	}
	defer os.Remove(tmpFile.Name())
	if _, err := tmpFile.Write([]byte(yaml)); err != nil {
		t.Fatalf("failed to write temp file: %v", err)
	}
	tmpFile.Close()

	st := NewStore(time.Now())
	st.SetConfig("gnmic-1", []TargetConfig{{Name: "ibk-lab-sw98", Address: "172.24.80.240:57400", Owner: "gnmic-1",
		Subs: []SubConfig{{Name: "sub1", Interval: 30 * time.Second}}}})

	// Cancelled context: RunConfig reads the file once and returns
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	RunConfig(ctx, st, tmpFile.Name(), time.Hour)

	cfg := st.targets["config"]
	if len(cfg) != 1 {
		t.Fatalf("expected 1 intended target from the collectors, got %d", len(cfg))
	}
	if tgt := cfg["ibk-lab-sw98"]; tgt.Owner != "" || tgt.Address != "172.24.80.240:57400" || len(tgt.Subs) != 1 {
		t.Errorf("unexpected intended target: %+v", tgt)
	}
}
