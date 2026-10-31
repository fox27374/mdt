package main

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

// Test checkConsul with real fixture data
func TestCheckConsulOK(t *testing.T) {
	// Load fixture files
	leaderData := readFixture(t, "testdata/consul_leader.json")
	membersData := readFixture(t, "testdata/consul_members.json")
	healthData := readFixture(t, "testdata/consul_health_gnmic-api.json")

	// Create test server
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/v1/status/leader":
			w.Header().Set("Content-Type", "application/json")
			w.Write(leaderData)
		case "/v1/agent/members":
			w.Header().Set("Content-Type", "application/json")
			w.Write(membersData)
		case "/v1/health/service/mdt-gnmic-api":
			w.Header().Set("Content-Type", "application/json")
			w.Write(healthData)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	// Build expected collectors list from health data
	collectors := []Collector{
		{Name: "gnmic-1"},
		{Name: "gnmic-2"},
	}

	hc := &http.Client{Timeout: 5 * time.Second}
	ctx := context.Background()

	comp := checkConsul(ctx, hc, server.URL, collectors)

	if !comp.OK {
		t.Errorf("expected OK=true, got false, Detail: %s", comp.Detail)
	}
	if comp.Name != "consul" {
		t.Errorf("expected Name=consul, got %s", comp.Name)
	}
	// Check that detail contains expected parts
	if !strings.Contains(comp.Detail, "leader") {
		t.Errorf("expected 'leader' in detail: %s", comp.Detail)
	}
	if !strings.Contains(comp.Detail, "members alive") {
		t.Errorf("expected 'members alive' in detail: %s", comp.Detail)
	}
	if !strings.Contains(comp.Detail, "collectors passing") {
		t.Errorf("expected 'collectors passing' in detail: %s", comp.Detail)
	}
}

// Test checkConsul with no leader
func TestCheckConsulNoLeader(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/v1/status/leader":
			// Return empty leader
			w.Header().Set("Content-Type", "application/json")
			w.Write([]byte(`""`))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	hc := &http.Client{Timeout: 5 * time.Second}
	ctx := context.Background()
	collectors := []Collector{{Name: "gnmic-1"}}

	comp := checkConsul(ctx, hc, server.URL, collectors)

	if comp.OK {
		t.Errorf("expected OK=false, got true")
	}
	if comp.Detail != "no leader" {
		t.Errorf("expected Detail='no leader', got %s", comp.Detail)
	}
}

// Test checkConsul with missing collector
func TestCheckConsulMissingCollector(t *testing.T) {
	// Load fixture files
	leaderData := readFixture(t, "testdata/consul_leader.json")
	membersData := readFixture(t, "testdata/consul_members.json")
	healthData := readFixture(t, "testdata/consul_health_gnmic-api.json")

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/v1/status/leader":
			w.Header().Set("Content-Type", "application/json")
			w.Write(leaderData)
		case "/v1/agent/members":
			w.Header().Set("Content-Type", "application/json")
			w.Write(membersData)
		case "/v1/health/service/mdt-gnmic-api":
			w.Header().Set("Content-Type", "application/json")
			w.Write(healthData)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	// Expect a collector that doesn't exist
	collectors := []Collector{
		{Name: "gnmic-1"},
		{Name: "gnmic-3"},
	}

	hc := &http.Client{Timeout: 5 * time.Second}
	ctx := context.Background()

	comp := checkConsul(ctx, hc, server.URL, collectors)

	if comp.OK {
		t.Errorf("expected OK=false, got true")
	}
	if !strings.Contains(comp.Detail, "gnmic-3") {
		t.Errorf("expected 'gnmic-3' in detail: %s", comp.Detail)
	}
}

