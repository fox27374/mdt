package main

import (
	"testing"
	"time"
)

func TestEvalSub(t *testing.T) {
	now := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
	started := time.Date(2024, 1, 1, 11, 0, 0, 0, time.UTC)

	tests := []struct {
		name      string
		now       time.Time
		started   time.Time
		lastSeen  time.Time
		interval  time.Duration
		errReason string
		want      Status
	}{
		{
			name:      "error reason set",
			now:       now,
			started:   started,
			lastSeen:  now.Add(-1 * time.Second), // fresh data
			interval:  30 * time.Second,
			errReason: "some error",
			want:      StatusError,
		},
		{
			name:      "never seen and within window",
			now:       now,
			started:   now.Add(-1 * time.Minute), // 1 minute ago
			lastSeen:  time.Time{},
			interval:  30 * time.Second,
			errReason: "",
			want:      StatusWaiting,
		},
		{
			name:      "never seen and past window",
			now:       now,
			started:   now.Add(-5 * time.Minute), // 5 minutes ago, past 2-minute window
			lastSeen:  time.Time{},
			interval:  30 * time.Second,
			errReason: "",
			want:      StatusNoData,
		},
		{
			name:      "seen 10s ago with 30s interval",
			now:       now,
			started:   now.Add(-1 * time.Hour),
			lastSeen:  now.Add(-10 * time.Second),
			interval:  30 * time.Second,
			errReason: "",
			want:      StatusOK,
		},
		{
			name:      "seen 3 minutes ago with 30s interval",
			now:       now,
			started:   now.Add(-1 * time.Hour),
			lastSeen:  now.Add(-3 * time.Minute),
			interval:  30 * time.Second,
			errReason: "",
			want:      StatusStale, // window is 2 min, 3 min > 2 min
		},
		{
			name:      "seen 2h ago with 1h interval",
			now:       now,
			started:   now.Add(-24 * time.Hour),
			lastSeen:  now.Add(-2 * time.Hour),
			interval:  1 * time.Hour,
			errReason: "",
			want:      StatusOK, // window is 3h, 2h < 3h
		},
		{
			name:      "seen 4h ago with 1h interval",
			now:       now,
			started:   now.Add(-24 * time.Hour),
			lastSeen:  now.Add(-4 * time.Hour),
			interval:  1 * time.Hour,
			errReason: "",
			want:      StatusStale, // window is 3h, 4h > 3h
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := EvalSub(tt.now, tt.started, tt.lastSeen, tt.interval, tt.errReason)
			if got != tt.want {
				t.Errorf("EvalSub() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestWorse(t *testing.T) {
	tests := []struct {
		name string
		a    Status
		b    Status
		want Status
	}{
		{
			name: "OK vs WAITING",
			a:    StatusOK,
			b:    StatusWaiting,
			want: StatusWaiting,
		},
		{
			name: "WAITING vs STALE",
			a:    StatusWaiting,
			b:    StatusStale,
			want: StatusStale,
		},
		{
			name: "STALE vs NO_DATA",
			a:    StatusStale,
			b:    StatusNoData,
			want: StatusNoData,
		},
		{
			name: "NO_DATA vs ERROR",
			a:    StatusNoData,
			b:    StatusError,
			want: StatusError,
		},
		{
			name: "same status",
			a:    StatusOK,
			b:    StatusOK,
			want: StatusOK,
		},
		{
			name: "reversed order",
			a:    StatusError,
			b:    StatusOK,
			want: StatusError,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := Worse(tt.a, tt.b)
			if got != tt.want {
				t.Errorf("Worse(%v, %v) = %v, want %v", tt.a, tt.b, got, tt.want)
			}
		})
	}
}

func TestStaleWindow(t *testing.T) {
	tests := []struct {
		name     string
		interval time.Duration
		want     time.Duration
	}{
		{
			name:     "30s interval",
			interval: 30 * time.Second,
			want:     2 * time.Minute, // 3*30s = 90s < 2min, so 2min
		},
		{
			name:     "1h interval",
			interval: 1 * time.Hour,
			want:     3 * time.Hour, // 3*1h = 3h > 2min, so 3h
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := StaleWindow(tt.interval)
			if got != tt.want {
				t.Errorf("StaleWindow(%v) = %v, want %v", tt.interval, got, tt.want)
			}
		})
	}
}

func TestParseCollectors(t *testing.T) {
	tests := []struct {
		name    string
		input   string
		want    []Collector
		wantErr bool
	}{
		{
			name:  "valid two-entry string",
			input: "gnmic-1=http://gnmic-1:8800,gnmic-2=http://gnmic-2:8800",
			want: []Collector{
				{Name: "gnmic-1", URL: "http://gnmic-1:8800"},
				{Name: "gnmic-2", URL: "http://gnmic-2:8800"},
			},
			wantErr: false,
		},
		{
			name:    "trailing slash trimmed",
			input:   "gnmic-1=http://gnmic-1:8800/",
			want:    []Collector{{Name: "gnmic-1", URL: "http://gnmic-1:8800"}},
			wantErr: false,
		},
		{
			name:    "empty string error",
			input:   "",
			want:    nil,
			wantErr: true,
		},
		{
			name:    "missing equal error",
			input:   "gnmic-1:http://gnmic-1:8800",
			want:    nil,
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ParseCollectors(tt.input)
			if (err != nil) != tt.wantErr {
				t.Errorf("ParseCollectors() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if len(got) != len(tt.want) {
				t.Errorf("ParseCollectors() got %d collectors, want %d", len(got), len(tt.want))
				return
			}
			for i, c := range got {
				if c.Name != tt.want[i].Name || c.URL != tt.want[i].URL {
					t.Errorf("ParseCollectors() got %v, want %v", c, tt.want[i])
				}
			}
		})
	}
}
