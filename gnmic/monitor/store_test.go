package main

import (
	"fmt"
	"sync"
	"testing"
	"time"
)

func TestStoreCollectorTargetWithFreshSeen(t *testing.T) {
	// A target from collector source with fresh Seen data gives sub OK and target OK
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	started := time.Date(2024, 1, 1, 11, 0, 0, 0, time.UTC)

	store := NewStore(started)

	// Collector reports target with subscription
	store.SetConfig("gnmic-1", []TargetConfig{
		{
			Name:    "target-1",
			Address: "10.0.0.1:57400",
			Owner:   "gnmic-1",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 30 * time.Second},
			},
		},
	})

	// Record fresh seen event
	store.Seen("target-1", "interfaces", now.Add(-5*time.Second))

	snap := store.Snapshot(now)

	if len(snap.Targets) != 1 {
		t.Fatalf("expected 1 target, got %d", len(snap.Targets))
	}

	tgt := snap.Targets[0]
	if tgt.Status != StatusOK {
		t.Errorf("target status = %v, want %v", tgt.Status, StatusOK)
	}
	if len(tgt.Subs) != 1 {
		t.Fatalf("expected 1 sub, got %d", len(tgt.Subs))
	}
	if tgt.Subs[0].Status != StatusOK {
		t.Errorf("sub status = %v, want %v", tgt.Subs[0].Status, StatusOK)
	}
}

func TestMultipleSubscriptionsInSnapshot(t *testing.T) {
	// Test that a target with multiple subscriptions shows all of them in the snapshot
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	started := time.Date(2024, 1, 1, 11, 0, 0, 0, time.UTC)
	st := NewStore(started)

	// Set a target with 3 subscriptions from both config and collector
	st.SetConfig("config", []TargetConfig{
		{
			Name:    "multi-target",
			Address: "10.0.0.1:57400",
			Owner:   "",
			Subs: []SubConfig{
				{Name: "sub1", Interval: 30 * time.Second},
				{Name: "sub2", Interval: 60 * time.Second},
				{Name: "sub3", Interval: 120 * time.Second},
			},
		},
	})

	st.SetConfig("gnmic-1", []TargetConfig{
		{
			Name:    "multi-target",
			Address: "10.0.0.1:57400",
			Owner:   "gnmic-1",
			Subs: []SubConfig{
				{Name: "sub1", Interval: 30 * time.Second},
				{Name: "sub2", Interval: 60 * time.Second},
				{Name: "sub3", Interval: 120 * time.Second},
			},
		},
	})

	snap := st.Snapshot(now)

	if len(snap.Targets) != 1 {
		t.Fatalf("expected 1 target, got %d", len(snap.Targets))
	}

	tgt := snap.Targets[0]
	if len(tgt.Subs) != 3 {
		t.Fatalf("expected 3 subscriptions, got %d", len(tgt.Subs))
	}

	// Verify all subscription names are present
	subNames := make(map[string]bool)
	for _, sub := range tgt.Subs {
		subNames[sub.Name] = true
	}
	for i := 1; i <= 3; i++ {
		subName := "sub" + string('0'+byte(i))
		if !subNames[subName] {
			t.Errorf("missing subscription %s", subName)
		}
	}
}

