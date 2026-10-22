package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/prometheus/common/expfmt"
	"github.com/prometheus/common/model"
)

// OtelThresholds are the limits of the OpenTelemetry collector check.
type OtelThresholds struct {
	FailPct  float64 // percent of metric points that failed to export between two polls; at or above is not OK
	QueuePct float64 // percent of an exporter's retry queue in use; at or above is not OK
}

// DefaultOtelThresholds: export failures 1%, queue 80%.
func DefaultOtelThresholds() OtelThresholds {
	return OtelThresholds{FailPct: 1, QueuePct: 80}
}

// ParseOtelThresholds builds thresholds from the defaults plus overrides read through `get` (pass os.Getenv).
// Keys: OTEL_FAIL_PCT, OTEL_QUEUE_PCT. An empty value keeps the default. A value that is not a number
// or is outside 0..100 returns an error naming the key.
func ParseOtelThresholds(get func(key string) string) (OtelThresholds, error) {
	th := DefaultOtelThresholds()
	for _, t := range []struct {
		key   string
		field *float64
	}{
		{"OTEL_FAIL_PCT", &th.FailPct},
		{"OTEL_QUEUE_PCT", &th.QueuePct},
	} {
		val := get(t.key)
		if val == "" {
			continue
		}
		f, err := strconv.ParseFloat(val, 64)
		if err != nil {
			return OtelThresholds{}, fmt.Errorf("%s: not a number", t.key)
		}
		if f < 0 || f > 100 {
			return OtelThresholds{}, fmt.Errorf("%s: out of range 0..100", t.key)
		}
		*t.field = f
	}
	return th, nil
}

// OtelExporter is the cumulative state of one exporter, summed over data types.
type OtelExporter struct {
	Sent, Failed        float64 // counters, metric points
	QueueSize, QueueCap float64 // gauges, batches
}

// OtelReceiver is the cumulative state of one receiver, summed over transports.
type OtelReceiver struct {
	Accepted, Refused, Failed float64 // counters, metric points
}

// OtelSample is one scrape of the collector's own Prometheus metrics.
type OtelSample struct {
	At         time.Time
	Exporters  map[string]OtelExporter
	Receivers  map[string]OtelReceiver
	RSS        float64 // bytes
	CPUSeconds float64 // total user + system CPU time
	Uptime     float64 // seconds
}

// OtelExporterState is one exporter row on the System tab. Rates need a previous sample (RatesKnown).
type OtelExporterState struct {
	Name         string  `json:"name"`
	SentPerSec   float64 `json:"sentPerSec"`
	FailedPerSec float64 `json:"failedPerSec"`
	RatesKnown   bool    `json:"ratesKnown"`
	QueueSize    float64 `json:"queueSize"`
	QueueCap     float64 `json:"queueCap"`
}

// OtelReceiverState is one receiver row on the System tab.
type OtelReceiverState struct {
	Name           string  `json:"name"`
	AcceptedPerSec float64 `json:"acceptedPerSec"`
	RefusedPerSec  float64 `json:"refusedPerSec"`
	FailedPerSec   float64 `json:"failedPerSec"`
	RatesKnown     bool    `json:"ratesKnown"`
}

// OtelState is the collector view served in the snapshot for the System tab.
type OtelState struct {
	Exporters []OtelExporterState `json:"exporters"`
	Receivers []OtelReceiverState `json:"receivers"`
	RSS       float64             `json:"rss"`      // bytes
	CPUPct    float64             `json:"cpuPct"`   // percent of one core since the previous poll
	CPUKnown  bool                `json:"cpuKnown"` // false on the first poll or after a counter reset
	Uptime    float64             `json:"uptime"`   // seconds
}

