package main

import (
	"context"
	"encoding/json"
	"fmt"
	"sync/atomic"
	"time"

	"github.com/nats-io/nats.go"
)

// Event represents a single gNMI event from the NATS message payload.
type Event struct {
	Name      string            `json:"name"`
	Timestamp int64             `json:"timestamp"`
	Tags      map[string]string `json:"tags"`
}

// parseEvents decodes one NATS message payload into events. The payload is normally a JSON array of
// events; also accept a single JSON object (one event). Anything else returns an error.
func parseEvents(data []byte) ([]Event, error) {
	if len(data) == 0 {
		return nil, fmt.Errorf("empty payload")
	}

	// Try parsing as an array first
	var events []Event
	err := json.Unmarshal(data, &events)
	if err == nil {
		return events, nil
	}

	// Try parsing as a single object
	var event Event
	err = json.Unmarshal(data, &event)
	if err == nil {
		return []Event{event}, nil
	}

	return nil, fmt.Errorf("invalid JSON: %w", err)
}

// eventKey returns the (target, sub) pair for one event, using the tag keys documented in
// testdata/README.md: the target comes from the target tag (usually "source"), the subscription from
// the subscription tag (usually "subscription-name"); if the subscription tag is missing fall back to
// Event.Name. ok is false if either value is empty.
func eventKey(e Event) (target, sub string, ok bool) {
	target = e.Tags["source"]
	if target == "" {
		return "", "", false
	}

	sub = e.Tags["subscription-name"]
	if sub == "" {
		sub = e.Name
	}

	if sub == "" {
		return "", "", false
	}

	return target, sub, true
}

// RunNATS connects to `url`, subscribes to `subject` and, for each message, calls
// st.Seen(target, sub, time.Now()) for every event whose eventKey is ok (use the local receive time,
// not the device timestamp, because device clocks differ). It blocks until ctx is done, then drains
// and closes the connection.
// Connection options: nats.MaxReconnects(-1), nats.RetryOnFailedConnect(true), a 2s reconnect wait,
// and handlers that keep st.SetComponent(Component{Name: "nats-consumer", ...}) current:
//   connected:    OK true,  Detail "subscribed to <subject>, <n> events"
//   disconnected: OK false, Detail "disconnected: <err>"
//   initial failure / not yet connected: OK false, Detail "connecting to <url>"
// <n> is a running event counter (use sync/atomic); refresh the component at most every 10 seconds
// while connected so the count stays current (a ticker inside RunNATS is fine).
func RunNATS(ctx context.Context, st *Store, url, subject string) {
	var eventCount int64
	updateTicker := time.NewTicker(10 * time.Second)
	defer updateTicker.Stop()

	opts := []nats.Option{
		nats.MaxReconnects(-1),
		nats.RetryOnFailedConnect(true),
		nats.ReconnectWait(2 * time.Second),
	}

	opts = append(opts, nats.DisconnectErrHandler(func(nc *nats.Conn, err error) {
		st.SetComponent(Component{
			Name:   "nats-consumer",
			OK:     false,
			Detail: fmt.Sprintf("disconnected: %v", err),
		})
	}))

	opts = append(opts, nats.ReconnectHandler(func(nc *nats.Conn) {
		// Reconnected
		count := atomic.LoadInt64(&eventCount)
		st.SetComponent(Component{
			Name:   "nats-consumer",
			OK:     true,
			Detail: fmt.Sprintf("subscribed to %s, %d events", subject, count),
		})
	}))

	// Initial state: not yet connected
	st.SetComponent(Component{
		Name:   "nats-consumer",
		OK:     false,
		Detail: fmt.Sprintf("connecting to %s", url),
	})

	nc, err := nats.Connect(url, opts...)
	if err != nil {
		st.SetComponent(Component{
			Name:   "nats-consumer",
			OK:     false,
			Detail: fmt.Sprintf("connecting to %s: %v", url, err),
		})
		<-ctx.Done()
		return
	}
	defer func() {
		nc.Drain()
		nc.Close()
	}()

	// Subscribe to the subject
	_, err = nc.Subscribe(subject, func(msg *nats.Msg) {
		events, err := parseEvents(msg.Data)
		if err != nil {
			// Log parsing error but continue processing other events
			return
		}

		now := time.Now()
		for _, event := range events {
			target, sub, ok := eventKey(event)
			if ok {
				st.Seen(target, sub, now)
				atomic.AddInt64(&eventCount, 1)
			}
		}
	})
	if err != nil {
		st.SetComponent(Component{
			Name:   "nats-consumer",
			OK:     false,
			Detail: fmt.Sprintf("connecting to %s: %v", url, err),
		})
		return
	}

	// Wait for context to be done
	for {
		select {
		case <-ctx.Done():
			return
		case <-updateTicker.C:
			// Refresh the component with the latest event count while connected
			if nc.IsConnected() {
				count := atomic.LoadInt64(&eventCount)
				st.SetComponent(Component{
					Name:   "nats-consumer",
					OK:     true,
					Detail: fmt.Sprintf("subscribed to %s, %d events", subject, count),
				})
			}
		}
	}
}