func TestTargetWithExplicitListAndTargetWithAllSubs(t *testing.T) {
	// Regression test for issue #50: A target with explicit subscription list and another
	// with no explicit list (using all) should both show all their subscriptions
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	started := time.Date(2024, 1, 1, 11, 0, 0, 0, time.UTC)
	st := NewStore(started)

	// Target 1: explicit list with 2 subscriptions
	st.SetConfig("config", []TargetConfig{
		{
			Name:    "explicit-list-target",
			Address: "10.0.0.1:57400",
			Subs: []SubConfig{
				{Name: "sub1", Interval: 30 * time.Second},
				{Name: "sub2", Interval: 60 * time.Second},
			},
		},
		{
			Name:    "all-subs-target",
			Address: "10.0.0.2:57400",
			Subs: []SubConfig{
				// No explicit list - should have all 3 subscriptions after config parsing
				{Name: "sub1", Interval: 30 * time.Second},
				{Name: "sub2", Interval: 60 * time.Second},
				{Name: "sub3", Interval: 120 * time.Second},
			},
		},
	})

	st.SetConfig("gnmic-1", []TargetConfig{
		{
			Name:    "explicit-list-target",
			Address: "10.0.0.1:57400",
			Owner:   "gnmic-1",
			Subs: []SubConfig{
				{Name: "sub1", Interval: 30 * time.Second},
				{Name: "sub2", Interval: 60 * time.Second},
			},
		},
		{
			Name:    "all-subs-target",
			Address: "10.0.0.2:57400",
			Owner:   "gnmic-1",
			Subs: []SubConfig{
				{Name: "sub1", Interval: 30 * time.Second},
				{Name: "sub2", Interval: 60 * time.Second},
				{Name: "sub3", Interval: 120 * time.Second},
			},
		},
	})

	snap := st.Snapshot(now)

	if len(snap.Targets) != 2 {
		t.Fatalf("expected 2 targets, got %d", len(snap.Targets))
	}

	// Check explicit list target has 2 subscriptions
	var explicitTarget *TargetState
	var allSubsTarget *TargetState
	for i := range snap.Targets {
		if snap.Targets[i].Name == "explicit-list-target" {
			explicitTarget = &snap.Targets[i]
		} else if snap.Targets[i].Name == "all-subs-target" {
			allSubsTarget = &snap.Targets[i]
		}
	}

	if explicitTarget == nil || allSubsTarget == nil {
		t.Fatalf("targets not found in snapshot")
	}

	if len(explicitTarget.Subs) != 2 {
		t.Errorf("explicit-list-target: expected 2 subs, got %d", len(explicitTarget.Subs))
	}

	if len(allSubsTarget.Subs) != 3 {
		t.Errorf("all-subs-target: expected 3 subs, got %d", len(allSubsTarget.Subs))
	}
}

func TestStoreNeverSeenWindow(t *testing.T) {
	// Never seen, within window gives WAITING; past window gives NO_DATA
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)

	// Test WAITING
	started1 := now.Add(-1 * time.Minute) // 1 minute ago
	store1 := NewStore(started1)

	store1.SetConfig("gnmic-1", []TargetConfig{
		{
			Name:  "target-1",
			Owner: "gnmic-1",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 30 * time.Second},
			},
		},
	})

	snap1 := store1.Snapshot(now)
	if len(snap1.Targets) != 1 || len(snap1.Targets[0].Subs) != 1 {
		t.Fatalf("unexpected snapshot structure")
	}
	if snap1.Targets[0].Subs[0].Status != StatusWaiting {
		t.Errorf("never seen within window status = %v, want %v", snap1.Targets[0].Subs[0].Status, StatusWaiting)
	}

	// Test NO_DATA
	started2 := now.Add(-5 * time.Minute) // 5 minutes ago, past 2-minute window
	store2 := NewStore(started2)

	store2.SetConfig("gnmic-1", []TargetConfig{
		{
			Name:  "target-1",
			Owner: "gnmic-1",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 30 * time.Second},
			},
		},
	})

	snap2 := store2.Snapshot(now)
	if len(snap2.Targets) != 1 || len(snap2.Targets[0].Subs) != 1 {
		t.Fatalf("unexpected snapshot structure")
	}
	if snap2.Targets[0].Subs[0].Status != StatusNoData {
		t.Errorf("never seen past window status = %v, want %v", snap2.Targets[0].Subs[0].Status, StatusNoData)
	}
	if snap2.Targets[0].Subs[0].Reason != "no data received" {
		t.Errorf("reason = %q, want %q", snap2.Targets[0].Subs[0].Reason, "no data received")
	}
}

func TestStoreStaleDataReason(t *testing.T) {
	// Stale data gives STALE with reason text "no data for ..."
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	started := time.Date(2024, 1, 1, 11, 0, 0, 0, time.UTC)

	store := NewStore(started)

	store.SetConfig("gnmic-1", []TargetConfig{
		{
			Name:  "target-1",
			Owner: "gnmic-1",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 30 * time.Second},
			},
		},
	})

	// Seen 3 minutes ago (stale: window is 2 min)
	store.Seen("target-1", "interfaces", now.Add(-3*time.Minute))

	snap := store.Snapshot(now)
	if len(snap.Targets) != 1 || len(snap.Targets[0].Subs) != 1 {
		t.Fatalf("unexpected snapshot structure")
	}

	sub := snap.Targets[0].Subs[0]
	if sub.Status != StatusStale {
		t.Errorf("status = %v, want %v", sub.Status, StatusStale)
	}
	if sub.Reason != "no data for 3m0s" {
		t.Errorf("reason = %q, want %q", sub.Reason, "no data for 3m0s")
	}
}