// Test checkConsul with a check marked critical
func TestCheckConsulCriticalCheck(t *testing.T) {
	leaderData := readFixture(t, "testdata/consul_leader.json")
	membersData := readFixture(t, "testdata/consul_members.json")

	// Modify health data to have a critical check
	healthData := readFixture(t, "testdata/consul_health_gnmic-api.json")
	var healthEntries []interface{}
	if err := json.Unmarshal(healthData, &healthEntries); err != nil {
		t.Fatalf("parse health fixture: %v", err)
	}

	// Change first service's check status to critical
	if len(healthEntries) > 0 {
		entry, ok := healthEntries[0].(map[string]interface{})
		if ok {
			checks, ok := entry["Checks"].([]interface{})
			if ok && len(checks) > 0 {
				check, ok := checks[0].(map[string]interface{})
				if ok {
					check["Status"] = "critical"
				}
			}
		}
	}

	modifiedHealth, _ := json.Marshal(healthEntries)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/v1/status/leader":
			w.Header().Set("Content-Type", "application/json")
			w.Write(leaderData)
		case "/v1/agent/members":
			w.Header().Set("Content-Type", "application/json")
			w.Write(membersData)
		case "/v1/health/service/mdt-gnmic-api":
			w.Header().Set("Content-Type", "application/json")
			w.Write(modifiedHealth)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	collectors := []Collector{
		{Name: "gnmic-1"},
		{Name: "gnmic-2"},
	}

	hc := &http.Client{Timeout: 5 * time.Second}
	ctx := context.Background()

	comp := checkConsul(ctx, hc, server.URL, collectors)

	if comp.OK {
		t.Errorf("expected OK=false, got true")
	}
}

// Test checkNATS with real fixture data
func TestCheckNATSOK(t *testing.T) {
	healthzData := readFixture(t, "testdata/nats_healthz.json")
	varzData := readFixture(t, "testdata/nats_varz.json")

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/healthz":
			w.Header().Set("Content-Type", "application/json")
			w.Write(healthzData)
		case "/varz":
			w.Header().Set("Content-Type", "application/json")
			w.Write(varzData)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	hc := &http.Client{Timeout: 5 * time.Second}
	ctx := context.Background()
	prev := &natsPrev{}
	now := time.Now()

	comp := checkNATS(ctx, hc, server.URL, prev, now)

	if !comp.OK {
		t.Errorf("expected OK=true, got false, Detail: %s", comp.Detail)
	}
	if comp.Name != "nats" {
		t.Errorf("expected Name=nats, got %s", comp.Name)
	}
	if !strings.Contains(comp.Detail, "connections") {
		t.Errorf("expected 'connections' in detail: %s", comp.Detail)
	}
	if !strings.Contains(comp.Detail, "rate n/a") {
		t.Errorf("expected 'rate n/a' in detail on first call: %s", comp.Detail)
	}
}

// Test checkNATS with a second call to compute rate
func TestCheckNATSRate(t *testing.T) {
	healthzData := readFixture(t, "testdata/nats_healthz.json")

	// First varz response with in_msgs = 100
	varzData1 := []byte(`{"connections": 3, "in_msgs": 100}`)

	// Second varz response with in_msgs = 200
	varzData2 := []byte(`{"connections": 3, "in_msgs": 200}`)

	callCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/healthz":
			w.Header().Set("Content-Type", "application/json")
			w.Write(healthzData)
		case "/varz":
			w.Header().Set("Content-Type", "application/json")
			callCount++
			if callCount == 1 {
				w.Write(varzData1)
			} else {
				w.Write(varzData2)
			}
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	hc := &http.Client{Timeout: 5 * time.Second}
	ctx := context.Background()
	prev := &natsPrev{}

	// First call
	now1 := time.Now()
	comp1 := checkNATS(ctx, hc, server.URL, prev, now1)

	if !strings.Contains(comp1.Detail, "rate n/a") {
		t.Errorf("expected 'rate n/a' on first call: %s", comp1.Detail)
	}

	// Second call a few seconds later
	now2 := now1.Add(2 * time.Second)
	comp2 := checkNATS(ctx, hc, server.URL, prev, now2)

	if !comp2.OK {
		t.Errorf("second call: expected OK=true, got false")
	}
	if strings.Contains(comp2.Detail, "rate n/a") {
		t.Errorf("second call: expected numeric rate, got: %s", comp2.Detail)
	}
	// With 100 msgs in 2 seconds, rate should be 50 msg/s
	if !strings.Contains(comp2.Detail, "50.0") {
		t.Errorf("expected '50.0' msg/s rate in: %s", comp2.Detail)
	}
}

