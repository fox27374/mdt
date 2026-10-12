package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"sort"
	"strings"
	"time"

	dto "github.com/prometheus/client_model/go"
	"github.com/prometheus/common/expfmt"
	"github.com/prometheus/common/model"
)

const seriesLimit = 500

// Series is one flattened Prometheus sample.
type Series struct {
	Name   string            `json:"name"`
	Type   string            `json:"type"`
	Labels map[string]string `json:"labels"`
	Value  float64           `json:"value"`
}

// SeriesResult is the filtered view returned by /api/metrics.
type SeriesResult struct {
	Total  int      `json:"total"`
	Shown  int      `json:"shown"`
	Series []Series `json:"series"`
}

// flattenSeries turns text exposition into samples. Histograms and summaries
// keep only _sum and _count (buckets and quantiles are noise when troubleshooting).
func flattenSeries(families map[string]*dto.MetricFamily) []Series {
	var out []Series
	for name, f := range families {
		typ := strings.ToLower(f.GetType().String())
		for _, m := range f.Metric {
			labels := make(map[string]string, len(m.Label))
			for _, l := range m.Label {
				labels[l.GetName()] = l.GetValue()
			}
			add := func(n string, v float64) {
				out = append(out, Series{Name: n, Type: typ, Labels: labels, Value: v})
			}
			switch {
			case m.Gauge != nil:
				add(name, m.Gauge.GetValue())
			case m.Counter != nil:
				add(name, m.Counter.GetValue())
			case m.Untyped != nil:
				add(name, m.Untyped.GetValue())
			case m.Histogram != nil:
				add(name+"_sum", m.Histogram.GetSampleSum())
				add(name+"_count", float64(m.Histogram.GetSampleCount()))
			case m.Summary != nil:
				add(name+"_sum", m.Summary.GetSampleSum())
				add(name+"_count", float64(m.Summary.GetSampleCount()))
			}
		}
	}
	return out
}

// filterSeries keeps series whose name contains nameSub, whose labels match every
// "key" (present) or "key=valueSub" (value contains) in labelSpecs, and whose
// name/source label contains target. All matching is case-insensitive.
func filterSeries(all []Series, nameSub string, labelSpecs []string, target string, limit int) SeriesResult {
	nameSub = strings.ToLower(nameSub)
	target = strings.ToLower(target)
	var matched []Series
	for _, s := range all {
		if !strings.Contains(strings.ToLower(s.Name), nameSub) {
			continue
		}
		if target != "" &&
			!strings.Contains(strings.ToLower(s.Labels["name"]), target) &&
			!strings.Contains(strings.ToLower(s.Labels["source"]), target) {
			continue
		}
		ok := true
		for _, spec := range labelSpecs {
			k, v, hasV := strings.Cut(spec, "=")
			k = strings.TrimSpace(k)
			if k == "" {
				continue
			}
			lv, present := s.Labels[k]
			if !present || (hasV && !strings.Contains(strings.ToLower(lv), strings.ToLower(strings.TrimSpace(v)))) {
				ok = false
				break
			}
		}
		if ok {
			matched = append(matched, s)
		}
	}
	sort.Slice(matched, func(i, j int) bool {
		if matched[i].Name != matched[j].Name {
			return matched[i].Name < matched[j].Name
		}
		return fmt.Sprint(matched[i].Labels) < fmt.Sprint(matched[j].Labels)
	})
	res := SeriesResult{Total: len(all), Shown: len(matched), Series: matched}
	if len(matched) > limit {
		res.Series = matched[:limit]
		res.Shown = limit
	}
	if res.Series == nil {
		res.Series = []Series{}
	}
	return res
}

func fetchSeries(ctx context.Context, hc *http.Client, url string) ([]Series, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	resp, err := hc.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("GET %s: %s", url, resp.Status)
	}
	parser := expfmt.NewTextParser(model.UTF8Validation)
	families, err := parser.TextToMetricFamilies(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("parse metrics: %w", err)
	}
	return flattenSeries(families), nil
}

// metricsHandler serves GET /api/metrics?name=&label=k=v,k2&target= from the output scrape endpoint.
func metricsHandler(url string) http.HandlerFunc {
	hc := &http.Client{Timeout: 5 * time.Second}
	return func(w http.ResponseWriter, r *http.Request) {
		all, err := fetchSeries(r.Context(), hc, url)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		q := r.URL.Query()
		var specs []string
		for _, l := range q["label"] {
			specs = append(specs, strings.Split(l, ",")...)
		}
		w.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(w).Encode(filterSeries(all, q.Get("name"), specs, q.Get("target"), seriesLimit)); err != nil {
			log.Printf("error encoding metrics: %v", err)
		}
	}
}