func TestStoreSeenByAddress(t *testing.T) {
	// Seen recorded under address resolves for a target with a name
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	started := time.Date(2024, 1, 1, 11, 0, 0, 0, time.UTC)

	store := NewStore(started)

	// Target has both Name and Address
	store.SetConfig("gnmic-1", []TargetConfig{
		{
			Name:    "target-1",
			Address: "10.0.0.1:57400",
			Owner:   "gnmic-1",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 30 * time.Second},
			},
		},
	})

	// Record seen event using the address, not the name
	store.Seen("10.0.0.1:57400", "interfaces", now.Add(-5*time.Second))

	snap := store.Snapshot(now)
	if len(snap.Targets) != 1 || len(snap.Targets[0].Subs) != 1 {
		t.Fatalf("unexpected snapshot structure")
	}

	sub := snap.Targets[0].Subs[0]
	if sub.Status != StatusOK {
		t.Errorf("status = %v, want %v", sub.Status, StatusOK)
	}
	if sub.Count != 1 {
		t.Errorf("count = %d, want 1", sub.Count)
	}
}

func TestStoreConfigSubUndefined(t *testing.T) {
	// Config sub with Interval 0 gives reason and target ERROR
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	started := time.Date(2024, 1, 1, 11, 0, 0, 0, time.UTC)

	store := NewStore(started)

	// Config has sub with Interval 0 (undefined)
	store.SetConfig("config", []TargetConfig{
		{
			Name:    "target-1",
			Address: "10.0.0.1:57400",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 0}, // Undefined
			},
		},
	})

	// Also add from collector to make target have owner
	store.SetConfig("gnmic-1", []TargetConfig{
		{
			Name:    "target-1",
			Address: "10.0.0.1:57400",
			Owner:   "gnmic-1",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 30 * time.Second},
			},
		},
	})

	snap := store.Snapshot(now)
	if len(snap.Targets) != 1 {
		t.Fatalf("expected 1 target, got %d", len(snap.Targets))
	}

	tgt := snap.Targets[0]
	if tgt.Status != StatusError {
		t.Errorf("target status = %v, want %v", tgt.Status, StatusError)
	}
	if len(tgt.Subs) != 1 {
		t.Fatalf("expected 1 sub, got %d", len(tgt.Subs))
	}
	if tgt.Subs[0].Status != StatusError {
		t.Errorf("sub status = %v, want %v", tgt.Subs[0].Status, StatusError)
	}
	if tgt.Subs[0].Reason != "subscription is not defined in mdt.yaml" {
		t.Errorf("reason = %q, want %q", tgt.Subs[0].Reason, "subscription is not defined in mdt.yaml")
	}
}

func TestStoreConfigSubNotRunning(t *testing.T) {
	// Config sub missing on owner gives "configured but not running on <owner>"
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	started := time.Date(2024, 1, 1, 11, 0, 0, 0, time.UTC)

	store := NewStore(started)

	// Config has sub that owner doesn't list
	store.SetConfig("config", []TargetConfig{
		{
			Name: "target-1",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 30 * time.Second},
			},
		},
	})

	// Collector lists target but not the sub
	store.SetConfig("gnmic-1", []TargetConfig{
		{
			Name:  "target-1",
			Owner: "gnmic-1",
			Subs: []SubConfig{
				{Name: "state", Interval: 30 * time.Second}, // Different sub
			},
		},
	})

	snap := store.Snapshot(now)
	if len(snap.Targets) != 1 {
		t.Fatalf("expected 1 target, got %d", len(snap.Targets))
	}

	// Find the interfaces sub
	tgt := snap.Targets[0]
	var interfacesSub *SubState
	for i, sub := range tgt.Subs {
		if sub.Name == "interfaces" {
			interfacesSub = &tgt.Subs[i]
			break
		}
	}

	if interfacesSub == nil {
		t.Fatalf("interfaces sub not found")
	}

	if interfacesSub.Status != StatusError {
		t.Errorf("status = %v, want %v", interfacesSub.Status, StatusError)
	}
	if interfacesSub.Reason != "configured but not running on gnmic-1" {
		t.Errorf("reason = %q, want %q", interfacesSub.Reason, "configured but not running on gnmic-1")
	}
}

