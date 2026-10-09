package main

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"sort"
	"time"

	"github.com/prometheus/common/expfmt"
	"github.com/prometheus/common/model"
)

// ContainerSample is one running container from a prometheus-podman-exporter scrape.
type ContainerSample struct {
	Name       string
	CPUSeconds float64 // podman_container_cpu_seconds_total (counter)
	MemUsed    float64 // podman_container_mem_usage_bytes
	MemLimit   float64 // podman_container_mem_limit_bytes (host memory when no --memory is set)
}

// ContainerState is one container row shown under its host.
type ContainerState struct {
	Name        string  `json:"name"`
	CPU         float64 `json:"cpu"`         // percent of one core, averaged over the last poll interval
	CPUKnown    bool    `json:"cpuKnown"`    // false on the first poll or after a counter reset
	MemUsed     float64 `json:"memUsed"`     // bytes
	MemLimitSet bool    `json:"memLimitSet"` // true when the limit is below the host's total memory
	MemPct      float64 `json:"memPct"`      // percent of the limit, only when MemLimitSet
}

// containerWindow is the previous scrape of one exporter, used for the CPU rate.
type containerWindow struct {
	At      time.Time
	Samples map[string]ContainerSample // by container name
}

// ParseContainerMetrics reads prometheus-podman-exporter text. Only containers with a CPU series
// (running ones) are returned, sorted by name. The include regex is matched against the name.
func ParseContainerMetrics(body io.Reader, include *regexp.Regexp) ([]ContainerSample, error) {
	parser := expfmt.NewTextParser(model.UTF8Validation)
	families, err := parser.TextToMetricFamilies(body)
	if err != nil {
		return nil, fmt.Errorf("parse container metrics: %w", err)
	}

	names := make(map[string]string)     // id -> name
	cpu := make(map[string]float64)      // id -> cpu seconds
	memUsed := make(map[string]float64)  // id -> bytes
	memLimit := make(map[string]float64) // id -> bytes

	for _, family := range families {
		if family == nil || family.Name == nil {
			continue
		}
		for _, metric := range family.Metric {
			if metric == nil {
				continue
			}
			id := getLabelValue(metric, "id")
			if id == "" {
				continue
			}
			switch *family.Name {
			case "podman_container_info":
				if name := getLabelValue(metric, "name"); name != "" {
					names[id] = name
				}
			case "podman_container_cpu_seconds_total":
				if metric.Counter != nil {
					cpu[id] = metric.Counter.GetValue()
				}
			case "podman_container_mem_usage_bytes":
				if metric.Gauge != nil {
					memUsed[id] = metric.Gauge.GetValue()
				}
			case "podman_container_mem_limit_bytes":
				if metric.Gauge != nil {
					memLimit[id] = metric.Gauge.GetValue()
				}
			}
		}
	}

	var out []ContainerSample
	for id, value := range cpu {
		name, ok := names[id]
		if !ok || (include != nil && !include.MatchString(name)) {
			continue
		}
		out = append(out, ContainerSample{
			Name:       name,
			CPUSeconds: value,
			MemUsed:    memUsed[id],
			MemLimit:   memLimit[id],
		})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Name < out[j].Name })
	return out, nil
}

// containerRows turns the current scrape into rows. CPU is a rate against the previous scrape;
// the first scrape, a missing previous sample, or a counter reset gives CPUKnown=false.
// The memory limit counts as set only when it is below memTotal (the host's total memory).
func containerRows(prev containerWindow, cur []ContainerSample, at time.Time, memTotal float64) []ContainerState {
	rows := make([]ContainerState, 0, len(cur))
	dt := at.Sub(prev.At).Seconds()

	for _, c := range cur {
		row := ContainerState{Name: c.Name, MemUsed: c.MemUsed}

		if p, ok := prev.Samples[c.Name]; ok && dt > 0 {
			if dc := c.CPUSeconds - p.CPUSeconds; dc >= 0 {
				row.CPU = 100 * dc / dt
				row.CPUKnown = true
			}
		}

		if c.MemLimit > 0 && memTotal > 0 && c.MemLimit < memTotal {
			row.MemLimitSet = true
			row.MemPct = clamp(100*c.MemUsed/c.MemLimit, 0, 100)
		}

		rows = append(rows, row)
	}
	return rows
}

// RunContainers scrapes each container exporter every `every` (first scrape immediately) until ctx
// is done. An unreachable exporter clears its rows; the host row is not affected.
func RunContainers(ctx context.Context, st *Store, targets []HostTarget, include *regexp.Regexp, every time.Duration) {
	client := &http.Client{Timeout: 5 * time.Second}
	windows := make(map[string]containerWindow) // by host name

	poll := func(now time.Time) {
		for _, target := range targets {
			samples, err := scrapeContainers(client, target.URL, include)
			if err != nil {
				delete(windows, target.Name)
				st.SetContainers(target.Name, nil)
				continue
			}
			st.SetContainers(target.Name, containerRows(windows[target.Name], samples, now, st.HostMemTotal(target.Name)))

			byName := make(map[string]ContainerSample, len(samples))
			for _, s := range samples {
				byName[s.Name] = s
			}
			windows[target.Name] = containerWindow{At: now, Samples: byName}
		}
	}

	ticker := time.NewTicker(every)
	defer ticker.Stop()

	poll(time.Now())
	for {
		select {
		case <-ctx.Done():
			return
		case now := <-ticker.C:
			poll(now)
		}
	}
}

func scrapeContainers(client *http.Client, url string, include *regexp.Regexp) ([]ContainerSample, error) {
	resp, err := client.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	return ParseContainerMetrics(resp.Body, include)
}