// ParseOtelMetrics reads the collector's Prometheus text (self-telemetry, default :8888/metrics).
// Counter names are accepted with or without the _total suffix (newer collectors add it). A body with
// no otelcol exporter or receiver series is an error, so a wrong URL is not reported as healthy.
func ParseOtelMetrics(body io.Reader, at time.Time) (OtelSample, error) {
	parser := expfmt.NewTextParser(model.UTF8Validation)
	families, err := parser.TextToMetricFamilies(body)
	if err != nil {
		return OtelSample{}, fmt.Errorf("parse otel metrics: %w", err)
	}

	s := OtelSample{
		At:        at,
		Exporters: make(map[string]OtelExporter),
		Receivers: make(map[string]OtelReceiver),
	}
	for _, family := range families {
		if family == nil || family.Name == nil {
			continue
		}
		name := strings.TrimSuffix(*family.Name, "_total")
		for _, metric := range family.Metric {
			if metric == nil {
				continue
			}
			value := metric.GetCounter().GetValue() + metric.GetGauge().GetValue()
			switch name {
			case "otelcol_exporter_sent_metric_points", "otelcol_exporter_send_failed_metric_points",
				"otelcol_exporter_queue_size", "otelcol_exporter_queue_capacity":
				exp := getLabelValue(metric, "exporter")
				if exp == "" {
					continue
				}
				e := s.Exporters[exp]
				switch name {
				case "otelcol_exporter_sent_metric_points":
					e.Sent += value
				case "otelcol_exporter_send_failed_metric_points":
					e.Failed += value
				case "otelcol_exporter_queue_size":
					e.QueueSize += value
				case "otelcol_exporter_queue_capacity":
					e.QueueCap += value
				}
				s.Exporters[exp] = e
			case "otelcol_receiver_accepted_metric_points", "otelcol_receiver_refused_metric_points",
				"otelcol_receiver_failed_metric_points":
				rcv := getLabelValue(metric, "receiver")
				if rcv == "" {
					continue
				}
				r := s.Receivers[rcv]
				switch name {
				case "otelcol_receiver_accepted_metric_points":
					r.Accepted += value
				case "otelcol_receiver_refused_metric_points":
					r.Refused += value
				case "otelcol_receiver_failed_metric_points":
					r.Failed += value
				}
				s.Receivers[rcv] = r
			case "otelcol_process_memory_rss":
				s.RSS = value
			case "otelcol_process_cpu_seconds":
				s.CPUSeconds = value
			case "otelcol_process_uptime":
				s.Uptime = value
			}
		}
	}

	if len(s.Exporters) == 0 && len(s.Receivers) == 0 {
		return OtelSample{}, fmt.Errorf("parse otel metrics: no otelcol exporter or receiver metrics")
	}
	return s, nil
}

// counterRate is the per-second increase of a counter over dt seconds. ok is false when dt is not
// positive or the counter went down (the collector restarted).
func counterRate(prev, cur, dt float64) (float64, bool) {
	if dt <= 0 || cur < prev {
		return 0, false
	}
	return (cur - prev) / dt, true
}

// buildOtelState turns one scrape, and the previous scrape if there is one, into the System tab view.
// Rows are sorted by name.
func buildOtelState(prev *OtelSample, cur OtelSample) OtelState {
	st := OtelState{
		Exporters: make([]OtelExporterState, 0, len(cur.Exporters)),
		Receivers: make([]OtelReceiverState, 0, len(cur.Receivers)),
		RSS:       cur.RSS,
		Uptime:    cur.Uptime,
	}

	dt := 0.0
	if prev != nil {
		dt = cur.At.Sub(prev.At).Seconds()
	}

	for name, e := range cur.Exporters {
		row := OtelExporterState{Name: name, QueueSize: e.QueueSize, QueueCap: e.QueueCap}
		if p, ok := prev.exporter(name); ok {
			sent, okSent := counterRate(p.Sent, e.Sent, dt)
			failed, okFailed := counterRate(p.Failed, e.Failed, dt)
			row.SentPerSec, row.FailedPerSec = sent, failed
			row.RatesKnown = okSent && okFailed
		}
		st.Exporters = append(st.Exporters, row)
	}
	sort.Slice(st.Exporters, func(i, j int) bool { return st.Exporters[i].Name < st.Exporters[j].Name })

	// Receiver rates are filled in by receiverRates, which needs state across polls
	for name := range cur.Receivers {
		st.Receivers = append(st.Receivers, OtelReceiverState{Name: name})
	}
	sort.Slice(st.Receivers, func(i, j int) bool { return st.Receivers[i].Name < st.Receivers[j].Name })

	if prev != nil && dt > 0 && cur.CPUSeconds >= prev.CPUSeconds {
		st.CPUPct = 100 * (cur.CPUSeconds - prev.CPUSeconds) / dt
		st.CPUKnown = true
	}
	return st
}

