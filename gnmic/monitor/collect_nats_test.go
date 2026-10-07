package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestParseEventsFromFixtures(t *testing.T) {
	fixtures := []string{
		"nats_mdt_1.json",
		"nats_mdt_2.json",
		"nats_mdt_3.json",
		"nats_mdt_4.json",
		"nats_mdt_5.json",
	}

	for _, fixture := range fixtures {
		t.Run(fixture, func(t *testing.T) {
			data, err := os.ReadFile(filepath.Join("testdata", fixture))
			if err != nil {
				t.Fatalf("failed to read fixture: %v", err)
			}

			events, err := parseEvents(data)
			if err != nil {
				t.Fatalf("parseEvents failed: %v", err)
			}

			if len(events) == 0 {
				t.Fatalf("expected at least one event, got %d", len(events))
			}

			// Check that eventKey returns ok for at least one event
			hasValidKey := false
			for _, event := range events {
				_, _, ok := eventKey(event)
				if ok {
					hasValidKey = true
					break
				}
			}

			if !hasValidKey {
				t.Fatalf("no event in fixture had a valid (target, sub) key")
			}
		})
	}
}

func TestParseEventsSingleObject(t *testing.T) {
	data := []byte(`{"name":"test","timestamp":1234567890,"tags":{"source":"target1","subscription-name":"sub1"},"values":{}}`)
	events, err := parseEvents(data)
	if err != nil {
		t.Fatalf("parseEvents failed: %v", err)
	}

	if len(events) != 1 {
		t.Fatalf("expected 1 event, got %d", len(events))
	}

	if events[0].Name != "test" {
		t.Fatalf("expected name 'test', got %q", events[0].Name)
	}
}

func TestParseEventsArray(t *testing.T) {
	data := []byte(`[{"name":"test1","timestamp":1234567890,"tags":{"source":"target1"},"values":{}},{"name":"test2","timestamp":1234567891,"tags":{"source":"target2"},"values":{}}]`)
	events, err := parseEvents(data)
	if err != nil {
		t.Fatalf("parseEvents failed: %v", err)
	}

	if len(events) != 2 {
		t.Fatalf("expected 2 events, got %d", len(events))
	}

	if events[0].Name != "test1" || events[1].Name != "test2" {
		t.Fatalf("unexpected event names")
	}
}

func TestParseEventsInvalidJSON(t *testing.T) {
	data := []byte("not json")
	_, err := parseEvents(data)
	if err == nil {
		t.Fatalf("expected error for invalid JSON, got nil")
	}
}

func TestParseEventsEmptyPayload(t *testing.T) {
	data := []byte("")
	_, err := parseEvents(data)
	if err == nil {
		t.Fatalf("expected error for empty payload, got nil")
	}
}

func TestEventKeyWithTags(t *testing.T) {
	event := Event{
		Name:      "test",
		Timestamp: 1234567890,
		Tags: map[string]string{
			"source":              "target1",
			"subscription-name":   "sub1",
		},
	}

	target, sub, ok := eventKey(event)
	if !ok {
		t.Fatalf("expected ok=true")
	}

	if target != "target1" {
		t.Fatalf("expected target 'target1', got %q", target)
	}

	if sub != "sub1" {
		t.Fatalf("expected sub 'sub1', got %q", sub)
	}
}

func TestEventKeyMissingSubscriptionTag(t *testing.T) {
	event := Event{
		Name:      "fallback_sub",
		Timestamp: 1234567890,
		Tags: map[string]string{
			"source": "target1",
		},
	}

	target, sub, ok := eventKey(event)
	if !ok {
		t.Fatalf("expected ok=true")
	}

	if target != "target1" {
		t.Fatalf("expected target 'target1', got %q", target)
	}

	if sub != "fallback_sub" {
		t.Fatalf("expected sub 'fallback_sub' (from Name), got %q", sub)
	}
}

func TestEventKeyEmptyTarget(t *testing.T) {
	event := Event{
		Name:      "test",
		Timestamp: 1234567890,
		Tags: map[string]string{
			"subscription-name": "sub1",
		},
	}

	_, _, ok := eventKey(event)
	if ok {
		t.Fatalf("expected ok=false for empty target")
	}
}

func TestEventKeyEmptySubscription(t *testing.T) {
	event := Event{
		Name:      "",
		Timestamp: 1234567890,
		Tags: map[string]string{
			"source": "target1",
		},
	}

	_, _, ok := eventKey(event)
	if ok {
		t.Fatalf("expected ok=false for empty subscription")
	}
}
