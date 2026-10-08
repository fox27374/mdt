package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"regexp"
	"strings"
	"testing"
	"time"
)

func TestParseHosts(t *testing.T) {
	tests := []struct {
		name    string
		input   string
		want    []HostTarget
		wantErr bool
	}{
		{
			name:    "empty string returns nil",
			input:   "",
			want:    nil,
			wantErr: false,
		},
		{
			name:  "two entries",
			input: "docker-host=http://host.containers.internal:9100,second=https://second.example.com:9100",
			want: []HostTarget{
				{Name: "docker-host", URL: "http://host.containers.internal:9100/metrics"},
				{Name: "second", URL: "https://second.example.com:9100/metrics"},
			},
			wantErr: false,
		},
		{
			name:    "trailing slash handling",
			input:   "host=http://localhost:9100/",
			want:    []HostTarget{{Name: "host", URL: "http://localhost:9100/metrics"}},
			wantErr: false,
		},
		{
			name:    "/metrics path handling",
			input:   "host=http://localhost:9100/metrics",
			want:    []HostTarget{{Name: "host", URL: "http://localhost:9100/metrics"}},
			wantErr: false,
		},
		{
			name:    "missing equals sign",
			input:   "no-equals",
			wantErr: true,
		},
		{
			name:    "empty name",
			input:   "=http://localhost:9100",
			wantErr: true,
		},
		{
			name:    "empty URL",
			input:   "host=",
			wantErr: true,
		},
		{
			name:    "bad scheme",
			input:   "host=ftp://localhost:9100",
			wantErr: true,
		},
		{
			name:    "spaces around entries",
			input:   " host1 = http://host1:9100 , host2 = http://host2:9100 ",
			want:    []HostTarget{{Name: "host1", URL: "http://host1:9100/metrics"}, {Name: "host2", URL: "http://host2:9100/metrics"}},
			wantErr: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ParseHosts(tt.input)
			if (err != nil) != tt.wantErr {
				t.Errorf("ParseHosts() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr {
				if len(got) != len(tt.want) {
					t.Errorf("ParseHosts() got %d hosts, want %d", len(got), len(tt.want))
					return
				}
				for i, g := range got {
					if g.Name != tt.want[i].Name || g.URL != tt.want[i].URL {
						t.Errorf("ParseHosts()[%d] = %v, want %v", i, g, tt.want[i])
					}
				}
			}
		})
	}
}

