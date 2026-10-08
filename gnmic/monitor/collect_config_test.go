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

	// Find ibk-lab-sw98 target
	var sw98 *TargetConfig
	for i := range targets {
		if targets[i].Name == "ibk-lab-sw98" {
			sw98 = &targets[i]
			break
		}
	}
	if sw98 == nil {
		t.Fatalf("target 'ibk-lab-sw98' not found")
	}
	if len(sw98.Subs) != 7 {
		t.Errorf("ibk-lab-sw98: expected 7 subs, got %d", len(sw98.Subs))
	}
	for _, sub := range sw98.Subs {
		if sub.Interval <= 0 {
			t.Errorf("ibk-lab-sw98.%s: expected Interval > 0, got %v", sub.Name, sub.Interval)
		}
	}

	// Find Lab-IBK-PA560-2 target
	var pa560 *TargetConfig
	for i := range targets {
		if targets[i].Name == "Lab-IBK-PA560-2" {
			pa560 = &targets[i]
			break
		}
	}
	if pa560 == nil {
		t.Fatalf("target 'Lab-IBK-PA560-2' not found")
	}
	if len(pa560.Subs) != 3 {
		t.Errorf("Lab-IBK-PA560-2: expected 3 subs, got %d", len(pa560.Subs))
	}
	want := map[string]time.Duration{
		"panos_if_stats":      30 * time.Second,
		"panos_cpu_stats":     5 * time.Minute,
		"panos_session_stats": time.Minute,
	}
	for _, sub := range pa560.Subs {
		if w, ok := want[sub.Name]; !ok || sub.Interval != w {
			t.Errorf("Lab-IBK-PA560-2.%s: expected Interval %v, got %v", sub.Name, w, sub.Interval)
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