// Test checkNATS with /healthz returning 503
func TestCheckNATSHealthzError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/healthz":
			w.WriteHeader(http.StatusServiceUnavailable)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	hc := &http.Client{Timeout: 5 * time.Second}
	ctx := context.Background()
	prev := &natsPrev{}
	now := time.Now()

	comp := checkNATS(ctx, hc, server.URL, prev, now)

	if comp.OK {
		t.Errorf("expected OK=false, got true")
	}
	if !strings.Contains(comp.Detail, "503") {
		t.Errorf("expected '503' in detail: %s", comp.Detail)
	}
}

// Test checkOutput with 200 response
func TestCheckOutputOK(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		w.Write([]byte("# HELP metric1 help text\n"))
	}))
	defer server.Close()

	hc := &http.Client{Timeout: 5 * time.Second}
	ctx := context.Background()

	comp := checkOutput(ctx, hc, server.URL)

	if !comp.OK {
		t.Errorf("expected OK=true, got false, Detail: %s", comp.Detail)
	}
	if comp.Name != "gnmic-output" {
		t.Errorf("expected Name=gnmic-output, got %s", comp.Name)
	}
	if comp.Detail != "serving metrics" {
		t.Errorf("expected Detail='serving metrics', got %s", comp.Detail)
	}
}

// Test checkOutput with 500 response
func TestCheckOutputError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	hc := &http.Client{Timeout: 5 * time.Second}
	ctx := context.Background()

	comp := checkOutput(ctx, hc, server.URL)

	if comp.OK {
		t.Errorf("expected OK=false, got true")
	}
	if !strings.Contains(comp.Detail, "500") {
		t.Errorf("expected '500' in detail: %s", comp.Detail)
	}
}

// Test checkOutput with closed server
func TestCheckOutputConnectionError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	server.Close()

	hc := &http.Client{Timeout: 5 * time.Second}
	ctx := context.Background()

	comp := checkOutput(ctx, hc, server.URL)

	if comp.OK {
		t.Errorf("expected OK=false, got true")
	}
	// Should contain some error message about connection
}

// Helper function to read fixture files
func readFixture(t *testing.T, path string) []byte {
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read fixture %s: %v", path, err)
	}
	return data
}

// Test the doGet helper
func TestDoGet(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		w.Write([]byte("test response"))
	}))
	defer server.Close()

	hc := &http.Client{Timeout: 5 * time.Second}
	ctx := context.Background()

	resp, err := doGet(ctx, hc, server.URL)
	if err != nil {
		t.Fatalf("doGet: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Errorf("expected status 200, got %d", resp.StatusCode)
	}

	body, _ := io.ReadAll(resp.Body)
	if string(body) != "test response" {
		t.Errorf("expected 'test response', got %s", body)
	}
}

// Test doGet with context cancellation
func TestDoGetContextCancelled(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(1 * time.Second)
		w.Write([]byte("response"))
	}))
	defer server.Close()

	hc := &http.Client{Timeout: 5 * time.Second}
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()

	_, err := doGet(ctx, hc, server.URL)
	if err == nil {
		t.Errorf("expected error due to context timeout")
	}
}