func TestParseThresholds(t *testing.T) {
	tests := []struct {
		name    string
		getter  func(key string) string
		want    HostThresholds
		wantErr bool
	}{
		{
			name:    "all defaults with empty getter",
			getter:  func(key string) string { return "" },
			want:    DefaultHostThresholds(),
			wantErr: false,
		},
		{
			name: "override one key",
			getter: func(key string) string {
				if key == "HOST_CPU_WARN" {
					return "75"
				}
				return ""
			},
			want:    HostThresholds{CPUWarn: 75, CPUCrit: 95, MemWarn: 85, MemCrit: 95, DiskWarn: 80, DiskCrit: 90, NetWarn: 70, NetCrit: 90},
			wantErr: false,
		},
		{
			name: "non-number error",
			getter: func(key string) string {
				if key == "HOST_CPU_WARN" {
					return "not-a-number"
				}
				return ""
			},
			wantErr: true,
		},
		{
			name: "out of range error",
			getter: func(key string) string {
				if key == "HOST_MEM_WARN" {
					return "150"
				}
				return ""
			},
			wantErr: true,
		},
		{
			name: "warn >= crit error",
			getter: func(key string) string {
				if key == "HOST_DISK_WARN" {
					return "95"
				}
				if key == "HOST_DISK_CRIT" {
					return "80"
				}
				return ""
			},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ParseThresholds(tt.getter)
			if (err != nil) != tt.wantErr {
				t.Errorf("ParseThresholds() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr && got != tt.want {
				t.Errorf("ParseThresholds() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestPollHost(t *testing.T) {
	// Test with first fixture (CPU should be UNKNOWN, component OK)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fixture, err := os.ReadFile("testdata/node_exporter.txt")
		if err != nil {
			t.Fatalf("read fixture: %v", err)
		}
		w.Header().Set("Content-Type", "text/plain")
		w.Write(fixture)
	}))
	defer server.Close()

	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	st := NewStore(now)
	th := DefaultHostThresholds()
	nicInclude := regexp.MustCompile(`^(en|eth|em|bond|ib)[a-z0-9]*$`)
	windows := make(map[string][]HostSample)

	client := &http.Client{Timeout: 5 * time.Second}
	host := HostTarget{Name: "test-host", URL: server.URL}

	pollHost(st, client, host, windows, th, nicInclude, now)

	// After first call, CPU should be UNKNOWN, component OK
	snap := st.Snapshot(now)
	if len(snap.Hosts) != 1 {
		t.Fatalf("expected 1 host, got %d", len(snap.Hosts))
	}

	hostState := snap.Hosts[0]
	if hostState.Name != "test-host" {
		t.Errorf("host name = %q, want test-host", hostState.Name)
	}
	if hostState.CPU.Level != LevelUnknown {
		t.Errorf("after first call, CPU level = %v, want UNKNOWN", hostState.CPU.Level)
	}

	// Component should be OK
	components := snap.Components
	var hostComp *Component
	for i := range components {
		if components[i].Name == "host test-host" {
			hostComp = &components[i]
			break
		}
	}
	if hostComp == nil {
		t.Fatalf("component 'host test-host' not found")
	}
	if !hostComp.OK {
		t.Errorf("component OK = %v, want true", hostComp.OK)
	}

	// Second call with different time (30 seconds later)
	now2 := now.Add(30 * time.Second)
	fixture2, err := os.ReadFile("testdata/node_exporter_second.txt")
	if err != nil {
		t.Fatalf("read second fixture: %v", err)
	}

	server2 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		w.Write(fixture2)
	}))
	defer server2.Close()

	host.URL = server2.URL
	pollHost(st, client, host, windows, th, nicInclude, now2)

	snap2 := st.Snapshot(now2)
	if len(snap2.Hosts) != 1 {
		t.Fatalf("expected 1 host after second call, got %d", len(snap2.Hosts))
	}

	hostState2 := snap2.Hosts[0]
	// After second call (30 seconds later), CPU should no longer be UNKNOWN
	if hostState2.CPU.Level == LevelUnknown {
		t.Errorf("after second call, CPU level = %v, want not UNKNOWN", hostState2.CPU.Level)
	}

	// Should have disks
	if len(hostState2.Disks) == 0 {
		t.Errorf("expected disks after second call, got none")
	}
}

func TestPollHostHTTPError(t *testing.T) {
	// Server that returns HTTP 500
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	st := NewStore(now)
	th := DefaultHostThresholds()
	nicInclude := regexp.MustCompile(`^(en|eth|em|bond|ib)[a-z0-9]*$`)
	windows := make(map[string][]HostSample)

	client := &http.Client{Timeout: 5 * time.Second}
	host := HostTarget{Name: "test-host", URL: server.URL}

	pollHost(st, client, host, windows, th, nicInclude, now)

	snap := st.Snapshot(now)
	if len(snap.Hosts) != 1 {
		t.Fatalf("expected 1 host, got %d", len(snap.Hosts))
	}

	hostState := snap.Hosts[0]
	if hostState.Level != LevelUnknown {
		t.Errorf("host level = %v, want UNKNOWN", hostState.Level)
	}

	if !strings.Contains(hostState.Reason, "exporter unreachable") {
		t.Errorf("reason = %q, want to contain 'exporter unreachable'", hostState.Reason)
	}

	// Component should be NOT OK
	components := snap.Components
	var hostComp *Component
	for i := range components {
		if components[i].Name == "host test-host" {
			hostComp = &components[i]
			break
		}
	}
	if hostComp == nil {
		t.Fatalf("component 'host test-host' not found")
	}
	if hostComp.OK {
		t.Errorf("component OK = %v, want false", hostComp.OK)
	}

	// Earlier samples should still be in the window
	if len(windows["test-host"]) != 0 {
		t.Errorf("window should have no samples after error (not yet), got %d", len(windows["test-host"]))
	}
}