func TestStoreTargetNoCollectorOwns(t *testing.T) {
	// Target only in "config" while another collector called SetConfig gives target reason
	// Before any collector calls SetConfig, no error
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	started := now.Add(-1 * time.Minute) // Only 1 minute ago, so within 2-minute window

	// Test 1: No collector has called SetConfig yet
	store1 := NewStore(started)
	store1.SetConfig("config", []TargetConfig{
		{
			Name: "target-1",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 30 * time.Second},
			},
		},
	})

	snap1 := store1.Snapshot(now)
	if len(snap1.Targets) != 1 {
		t.Fatalf("expected 1 target in snap1, got %d", len(snap1.Targets))
	}
	if snap1.Targets[0].Status != StatusWaiting {
		t.Errorf("snap1 target status = %v, want %v", snap1.Targets[0].Status, StatusWaiting)
	}
	if snap1.Targets[0].Reason != "" {
		t.Errorf("snap1 target reason = %q, want empty", snap1.Targets[0].Reason)
	}

	// Test 2: Collector has called SetConfig but doesn't own this target
	store2 := NewStore(started)
	store2.SetConfig("gnmic-1", []TargetConfig{
		{
			Name: "other-target",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 30 * time.Second},
			},
		},
	})

	store2.SetConfig("config", []TargetConfig{
		{
			Name: "target-1",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 30 * time.Second},
			},
		},
	})

	snap2 := store2.Snapshot(now)
	if len(snap2.Targets) != 2 {
		t.Fatalf("expected 2 targets in snap2, got %d", len(snap2.Targets))
	}

	// Find target-1
	var tgt1 *TargetState
	for i, t := range snap2.Targets {
		if t.Name == "target-1" {
			tgt1 = &snap2.Targets[i]
			break
		}
	}

	if tgt1 == nil {
		t.Fatalf("target-1 not found in snap2")
	}

	if tgt1.Status != StatusError {
		t.Errorf("snap2 target-1 status = %v, want %v", tgt1.Status, StatusError)
	}
	if tgt1.Reason != "no collector owns this target" {
		t.Errorf("snap2 target-1 reason = %q, want %q", tgt1.Reason, "no collector owns this target")
	}
}

func TestStoreTwoCollectorsLatestWins(t *testing.T) {
	// Two collectors list same target: later SetConfig call wins owner
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	started := time.Date(2024, 1, 1, 11, 0, 0, 0, time.UTC)

	store := NewStore(started)

	// First collector sets config
	store.SetConfig("gnmic-1", []TargetConfig{
		{
			Name:  "target-1",
			Owner: "gnmic-1",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 30 * time.Second},
			},
		},
	})

	// Second collector sets config later
	store.SetConfig("gnmic-2", []TargetConfig{
		{
			Name:  "target-1",
			Owner: "gnmic-2",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 30 * time.Second},
			},
		},
	})

	snap := store.Snapshot(now)
	if len(snap.Targets) != 1 {
		t.Fatalf("expected 1 target, got %d", len(snap.Targets))
	}

	if snap.Targets[0].Owner != "gnmic-2" {
		t.Errorf("owner = %q, want %q", snap.Targets[0].Owner, "gnmic-2")
	}
}

func TestStoreIssueOwnerMatching(t *testing.T) {
	// Issue from non-owner collector ignored; one from owner applied
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	started := time.Date(2024, 1, 1, 11, 0, 0, 0, time.UTC)

	store := NewStore(started)

	// Collector gnmic-1 owns target-1
	store.SetConfig("gnmic-1", []TargetConfig{
		{
			Name:  "target-1",
			Owner: "gnmic-1",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 30 * time.Second},
			},
		},
	})

	// Issue from non-owner collector (should be ignored)
	store.SetIssues("gnmic-2", []Issue{
		{
			Collector: "gnmic-2",
			Target:    "target-1",
			Sub:       "interfaces",
			Reason:    "bad data from gnmic-2",
		},
	})

	// Issue from owner collector (should apply)
	store.SetIssues("gnmic-1", []Issue{
		{
			Collector: "gnmic-1",
			Target:    "target-1",
			Sub:       "interfaces",
			Reason:    "collector reported error",
		},
		{
			Collector: "gnmic-1",
			Target:    "target-1",
			Sub:       "",
			Reason:    "target offline",
		},
	})

	snap := store.Snapshot(now)
	if len(snap.Targets) != 1 {
		t.Fatalf("expected 1 target, got %d", len(snap.Targets))
	}

	tgt := snap.Targets[0]
	if len(tgt.Subs) != 1 {
		t.Fatalf("expected 1 sub, got %d", len(tgt.Subs))
	}

	// Sub should have the owner's issue
	if tgt.Subs[0].Reason != "collector reported error" {
		t.Errorf("sub reason = %q, want %q", tgt.Subs[0].Reason, "collector reported error")
	}

	// Target should have the target-level issue
	if tgt.Reason != "target offline" {
		t.Errorf("target reason = %q, want %q", tgt.Reason, "target offline")
	}
	if tgt.Status != StatusError {
		t.Errorf("target status = %v, want %v", tgt.Status, StatusError)
	}
}