// exporter and receiver look up a row of a possibly nil previous sample.
func (s *OtelSample) exporter(name string) (OtelExporter, bool) {
	if s == nil {
		return OtelExporter{}, false
	}
	e, ok := s.Exporters[name]
	return e, ok
}

// otelRateStale is how long a receiver counter may stand still before its held rate drops to zero.
const otelRateStale = 5 * time.Minute

// receiverMark is the last point at which a receiver's counters changed, and the rates measured then.
type receiverMark struct {
	at  time.Time
	r   OtelReceiver
	row OtelReceiverState
}

// receiverRates fills in the receiver rows of one poll. Scraping receivers bump their counters once per
// scrape interval (often longer than the poll), so a plain poll-to-poll rate is mostly zero. Instead each
// rate is measured between two changes of the counters and held until the next change, dropping to zero
// once nothing changed for otelRateStale. marks keeps that state between polls.
func receiverRates(marks map[string]receiverMark, cur OtelSample, rows []OtelReceiverState) {
	for i := range rows {
		name := rows[i].Name
		r := cur.Receivers[name]
		m, ok := marks[name]
		switch {
		case !ok || r.Accepted < m.r.Accepted || r.Refused < m.r.Refused || r.Failed < m.r.Failed:
			// First sight or collector restart: start measuring from here
			marks[name] = receiverMark{at: cur.At, r: r, row: rows[i]}
		case r == m.r:
			if cur.At.Sub(m.at) > otelRateStale {
				rows[i] = OtelReceiverState{Name: name, RatesKnown: true}
			} else {
				rows[i] = m.row
			}
		default:
			dt := cur.At.Sub(m.at).Seconds()
			acc, _ := counterRate(m.r.Accepted, r.Accepted, dt)
			ref, _ := counterRate(m.r.Refused, r.Refused, dt)
			fail, _ := counterRate(m.r.Failed, r.Failed, dt)
			rows[i] = OtelReceiverState{Name: name, AcceptedPerSec: acc, RefusedPerSec: ref, FailedPerSec: fail, RatesKnown: true}
			marks[name] = receiverMark{at: cur.At, r: r, row: rows[i]}
		}
	}
}

// exportDelta sums, over the exporters present in both samples, the metric points sent and failed
// between prev and cur. ok is false without a previous sample, without a positive interval, or when no
// exporter is comparable. Exporters whose counters went down (restart) are left out.
func exportDelta(prev *OtelSample, cur OtelSample) (sent, failed, dt float64, ok bool) {
	if prev == nil {
		return 0, 0, 0, false
	}
	dt = cur.At.Sub(prev.At).Seconds()
	if dt <= 0 {
		return 0, 0, 0, false
	}
	for name, e := range cur.Exporters {
		p, found := prev.exporter(name)
		if !found || e.Sent < p.Sent || e.Failed < p.Failed {
			continue
		}
		sent += e.Sent - p.Sent
		failed += e.Failed - p.Failed
		ok = true
	}
	return sent, failed, dt, ok
}

// worstQueue returns the exporter whose retry queue is fullest, as a percent of its capacity.
// Exporters without a queue (capacity 0) are skipped. ok is false when no exporter has a queue.
func worstQueue(cur OtelSample) (name string, pct float64, ok bool) {
	for n, e := range cur.Exporters {
		if e.QueueCap <= 0 {
			continue
		}
		p := 100 * e.QueueSize / e.QueueCap
		if !ok || p > pct || (p == pct && n < name) {
			name, pct, ok = n, p, true
		}
	}
	return name, pct, ok
}