func TestRunHosts(t *testing.T) {
	// Create a test server
	callCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		fixture, err := os.ReadFile("testdata/node_exporter.txt")
		if err != nil {
			t.Fatalf("read fixture: %v", err)
		}
		w.Header().Set("Content-Type", "text/plain")
		w.Write(fixture)
	}))
	defer server.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	st := NewStore(now)
	th := DefaultHostThresholds()
	nicInclude := regexp.MustCompile(`^(en|eth|em|bond|ib)[a-z0-9]*$`)
	hosts := []HostTarget{{Name: "test-host", URL: server.URL}}

	RunHosts(ctx, st, hosts, th, nicInclude, 50*time.Millisecond)

	snap := st.Snapshot(now)

	// Should have called the server at least once (immediately)
	if callCount < 1 {
		t.Errorf("server called %d times, want >= 1", callCount)
	}

	// Snapshot should contain the host
	if len(snap.Hosts) < 1 {
		t.Errorf("expected at least 1 host in snapshot, got %d", len(snap.Hosts))
	}
}

func TestHostDetailBuilding(t *testing.T) {
	tests := []struct {
		name   string
		state  HostState
		want   string
	}{
		{
			name: "cpu n/a, 1 disk, 1 NIC",
			state: HostState{
				Name: "host1",
				CPU:  MetricState{Name: "cpu", Level: LevelUnknown},
				Memory: MetricState{Name: "memory", Value: 40},
				Disks: []MetricState{
					{Name: "/", Value: 50},
				},
				NICs: []MetricState{
					{Name: "eth0", Value: 30},
				},
			},
			want: "cpu n/a, memory 40%, 1 disks, 1 NIC",
		},
		{
			name: "cpu known, 2 disks, 2 NICs",
			state: HostState{
				Name: "host2",
				CPU:  MetricState{Name: "cpu", Value: 12, Level: LevelOK},
				Memory: MetricState{Name: "memory", Value: 40},
				Disks: []MetricState{
					{Name: "/", Value: 50},
					{Name: "/var", Value: 60},
				},
				NICs: []MetricState{
					{Name: "eth0", Value: 30},
					{Name: "eth1", Value: 20},
				},
			},
			want: "cpu 12%, memory 40%, 2 disks, 2 NICs",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := buildHostDetail(tt.state)
			if got != tt.want {
				t.Errorf("buildHostDetail() = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestParseThresholdsErrorMessages(t *testing.T) {
	tests := []struct {
		name    string
		getter  func(key string) string
		wantMsg string
	}{
		{
			name: "HOST_CPU_WARN non-number",
			getter: func(key string) string {
				if key == "HOST_CPU_WARN" {
					return "bad"
				}
				return ""
			},
			wantMsg: "HOST_CPU_WARN",
		},
		{
			name: "HOST_MEM_WARN out of range",
			getter: func(key string) string {
				if key == "HOST_MEM_WARN" {
					return "101"
				}
				return ""
			},
			wantMsg: "HOST_MEM_WARN",
		},
		{
			name: "HOST_NET_WARN >= HOST_NET_CRIT",
			getter: func(key string) string {
				if key == "HOST_NET_WARN" {
					return "95"
				}
				if key == "HOST_NET_CRIT" {
					return "90"
				}
				return ""
			},
			wantMsg: "HOST_NET_WARN",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := ParseThresholds(tt.getter)
			if err == nil {
				t.Errorf("ParseThresholds() expected error")
				return
			}
			if !strings.Contains(err.Error(), tt.wantMsg) {
				t.Errorf("ParseThresholds() error = %q, want to contain %q", err.Error(), tt.wantMsg)
			}
		})
	}
}