func TestStoreComponentUpsert(t *testing.T) {
	// SetComponent upserts and components come back sorted
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	started := time.Date(2024, 1, 1, 11, 0, 0, 0, time.UTC)

	store := NewStore(started)

	// Set some components
	store.SetComponent(Component{Name: "zebra", OK: true, Detail: "up"})
	store.SetComponent(Component{Name: "apple", OK: false, Detail: "down"})
	store.SetComponent(Component{Name: "mongo", OK: true, Detail: "ok"})

	// Update one
	store.SetComponent(Component{Name: "apple", OK: true, Detail: "recovered"})

	snap := store.Snapshot(now)

	if len(snap.Components) != 3 {
		t.Fatalf("expected 3 components, got %d", len(snap.Components))
	}

	// Check sorting and update
	if snap.Components[0].Name != "apple" || !snap.Components[0].OK || snap.Components[0].Detail != "recovered" {
		t.Errorf("component[0] = %+v, want {Name:apple, OK:true, Detail:recovered}", snap.Components[0])
	}
	if snap.Components[1].Name != "mongo" {
		t.Errorf("component[1].Name = %q, want mongo", snap.Components[1].Name)
	}
	if snap.Components[2].Name != "zebra" {
		t.Errorf("component[2].Name = %q, want zebra", snap.Components[2].Name)
	}
}

func TestStoreNilToEmptySlices(t *testing.T) {
	// Slices must never be nil
	store := NewStore(time.Now())
	snap := store.Snapshot(time.Now())

	if snap.Targets == nil {
		t.Errorf("Targets is nil, want empty slice")
	}
	if snap.Components == nil {
		t.Errorf("Components is nil, want empty slice")
	}
}

func TestStoreConcurrentSeen(t *testing.T) {
	// Concurrent Seen calls do not race
	store := NewStore(time.Now())
	now := time.Now()

	store.SetConfig("gnmic-1", []TargetConfig{
		{
			Name:  "target-1",
			Owner: "gnmic-1",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 30 * time.Second},
			},
		},
	})

	// Launch many goroutines calling Seen concurrently
	var wg sync.WaitGroup
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			store.Seen("target-1", "interfaces", now.Add(time.Duration(n)*time.Millisecond))
		}(i)
	}

	wg.Wait()

	snap := store.Snapshot(now.Add(1 * time.Second))
	if len(snap.Targets) != 1 || len(snap.Targets[0].Subs) != 1 {
		t.Fatalf("unexpected snapshot structure")
	}

	// Count should be 100
	if snap.Targets[0].Subs[0].Count != 100 {
		t.Errorf("count = %d, want 100", snap.Targets[0].Subs[0].Count)
	}
}

func TestStoreMergeAddresses(t *testing.T) {
	// When same target key comes from multiple sources, merge addresses
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	started := time.Date(2024, 1, 1, 11, 0, 0, 0, time.UTC)

	store := NewStore(started)

	// Config has one address
	store.SetConfig("config", []TargetConfig{
		{
			Name:    "target-1",
			Address: "10.0.0.1:57400",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 30 * time.Second},
			},
		},
	})

	// Collector reports same target with same name, no change expected
	store.SetConfig("gnmic-1", []TargetConfig{
		{
			Name:    "target-1",
			Address: "10.0.0.1:57400",
			Owner:   "gnmic-1",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 30 * time.Second},
			},
		},
	})

	snap := store.Snapshot(now)
	if len(snap.Targets) != 1 {
		t.Fatalf("expected 1 target, got %d", len(snap.Targets))
	}

	tgt := snap.Targets[0]
	if tgt.Name != "target-1" || tgt.Address != "10.0.0.1:57400" {
		t.Errorf("target = {Name:%q, Address:%q}, want {Name:target-1, Address:10.0.0.1:57400}", tgt.Name, tgt.Address)
	}
}