// evalOtel decides the Overview status of the collector from one poll. healthProblem and metricsProblem
// are the reasons the health endpoint or the metrics scrape failed, "" when fine or not configured.
// cur is nil when there is no scrape; prev is nil on the first poll, when only health and queue count.
// Not OK when: health fails, the scrape fails, the export failure ratio since prev is at or above
// th.FailPct (no traffic in the interval is not a failure), or any exporter queue is at or above th.QueuePct.
func evalOtel(healthProblem, metricsProblem string, prev, cur *OtelSample, th OtelThresholds) (bool, string) {
	if healthProblem != "" {
		return false, "health: " + healthProblem
	}
	if metricsProblem != "" {
		return false, "metrics: " + metricsProblem
	}
	if cur == nil {
		return true, "healthy"
	}

	var parts []string
	sent, failed, dt, rated := exportDelta(prev, *cur)
	if rated {
		parts = append(parts, fmt.Sprintf("sent %.0f points/s", sent/dt))
		if sent+failed > 0 {
			failPct := 100 * failed / (sent + failed)
			if failPct >= th.FailPct {
				return false, fmt.Sprintf("export failing: %.1f%% failed", failPct)
			}
			parts = append(parts, fmt.Sprintf("%.1f%% failed", failPct))
		}
	} else {
		parts = append(parts, "rate n/a")
	}

	if name, pct, ok := worstQueue(*cur); ok {
		if pct >= th.QueuePct {
			return false, fmt.Sprintf("exporter %s queue %.0f%% full", name, pct)
		}
		parts = append(parts, fmt.Sprintf("queue %.0f%%", pct))
	}
	return true, strings.Join(parts, ", ")
}

// checkOtelHealth returns "" when GET url gives HTTP 200 with JSON status "Server available"
// (the health_check extension), otherwise the reason.
func checkOtelHealth(ctx context.Context, hc *http.Client, url string) string {
	resp, err := doGet(ctx, hc, url)
	if err != nil {
		return err.Error()
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Sprintf("HTTP %d", resp.StatusCode)
	}

	var body struct {
		Status string `json:"status"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return fmt.Sprintf("parse health: %v", err)
	}
	if body.Status != "Server available" {
		return fmt.Sprintf("status %q", body.Status)
	}
	return ""
}

// scrapeOtel fetches and parses the collector's metrics at url.
func scrapeOtel(ctx context.Context, hc *http.Client, url string, at time.Time) (OtelSample, error) {
	resp, err := doGet(ctx, hc, url)
	if err != nil {
		return OtelSample{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return OtelSample{}, fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	return ParseOtelMetrics(resp.Body, at)
}

// OtelConfig holds the collector check settings. An empty URL skips that check.
type OtelConfig struct {
	HealthURL  string // "http://otel-collector:13133/"
	MetricsURL string // "http://otel-collector:8888/metrics"
	Thresholds OtelThresholds
}

// pollOtel runs one check. It returns the "otel-collector" component, the System tab state (nil when
// there is no scrape) and the scrape to pass as prev next time (nil when there is none).
func pollOtel(ctx context.Context, hc *http.Client, cfg OtelConfig, prev *OtelSample, now time.Time) (Component, *OtelState, *OtelSample) {
	healthProblem := ""
	if cfg.HealthURL != "" {
		healthProblem = checkOtelHealth(ctx, hc, cfg.HealthURL)
	}

	var cur *OtelSample
	metricsProblem := ""
	if cfg.MetricsURL != "" {
		s, err := scrapeOtel(ctx, hc, cfg.MetricsURL, now)
		if err != nil {
			metricsProblem = err.Error()
		} else {
			cur = &s
		}
	}

	ok, detail := evalOtel(healthProblem, metricsProblem, prev, cur, cfg.Thresholds)
	comp := Component{Name: "otel-collector", OK: ok, Detail: detail}
	if cur == nil {
		return comp, nil, nil
	}
	st := buildOtelState(prev, *cur)
	return comp, &st, cur
}

// RunOtel polls the collector every `every` (first poll immediately) until ctx is done, with a 5 second
// HTTP timeout per request. It keeps the "otel-collector" component and the System tab state current.
func RunOtel(ctx context.Context, st *Store, cfg OtelConfig, every time.Duration) {
	hc := &http.Client{Timeout: 5 * time.Second}
	var prev *OtelSample
	marks := make(map[string]receiverMark)

	poll := func() {
		comp, state, cur := pollOtel(ctx, hc, cfg, prev, time.Now())
		if state != nil {
			receiverRates(marks, *cur, state.Receivers)
		}
		st.SetComponent(comp)
		st.SetOtel(state)
		if cur != nil {
			prev = cur
		}
	}

	ticker := time.NewTicker(every)
	defer ticker.Stop()

	poll()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			poll()
		}
	}
}
