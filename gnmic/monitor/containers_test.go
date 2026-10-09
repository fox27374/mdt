package main

import (
	"context"
	"math"
	"net/http"
	"net/http/httptest"
	"os"
	"regexp"
	"testing"
	"time"
)

const podmanMemTotal = 4112338944 // host memory; podman reports it as the limit when none is set

func loadContainerSample(t *testing.T, file string, include *regexp.Regexp) []ContainerSample {
	t.Helper()
	f, err := os.Open("testdata/" + file)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	samples, err := ParseContainerMetrics(f, include)
	if err != nil {
		t.Fatalf("ParseContainerMetrics(%s): %v", file, err)
	}
	return samples
}

func TestParseContainerMetricsRunningOnly(t *testing.T) {
	samples := loadContainerSample(t, "podman_exporter.txt", nil)

	var names []string
	for _, s := range samples {
		names = append(names, s.Name)
	}
	want := []string{"fx-a", "fx-b", "fx-c", "fx-exporter"}
	if len(names) != len(want) {
		t.Fatalf("names = %v, want %v", names, want)
	}
	for i := range want {
		if names[i] != want[i] {
			t.Fatalf("names = %v, want %v", names, want)
		}
	}

	for _, s := range samples {
		if s.Name == "fx-b" {
			if s.MemLimit != 67108864 {
				t.Errorf("fx-b MemLimit = %v, want 67108864 (--memory 64m)", s.MemLimit)
			}
			if s.MemUsed != 53248 {
				t.Errorf("fx-b MemUsed = %v, want 53248", s.MemUsed)
			}
			if s.CPUSeconds != 0.01595 {
				t.Errorf("fx-b CPUSeconds = %v, want 0.01595", s.CPUSeconds)
			}
		}
	}
}

func TestParseContainerMetricsInclude(t *testing.T) {
	samples := loadContainerSample(t, "podman_exporter.txt", regexp.MustCompile(`^fx-[ab]$`))
	if len(samples) != 2 || samples[0].Name != "fx-a" || samples[1].Name != "fx-b" {
		t.Fatalf("include filter gave %+v, want fx-a and fx-b", samples)
	}
}

func TestContainerRowsCPURateAndMemory(t *testing.T) {
	first := loadContainerSample(t, "podman_exporter.txt", nil)
	second := loadContainerSample(t, "podman_exporter_second.txt", nil)

	t0 := time.Date(2026, 10, 9, 8, 0, 0, 0, time.UTC)
	t1 := t0.Add(30 * time.Second)

	// First poll: no previous sample, so CPU is unknown
	prev := containerWindow{}
	rows := containerRows(prev, first, t0, podmanMemTotal)
	for _, r := range rows {
		if r.CPUKnown {
			t.Errorf("%s: CPU known on first poll", r.Name)
		}
	}

	// Second poll: CPU rate = delta cpu seconds / delta wall seconds * 100
	prev = containerWindow{At: t0, Samples: map[string]ContainerSample{}}
	for _, s := range first {
		prev.Samples[s.Name] = s
	}
	rows = containerRows(prev, second, t1, podmanMemTotal)
	if len(rows) != 4 {
		t.Fatalf("got %d rows, want 4", len(rows))
	}
	for i, r := range rows {
		want := 100 * (second[i].CPUSeconds - first[i].CPUSeconds) / 30
		if !r.CPUKnown || math.Abs(r.CPU-want) > 1e-9 {
			t.Errorf("%s: CPU = %v (known %v), want %v", r.Name, r.CPU, r.CPUKnown, want)
		}
	}

	// Memory: fx-b has a 64 MiB limit, fx-a has no limit (limit equals host memory)
	for _, r := range rows {
		switch r.Name {
		case "fx-b":
			if !r.MemLimitSet || math.Abs(r.MemPct-100*53248/67108864.0) > 1e-9 {
				t.Errorf("fx-b: MemLimitSet %v MemPct %v", r.MemLimitSet, r.MemPct)
			}
		case "fx-a":
			if r.MemLimitSet {
				t.Errorf("fx-a: limit reported as set although it equals host memory")
			}
		}
	}
}

func TestContainerRowsCounterReset(t *testing.T) {
	cur := []ContainerSample{{Name: "x", CPUSeconds: 1}}
	prev := containerWindow{
		At:      time.Unix(0, 0),
		Samples: map[string]ContainerSample{"x": {Name: "x", CPUSeconds: 50}},
	}
	rows := containerRows(prev, cur, time.Unix(10, 0), 0)
	if rows[0].CPUKnown {
		t.Errorf("CPU known after counter reset")
	}
}

func TestRunContainersExporterDownClearsRows(t *testing.T) {
	st := NewStore(time.Now())
	st.SetContainers("docker-host", []ContainerState{{Name: "stale"}})

	down := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "down", http.StatusInternalServerError)
	}))
	defer down.Close()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan struct{})
	go func() {
		RunContainers(ctx, st, []HostTarget{{Name: "docker-host", URL: down.URL}}, nil, time.Hour)
		close(done)
	}()

	// Wait until the failed poll has cleared the stale rows
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		st.mu.RLock()
		_, ok := st.containers["docker-host"]
		st.mu.RUnlock()
		if !ok {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	cancel()
	<-done

	st.mu.RLock()
	defer st.mu.RUnlock()
	if _, ok := st.containers["docker-host"]; ok {
		t.Errorf("rows still present after exporter failure")
	}
}