// Test parseLocks with the live Consul KV response (14 held locks, values are base64 instance names)
func TestParseLocksLiveFixture(t *testing.T) {
	body, err := os.ReadFile("testdata/consul_kv_targets.json")
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	locks, err := parseLocks(body, "gnmic/mdt/targets/")
	if err != nil {
		t.Fatalf("parseLocks: %v", err)
	}
	if len(locks) != 14 {
		t.Fatalf("got %d locks, want 14", len(locks))
	}
	if locks["ibk-lab-border01"] != "gnmic-1" {
		t.Errorf("ibk-lab-border01 holder = %q, want gnmic-1", locks["ibk-lab-border01"])
	}
	if locks["ibk-lab-sw98"] != "gnmic-2" {
		t.Errorf("ibk-lab-sw98 holder = %q, want gnmic-2", locks["ibk-lab-sw98"])
	}
}

func TestParseLocks(t *testing.T) {
	const prefix = "gnmic/mdt/targets/"
	tests := []struct {
		name    string
		body    string
		want    map[string]string
		wantErr bool
	}{
		{
			name: "held lock",
			body: `[{"Key":"gnmic/mdt/targets/t1","Value":"Z25taWMtMQ==","Session":"s1"}]`,
			want: map[string]string{"t1": "gnmic-1"},
		},
		{
			name: "released lock without session is ignored",
			body: `[{"Key":"gnmic/mdt/targets/t1","Value":"Z25taWMtMQ==","Session":""}]`,
			want: map[string]string{},
		},
		{
			name: "key outside prefix is ignored",
			body: `[{"Key":"gnmic/mdt/leader","Value":"Z25taWMtMQ==","Session":"s1"}]`,
			want: map[string]string{},
		},
		{
			name: "empty value is ignored",
			body: `[{"Key":"gnmic/mdt/targets/t1","Value":"","Session":"s1"}]`,
			want: map[string]string{},
		},
		{
			name: "null value is ignored",
			body: `[{"Key":"gnmic/mdt/targets/t1","Value":null,"Session":"s1"}]`,
			want: map[string]string{},
		},
		{
			name: "empty response",
			body: `[]`,
			want: map[string]string{},
		},
		{
			name:    "bad base64",
			body:    `[{"Key":"gnmic/mdt/targets/t1","Value":"!!!","Session":"s1"}]`,
			wantErr: true,
		},
		{
			name:    "not json",
			body:    `<html>`,
			wantErr: true,
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := parseLocks([]byte(tt.body), prefix)
			if (err != nil) != tt.wantErr {
				t.Fatalf("err = %v, wantErr %v", err, tt.wantErr)
			}
			if tt.wantErr {
				return
			}
			if len(got) != len(tt.want) {
				t.Fatalf("got %v, want %v", got, tt.want)
			}
			for k, v := range tt.want {
				if got[k] != v {
					t.Errorf("%s = %q, want %q", k, got[k], v)
				}
			}
		})
	}
}

func TestFetchLocksQueriesRecurse(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.RequestURI() != "/v1/kv/gnmic/mdt/targets/?recurse" {
			http.NotFound(w, r)
			return
		}
		w.Write([]byte(`[{"Key":"gnmic/mdt/targets/t1","Value":"Z25taWMtMg==","Session":"s1"}]`))
	}))
	defer srv.Close()

	locks, err := fetchLocks(context.Background(), &http.Client{Timeout: 5 * time.Second}, srv.URL, "gnmic/mdt/targets/")
	if err != nil {
		t.Fatalf("fetchLocks: %v", err)
	}
	if locks["t1"] != "gnmic-2" {
		t.Errorf("t1 holder = %q, want gnmic-2", locks["t1"])
	}

	// Unreachable Consul: nil, no error needed by the caller beyond falling back
	locks, err = fetchLocks(context.Background(), &http.Client{Timeout: time.Second}, "http://127.0.0.1:1", "gnmic/mdt/targets/")
	if err == nil || locks != nil {
		t.Errorf("unreachable: locks = %v, err = %v; want nil and an error", locks, err)
	}
}