func TestStoreSeenCountAggregation(t *testing.T) {
	// Seen from both name and address should aggregate counts
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	started := time.Date(2024, 1, 1, 11, 0, 0, 0, time.UTC)

	store := NewStore(started)

	store.SetConfig("gnmic-1", []TargetConfig{
		{
			Name:    "target-1",
			Address: "10.0.0.1:57400",
			Owner:   "gnmic-1",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 30 * time.Second},
			},
		},
	})

	// Record seen by name
	store.Seen("target-1", "interfaces", now.Add(-5*time.Second))
	store.Seen("target-1", "interfaces", now.Add(-4*time.Second))

	// Record seen by address
	store.Seen("10.0.0.1:57400", "interfaces", now.Add(-3*time.Second))

	snap := store.Snapshot(now)
	if len(snap.Targets) != 1 || len(snap.Targets[0].Subs) != 1 {
		t.Fatalf("unexpected snapshot structure")
	}

	sub := snap.Targets[0].Subs[0]
	if sub.Count != 3 {
		t.Errorf("count = %d, want 3", sub.Count)
	}
	// LastSeen should be the most recent
	if sub.LastSeen == nil || *sub.LastSeen != now.Add(-3*time.Second) {
		t.Errorf("LastSeen mismatch")
	}
}

func TestStoreSeenDataHandling(t *testing.T) {
	// Record fresh seen event properly sets count and LastSeen
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	started := time.Date(2024, 1, 1, 11, 0, 0, 0, time.UTC)

	store := NewStore(started)

	store.SetConfig("gnmic-1", []TargetConfig{
		{
			Name:  "target-1",
			Owner: "gnmic-1",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 30 * time.Second},
			},
		},
	})

	// Record multiple seen events
	t1 := now.Add(-10 * time.Second)
	t2 := now.Add(-5 * time.Second)
	t3 := now.Add(-2 * time.Second)

	store.Seen("target-1", "interfaces", t1)
	store.Seen("target-1", "interfaces", t2)
	store.Seen("target-1", "interfaces", t3)

	snap := store.Snapshot(now)
	sub := snap.Targets[0].Subs[0]

	if sub.Count != 3 {
		t.Errorf("count = %d, want 3", sub.Count)
	}
	if sub.LastSeen == nil || *sub.LastSeen != t3 {
		t.Errorf("LastSeen = %v, want %v", sub.LastSeen, t3)
	}
}

func TestStoreOrderingOfTargets(t *testing.T) {
	// Targets sorted by Name (then Address)
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	started := time.Date(2024, 1, 1, 11, 0, 0, 0, time.UTC)

	store := NewStore(started)

	store.SetConfig("config", []TargetConfig{
		{Name: "zulu", Address: "10.0.0.3:57400"},
		{Name: "alpha", Address: "10.0.0.1:57400"},
		{Name: "bravo", Address: "10.0.0.2:57400"},
	})

	snap := store.Snapshot(now)

	if len(snap.Targets) != 3 {
		t.Fatalf("expected 3 targets, got %d", len(snap.Targets))
	}

	if snap.Targets[0].Name != "alpha" || snap.Targets[1].Name != "bravo" || snap.Targets[2].Name != "zulu" {
		t.Errorf("targets not sorted: %v", []string{
			snap.Targets[0].Name, snap.Targets[1].Name, snap.Targets[2].Name,
		})
	}
}

