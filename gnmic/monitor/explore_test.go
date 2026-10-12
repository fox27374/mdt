package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

const exploreBody = `# TYPE gnmic_target_up gauge
gnmic_target_up{name="r1"} 1
gnmic_target_up{name="r2"} 0
# TYPE gnmic_failed_total counter
gnmic_failed_total{source="r1",subscription="Cpu"} 3
# TYPE lat histogram
lat_bucket{le="1"} 1
lat_bucket{le="+Inf"} 2
lat_sum 5
lat_count 2
`

func TestMetricsHandlerFilter(t *testing.T) {
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(exploreBody))
	}))
	defer up.Close()
	all, err := fetchSeries(t.Context(), up.Client(), up.URL)
	if err != nil {
		t.Fatal(err)
	}
	if len(all) != 5 { // up x2, failed, lat_sum, lat_count
		t.Fatalf("total = %d, want 5", len(all))
	}
	cases := []struct {
		name   string
		labels []string
		target string
		want   int
	}{
		{"", nil, "", 5},
		{"TARGET_UP", nil, "", 2},
		{"", []string{"name=r2"}, "", 1},
		{"", []string{"subscription"}, "", 1},
		{"", []string{"subscription=cp"}, "R1", 1},
		{"", []string{`name="r2"`}, "", 1},
		{"gnmic_target_up", []string{`name="r1"`}, "", 1},
		{"", nil, "r1", 2},
		{"nope", nil, "", 0},
	}
	for _, c := range cases {
		if got := filterSeries(all, c.name, c.labels, c.target, 500).Shown; got != c.want {
			t.Errorf("%+v: shown = %d, want %d", c, got, c.want)
		}
	}
	if r := filterSeries(all, "", nil, "", 2); r.Shown != 2 || r.Total != 5 {
		t.Errorf("limit: %+v", r)
	}

	rec := httptest.NewRecorder()
	metricsHandler(up.URL)(rec, httptest.NewRequest("GET", "/api/metrics?name=up&label=name=r1", nil))
	if rec.Code != 200 || !strings.Contains(rec.Body.String(), `"shown":1`) {
		t.Errorf("handler: %d %s", rec.Code, rec.Body)
	}
}
