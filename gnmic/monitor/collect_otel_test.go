package main

import (
	"context"
	"math"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

func loadOtelSample(t *testing.T, file string, at time.Time) OtelSample {
	t.Helper()
	f, err := os.Open("testdata/" + file)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	s, err := ParseOtelMetrics(f, at)
	if err != nil {
		t.Fatalf("ParseOtelMetrics(%s): %v", file, err)
	}
	return s
}

func near(a, b float64) bool { return math.Abs(a-b) < 1e-9 }

func TestParseOtelMetricsFixtures(t *testing.T) {
	at := time.Date(2026, 10, 22, 5, 0, 0, 0, time.UTC)
	s := loadOtelSample(t, "otel_metrics.txt", at)

	e, ok := s.Exporters["splunk_hec/splunkfree"]
	if !ok {
		t.Fatalf("exporter splunk_hec/splunkfree missing: %v", s.Exporters)
	}
	if e.Sent != 865910 || e.Failed != 57964 || e.QueueSize != 0 || e.QueueCap != 1000 {
		t.Errorf("exporter = %+v, want sent 865910 failed 57964 queue 0/1000", e)
	}

	if r := s.Receivers["prometheus/gnmic"]; r.Accepted != 63090 || r.Refused != 0 || r.Failed != 0 {
		t.Errorf("prometheus/gnmic receiver = %+v", r)
	}
	if r := s.Receivers["hostmetrics"]; r.Accepted != 18281 {
		t.Errorf("hostmetrics receiver = %+v", r)
	}

	if !near(s.CPUSeconds, 43.51) || !near(s.Uptime, 1803.258362937) || !near(s.RSS, 3.20704512e+08) {
		t.Errorf("process = cpu %v uptime %v rss %v", s.CPUSeconds, s.Uptime, s.RSS)
	}
	if !s.At.Equal(at) {
		t.Errorf("At = %v, want %v", s.At, at)
	}
}

func TestParseOtelMetricsTotalSuffix(t *testing.T) {
	body := `# TYPE otelcol_exporter_sent_metric_points_total counter
otelcol_exporter_sent_metric_points_total{exporter="x"} 10
# TYPE otelcol_exporter_send_failed_metric_points_total counter
otelcol_exporter_send_failed_metric_points_total{exporter="x"} 2
# TYPE otelcol_receiver_accepted_metric_points_total counter
otelcol_receiver_accepted_metric_points_total{receiver="r",transport="http"} 7
`
	s, err := ParseOtelMetrics(strings.NewReader(body), time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if e := s.Exporters["x"]; e.Sent != 10 || e.Failed != 2 {
		t.Errorf("exporter x = %+v, want sent 10 failed 2", e)
	}
	if r := s.Receivers["r"]; r.Accepted != 7 {
		t.Errorf("receiver r = %+v, want accepted 7", r)
	}
}

func TestParseOtelMetricsNotOtel(t *testing.T) {
	if _, err := ParseOtelMetrics(strings.NewReader("node_cpu_seconds_total{cpu=\"0\"} 1\n"), time.Now()); err == nil {
		t.Error("expected error for a body without otelcol series")
	}
	if _, err := ParseOtelMetrics(strings.NewReader("this is { not prometheus"), time.Now()); err == nil {
		t.Error("expected error for garbage input")
	}
}

func TestParseOtelThresholds(t *testing.T) {
	mk := func(kv map[string]string) func(string) string {
		return func(k string) string { return kv[k] }
	}
	th, err := ParseOtelThresholds(mk(nil))
	if err != nil || th != DefaultOtelThresholds() || th.FailPct != 1 || th.QueuePct != 80 {
		t.Errorf("defaults = %+v, %v", th, err)
	}
	th, err = ParseOtelThresholds(mk(map[string]string{"OTEL_FAIL_PCT": "5", "OTEL_QUEUE_PCT": "50"}))
	if err != nil || th.FailPct != 5 || th.QueuePct != 50 {
		t.Errorf("overrides = %+v, %v", th, err)
	}
	for _, kv := range []map[string]string{
		{"OTEL_FAIL_PCT": "x"},
		{"OTEL_QUEUE_PCT": "101"},
		{"OTEL_QUEUE_PCT": "-1"},
	} {
		if _, err := ParseOtelThresholds(mk(kv)); err == nil {
			t.Errorf("expected error for %v", kv)
		}
	}
}

func TestOtelURLs(t *testing.T) {
	lookup := func(kv map[string]string) func(string) (string, bool) {
		return func(k string) (string, bool) { v, ok := kv[k]; return v, ok }
	}
	h, m := otelURLs(lookup(nil))
	if h != "http://otel-collector:13133/" || m != "http://otel-collector:8888/metrics" {
		t.Errorf("defaults = %q, %q", h, m)
	}
	h, m = otelURLs(lookup(map[string]string{"OTEL_HEALTH_URL": "", "OTEL_METRICS_URL": "http://x:1/m"}))
	if h != "" || m != "http://x:1/m" {
		t.Errorf("health off = %q, %q", h, m)
	}
	h, m = otelURLs(lookup(map[string]string{"OTEL_HEALTH_URL": "", "OTEL_METRICS_URL": ""}))
	if h != "" || m != "" {
		t.Errorf("both explicitly empty = %q, %q; want disabled", h, m)
	}
}

func TestBuildOtelStateRates(t *testing.T) {
	t0 := time.Date(2026, 10, 22, 5, 0, 0, 0, time.UTC)
	first := loadOtelSample(t, "otel_metrics.txt", t0)
	second := loadOtelSample(t, "otel_metrics_second.txt", t0.Add(30*time.Second))

	// First poll: nothing is a rate yet, but totals are still shown
	st := buildOtelState(nil, first)
	if len(st.Exporters) != 1 || st.Exporters[0].RatesKnown {
		t.Fatalf("first poll exporters = %+v", st.Exporters)
	}
	if st.CPUKnown || st.Uptime == 0 || st.RSS == 0 {
		t.Errorf("first poll process = %+v", st)
	}

	st = buildOtelState(&first, second)
	e := st.Exporters[0]
	if !e.RatesKnown || !near(e.SentPerSec, 1000) || !near(e.FailedPerSec, 1) {
		t.Errorf("exporter rates = %+v, want 1000 sent/s, 1 failed/s", e)
	}
	if e.QueueCap != 1000 || e.QueueSize != 0 {
		t.Errorf("exporter queue = %+v", e)
	}
	if !st.CPUKnown || !near(st.CPUPct, 1) {
		t.Errorf("cpu = %v known %v, want 1%% of one core", st.CPUPct, st.CPUKnown)
	}
}

func TestReceiverRates(t *testing.T) {
	t0 := time.Date(2026, 10, 22, 5, 0, 0, 0, time.UTC)
	marks := make(map[string]receiverMark)
	poll := func(after time.Duration, accepted float64) OtelReceiverState {
		cur := OtelSample{At: t0.Add(after), Receivers: map[string]OtelReceiver{"p": {Accepted: accepted}}}
		rows := []OtelReceiverState{{Name: "p"}}
		receiverRates(marks, cur, rows)
		return rows[0]
	}

	if r := poll(0, 1000); r.RatesKnown {
		t.Errorf("first sight should have no rate: %+v", r)
	}
	// Polled every 15s, scraped every 60s: the rate is measured over the full scrape interval and held
	if r := poll(15*time.Second, 1000); r.RatesKnown {
		t.Errorf("no change yet should still have no rate: %+v", r)
	}
	if r := poll(60*time.Second, 4000); !r.RatesKnown || !near(r.AcceptedPerSec, 50) {
		t.Errorf("after first change = %+v, want 50/s", r)
	}
	for _, after := range []time.Duration{75, 90, 105} {
		if r := poll(after*time.Second, 4000); !near(r.AcceptedPerSec, 50) {
			t.Errorf("at %ds held rate = %+v, want 50/s", after, r)
		}
	}
	if r := poll(120*time.Second, 7000); !near(r.AcceptedPerSec, 50) {
		t.Errorf("after second change = %+v, want 50/s", r)
	}
	// Stalled longer than otelRateStale drops to zero
	if r := poll(120*time.Second+otelRateStale+time.Second, 7000); !r.RatesKnown || r.AcceptedPerSec != 0 {
		t.Errorf("stalled = %+v, want known 0/s", r)
	}
	// Collector restart: counters went down, measuring starts over
	if r := poll(20*time.Minute, 10); r.RatesKnown {
		t.Errorf("after reset = %+v, want no rate", r)
	}
}

func TestBuildOtelStateCounterReset(t *testing.T) {
	t0 := time.Date(2026, 10, 22, 5, 0, 0, 0, time.UTC)
	prev := OtelSample{At: t0, Exporters: map[string]OtelExporter{"x": {Sent: 500, Failed: 0}}}
	cur := OtelSample{At: t0.Add(10 * time.Second), Exporters: map[string]OtelExporter{"x": {Sent: 20, Failed: 0}}}
	st := buildOtelState(&prev, cur)
	if st.Exporters[0].RatesKnown {
		t.Errorf("counter reset should give no rate: %+v", st.Exporters[0])
	}
}

func TestEvalOtel(t *testing.T) {
	th := DefaultOtelThresholds()
	t0 := time.Date(2026, 10, 22, 5, 0, 0, 0, time.UTC)
	mk := func(at time.Time, sent, failed, qsize float64) *OtelSample {
		return &OtelSample{At: at, Exporters: map[string]OtelExporter{
			"splunk": {Sent: sent, Failed: failed, QueueSize: qsize, QueueCap: 100},
		}}
	}
	prev := mk(t0, 1000, 0, 0)

	tests := []struct {
		name          string
		healthProblem string
		metricsProb   string
		prev, cur     *OtelSample
		wantOK        bool
		wantDetail    string // substring
	}{
		{"healthy with rates", "", "", prev, mk(t0.Add(10*time.Second), 2000, 0, 0), true, "sent 100 points/s"},
		{"health down", "HTTP 503", "", prev, mk(t0.Add(10*time.Second), 2000, 0, 0), false, "health: HTTP 503"},
		{"scrape down", "", "connection refused", prev, nil, false, "metrics: connection refused"},
		{"failure ratio over threshold", "", "", prev, mk(t0.Add(10*time.Second), 1980, 20, 0), false, "export failing: 2.0% failed"},
		{"failure ratio under threshold", "", "", prev, mk(t0.Add(10*time.Second), 3000, 10, 0), true, "0.5% failed"},
		{"no traffic is not a failure", "", "", prev, mk(t0.Add(10*time.Second), 1000, 0, 0), true, "sent 0 points/s"},
		{"queue over threshold", "", "", prev, mk(t0.Add(10*time.Second), 2000, 0, 85), false, "queue 85% full"},
		{"queue under threshold", "", "", prev, mk(t0.Add(10*time.Second), 2000, 0, 79), true, "queue 79%"},
		{"first poll judges queue only", "", "", nil, mk(t0, 1000, 500, 10), true, "rate n/a, queue 10%"},
		{"first poll queue over", "", "", nil, mk(t0, 1000, 0, 90), false, "queue 90% full"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			ok, detail := evalOtel(tt.healthProblem, tt.metricsProb, tt.prev, tt.cur, th)
			if ok != tt.wantOK {
				t.Errorf("ok = %v (%q), want %v", ok, detail, tt.wantOK)
			}
			if !strings.Contains(detail, tt.wantDetail) {
				t.Errorf("detail = %q, want it to contain %q", detail, tt.wantDetail)
			}
		})
	}
}

func TestPollOtelHTTP(t *testing.T) {
	first, err := os.ReadFile("testdata/otel_metrics.txt")
	if err != nil {
		t.Fatal(err)
	}
	second, err := os.ReadFile("testdata/otel_metrics_second.txt")
	if err != nil {
		t.Fatal(err)
	}
	health, err := os.ReadFile("testdata/otel_health.json")
	if err != nil {
		t.Fatal(err)
	}

	calls := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/":
			w.Write(health)
		case "/metrics":
			calls++
			if calls == 1 {
				w.Write(first)
			} else {
				w.Write(second)
			}
		default:
			http.NotFound(w, r)
		}
	}))
	defer srv.Close()

	cfg := OtelConfig{HealthURL: srv.URL + "/", MetricsURL: srv.URL + "/metrics", Thresholds: DefaultOtelThresholds()}
	hc := &http.Client{Timeout: 5 * time.Second}
	ctx := context.Background()

	comp, state, prev := pollOtel(ctx, hc, cfg, nil, time.Now())
	if comp.Name != "otel-collector" || !comp.OK || state == nil || prev == nil {
		t.Fatalf("first poll = %+v, state nil %v, prev nil %v", comp, state == nil, prev == nil)
	}

	comp, state, _ = pollOtel(ctx, hc, cfg, prev, time.Now().Add(30*time.Second))
	if !comp.OK || state == nil || !state.Exporters[0].RatesKnown {
		t.Errorf("second poll = %+v, state %+v", comp, state)
	}

	// Health endpoint answering 503 makes the component not OK, but the metrics still show
	srv503 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/" {
			http.Error(w, "down", http.StatusServiceUnavailable)
			return
		}
		w.Write(first)
	}))
	defer srv503.Close()
	comp, state, _ = pollOtel(ctx, hc, OtelConfig{HealthURL: srv503.URL + "/", MetricsURL: srv503.URL + "/metrics", Thresholds: DefaultOtelThresholds()}, nil, time.Now())
	if comp.OK || !strings.Contains(comp.Detail, "HTTP 503") || state == nil {
		t.Errorf("health down = %+v, state nil %v", comp, state == nil)
	}

	// Health only (metrics check off): OK on a 200 with the expected status
	comp, state, prev = pollOtel(ctx, hc, OtelConfig{HealthURL: srv.URL + "/", Thresholds: DefaultOtelThresholds()}, nil, time.Now())
	if !comp.OK || state != nil || prev != nil {
		t.Errorf("health-only poll = %+v, state nil %v", comp, state == nil)
	}

	// Wrong status text is not OK
	srvBad := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"status":"Starting"}`))
	}))
	defer srvBad.Close()
	comp, _, _ = pollOtel(ctx, hc, OtelConfig{HealthURL: srvBad.URL + "/", Thresholds: DefaultOtelThresholds()}, nil, time.Now())
	if comp.OK || !strings.Contains(comp.Detail, `status "Starting"`) {
		t.Errorf("bad status = %+v", comp)
	}
}