func TestStoreOrderingOfSubs(t *testing.T) {
	// Subs sorted by Name
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	started := time.Date(2024, 1, 1, 11, 0, 0, 0, time.UTC)

	store := NewStore(started)

	store.SetConfig("config", []TargetConfig{
		{
			Name: "target-1",
			Subs: []SubConfig{
				{Name: "zebra", Interval: 30 * time.Second},
				{Name: "alpha", Interval: 30 * time.Second},
				{Name: "bravo", Interval: 30 * time.Second},
			},
		},
	})

	snap := store.Snapshot(now)
	if len(snap.Targets) != 1 {
		t.Fatalf("expected 1 target, got %d", len(snap.Targets))
	}

	if len(snap.Targets[0].Subs) != 3 {
		t.Fatalf("expected 3 subs, got %d", len(snap.Targets[0].Subs))
	}

	if snap.Targets[0].Subs[0].Name != "alpha" || snap.Targets[0].Subs[1].Name != "bravo" || snap.Targets[0].Subs[2].Name != "zebra" {
		t.Errorf("subs not sorted: %v", []string{
			snap.Targets[0].Subs[0].Name, snap.Targets[0].Subs[1].Name, snap.Targets[0].Subs[2].Name,
		})
	}
}

func TestStoreTargetIdentityByAddress(t *testing.T) {
	// Target identity: if Name is empty, use Address as key
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	started := time.Date(2024, 1, 1, 11, 0, 0, 0, time.UTC)

	store := NewStore(started)

	// Set targets with only Address (no Name)
	store.SetConfig("config", []TargetConfig{
		{
			Name:    "",
			Address: "10.0.0.1:57400",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 30 * time.Second},
			},
		},
		{
			Name:    "",
			Address: "10.0.0.2:57400",
			Subs: []SubConfig{
				{Name: "interfaces", Interval: 30 * time.Second},
			},
		},
	})

	snap := store.Snapshot(now)

	if len(snap.Targets) != 2 {
		t.Fatalf("expected 2 targets, got %d", len(snap.Targets))
	}

	// Both targets should use Address as their Name in snapshot
	names := []string{snap.Targets[0].Name, snap.Targets[1].Name}
	if (names[0] != "10.0.0.1:57400" && names[0] != "10.0.0.2:57400") ||
		(names[1] != "10.0.0.1:57400" && names[1] != "10.0.0.2:57400") {
		t.Errorf("target names don't match addresses: %v", names)
	}
}

func TestStoreWorseStatus(t *testing.T) {
	// Target status is Worse of all sub statuses
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	started := now.Add(-1 * time.Minute) // Only 1 minute ago, within 2-minute window

	store := NewStore(started)

	store.SetConfig("gnmic-1", []TargetConfig{
		{
			Name:  "target-1",
			Owner: "gnmic-1",
			Subs: []SubConfig{
				{Name: "sub1", Interval: 30 * time.Second},
				{Name: "sub2", Interval: 30 * time.Second},
				{Name: "sub3", Interval: 30 * time.Second},
			},
		},
	})

	// sub1: OK
	store.Seen("target-1", "sub1", now.Add(-5*time.Second))

	// sub2: STALE
	store.Seen("target-1", "sub2", now.Add(-3*time.Minute))

	// sub3: WAITING (never seen but within window)

	snap := store.Snapshot(now)
	if len(snap.Targets) != 1 {
		t.Fatalf("expected 1 target, got %d", len(snap.Targets))
	}

	tgt := snap.Targets[0]
	// Target status should be STALE (Worse of OK, STALE, WAITING)
	if tgt.Status != StatusStale {
		t.Errorf("target status = %v, want %v", tgt.Status, StatusStale)
	}
}

func TestSetHostUpsert(t *testing.T) {
	// SetHost upserts by name; the snapshot contains the host
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	store := NewStore(now)

	// Set a host
	host1 := HostState{
		Name:  "host-1",
		Level: LevelOK,
		CPU:   MetricState{Name: "cpu", Level: LevelOK, Value: 50},
	}
	store.SetHost(host1)

	snap := store.Snapshot(now)
	if len(snap.Hosts) != 1 {
		t.Fatalf("expected 1 host, got %d", len(snap.Hosts))
	}

	if snap.Hosts[0].Name != "host-1" || snap.Hosts[0].Level != LevelOK {
		t.Errorf("host = %+v, want {Name:host-1, Level:OK}", snap.Hosts[0])
	}

	// Update the same host
	host1Updated := HostState{
		Name:  "host-1",
		Level: LevelWarn,
		CPU:   MetricState{Name: "cpu", Level: LevelWarn, Value: 80},
	}
	store.SetHost(host1Updated)

	snap = store.Snapshot(now)
	if len(snap.Hosts) != 1 {
		t.Fatalf("expected 1 host after update, got %d", len(snap.Hosts))
	}

	if snap.Hosts[0].Level != LevelWarn {
		t.Errorf("host level after update = %v, want %v", snap.Hosts[0].Level, LevelWarn)
	}
}

func TestHostsOrdering(t *testing.T) {
	// Hosts are ordered CRIT before WARN before UNKNOWN before OK, then by name within a level
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	store := NewStore(now)

	// Add hosts in random order
	store.SetHost(HostState{Name: "ok-zebra", Level: LevelOK})
	store.SetHost(HostState{Name: "crit-alpha", Level: LevelCrit})
	store.SetHost(HostState{Name: "warn-bravo", Level: LevelWarn})
	store.SetHost(HostState{Name: "ok-alpha", Level: LevelOK})
	store.SetHost(HostState{Name: "unknown-charlie", Level: LevelUnknown})
	store.SetHost(HostState{Name: "warn-alpha", Level: LevelWarn})
	store.SetHost(HostState{Name: "crit-bravo", Level: LevelCrit})

	snap := store.Snapshot(now)

	if len(snap.Hosts) != 7 {
		t.Fatalf("expected 7 hosts, got %d", len(snap.Hosts))
	}

	expectedOrder := []string{
		"crit-alpha",
		"crit-bravo",
		"warn-alpha",
		"warn-bravo",
		"unknown-charlie",
		"ok-alpha",
		"ok-zebra",
	}

	for i, expected := range expectedOrder {
		if snap.Hosts[i].Name != expected {
			t.Errorf("host[%d] = %q, want %q", i, snap.Hosts[i].Name, expected)
		}
	}
}

func TestHostsEmptySlice(t *testing.T) {
	// Empty store has Hosts of length 0 and not nil
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	store := NewStore(now)

	snap := store.Snapshot(now)

	if snap.Hosts == nil {
		t.Errorf("hosts is nil, want empty slice")
	}
	if len(snap.Hosts) != 0 {
		t.Errorf("hosts length = %d, want 0", len(snap.Hosts))
	}
}

func TestHostsCopyPreventsModification(t *testing.T) {
	// Modifying a returned HostState's Disks slice does not change the store
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	store := NewStore(now)

	originalDisks := []MetricState{
		{Name: "disk1", Level: LevelOK, Value: 50},
		{Name: "disk2", Level: LevelWarn, Value: 80},
	}

	originalNICs := []MetricState{
		{Name: "eth0", Level: LevelOK, Value: 30},
	}

	host := HostState{
		Name:  "host-1",
		Level: LevelWarn,
		Disks: originalDisks,
		NICs:  originalNICs,
	}

	store.SetHost(host)

	// Get the snapshot
	snap := store.Snapshot(now)
	if len(snap.Hosts) != 1 {
		t.Fatalf("expected 1 host, got %d", len(snap.Hosts))
	}

	// Modify the returned host's slices
	snap.Hosts[0].Disks[0].Name = "modified-disk"
	snap.Hosts[0].NICs[0].Value = 999

	// Get another snapshot and verify the store's data is unchanged
	snap2 := store.Snapshot(now)
	if snap2.Hosts[0].Disks[0].Name != "disk1" {
		t.Errorf("disk name in store was modified, got %q, want disk1", snap2.Hosts[0].Disks[0].Name)
	}
	if snap2.Hosts[0].NICs[0].Value != 30 {
		t.Errorf("NIC value in store was modified, got %v, want 30", snap2.Hosts[0].NICs[0].Value)
	}
}

func TestHostsConcurrentSetHostSnapshot(t *testing.T) {
	// Concurrent SetHost and Snapshot calls pass go test -race
	store := NewStore(time.Now())
	now := time.Now()

	// Launch many goroutines calling SetHost concurrently
	var wg sync.WaitGroup
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			host := HostState{
				Name:  fmt.Sprintf("host-%d", n%5), // Only 5 unique hosts
				Level: []HostLevel{LevelOK, LevelWarn, LevelCrit, LevelUnknown}[n%4],
				CPU:   MetricState{Name: "cpu", Level: LevelOK, Value: float64(n)},
			}
			store.SetHost(host)
		}(i)
	}

	// Also call Snapshot concurrently
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_ = store.Snapshot(now)
		}()
	}

	wg.Wait()

	// Verify we have at most 5 hosts (the unique ones)
	snap := store.Snapshot(now)
	if len(snap.Hosts) > 5 {
		t.Errorf("hosts count = %d, want <= 5", len(snap.Hosts))
	}
}
