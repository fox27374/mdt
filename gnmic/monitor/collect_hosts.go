package main

import (
	"context"
	"fmt"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"
)

type HostTarget struct {
	Name string // e.g. "docker-host"
	URL  string // full scrape URL, e.g. "http://host.containers.internal:9100/metrics"
}

// ParseHosts parses "name=http://addr:9100,name2=http://addr2:9100/metrics".
// Spaces around entries are trimmed. An empty string returns (nil, nil): the feature is off.
// A URL without a path (nothing after host:port, after trimming a trailing slash) gets "/metrics" appended.
// An entry without "=", with an empty name, or with an empty URL, or a URL that does not start with
// http:// or https://, returns an error.
func ParseHosts(s string) ([]HostTarget, error) {
	if s == "" {
		return nil, nil
	}

	var hosts []HostTarget
	entries := splitComma(s)
	for _, entry := range entries {
		entry = trimSpace(entry)
		if entry == "" {
			continue
		}

		parts := splitEqual(entry)
		if len(parts) != 2 {
			return nil, fmt.Errorf("entry without '=': %q", entry)
		}

		// Trim name and URL, checking for empty strings
		nameRaw := parts[0]
		urlRaw := parts[1]

		// Check if raw parts are non-empty before trimming (to avoid bug in trimSpace)
		if nameRaw == "" {
			return nil, fmt.Errorf("empty name in entry: %q", entry)
		}
		if urlRaw == "" {
			return nil, fmt.Errorf("empty URL in entry: %q", entry)
		}

		name := trimSpace(nameRaw)
		url := trimSpace(urlRaw)

		if name == "" {
			return nil, fmt.Errorf("empty name in entry: %q", entry)
		}
		if url == "" {
			return nil, fmt.Errorf("empty URL in entry: %q", entry)
		}

		// Check scheme
		if !strings.HasPrefix(url, "http://") && !strings.HasPrefix(url, "https://") {
			return nil, fmt.Errorf("URL does not start with http:// or https://: %q", url)
		}

		// Trim trailing slash and append /metrics if needed
		url = trimTrailingSlash(url)
		if !strings.Contains(url[strings.Index(url, "://")+3:], "/") {
			url += "/metrics"
		}

		hosts = append(hosts, HostTarget{
			Name: name,
			URL:  url,
		})
	}

	return hosts, nil
}

// ParseThresholds builds thresholds from the defaults plus overrides read through `get` (pass os.Getenv).
// Keys: HOST_CPU_WARN, HOST_CPU_CRIT, HOST_MEM_WARN, HOST_MEM_CRIT, HOST_DISK_WARN, HOST_DISK_CRIT,
// HOST_NET_WARN, HOST_NET_CRIT. An empty value keeps the default. A value that is not a number,
// is outside 0..100, or gives warn >= crit for its pair returns an error naming the key.
func ParseThresholds(get func(key string) string) (HostThresholds, error) {
	th := DefaultHostThresholds()

	type threshold struct {
		key   string
		field *float64
		pair  string // for warn/crit pairs
	}

	thresholds := []threshold{
		{"HOST_CPU_WARN", &th.CPUWarn, "HOST_CPU_CRIT"},
		{"HOST_CPU_CRIT", &th.CPUCrit, "HOST_CPU_WARN"},
		{"HOST_MEM_WARN", &th.MemWarn, "HOST_MEM_CRIT"},
		{"HOST_MEM_CRIT", &th.MemCrit, "HOST_MEM_WARN"},
		{"HOST_DISK_WARN", &th.DiskWarn, "HOST_DISK_CRIT"},
		{"HOST_DISK_CRIT", &th.DiskCrit, "HOST_DISK_WARN"},
		{"HOST_NET_WARN", &th.NetWarn, "HOST_NET_CRIT"},
		{"HOST_NET_CRIT", &th.NetCrit, "HOST_NET_WARN"},
	}

	for _, t := range thresholds {
		val := get(t.key)
		if val == "" {
			continue
		}

		f, err := strconv.ParseFloat(val, 64)
		if err != nil {
			return HostThresholds{}, fmt.Errorf("%s: not a number", t.key)
		}

		if f < 0 || f > 100 {
			return HostThresholds{}, fmt.Errorf("%s: out of range 0..100", t.key)
		}

		*t.field = f
	}

	// Check warn >= crit constraints
	if th.CPUWarn >= th.CPUCrit {
		return HostThresholds{}, fmt.Errorf("HOST_CPU_WARN >= HOST_CPU_CRIT")
	}
	if th.MemWarn >= th.MemCrit {
		return HostThresholds{}, fmt.Errorf("HOST_MEM_WARN >= HOST_MEM_CRIT")
	}
	if th.DiskWarn >= th.DiskCrit {
		return HostThresholds{}, fmt.Errorf("HOST_DISK_WARN >= HOST_DISK_CRIT")
	}
	if th.NetWarn >= th.NetCrit {
		return HostThresholds{}, fmt.Errorf("HOST_NET_WARN >= HOST_NET_CRIT")
	}

	return th, nil
}

// RunHosts scrapes every host every `every` (first scrape immediately) until ctx is done, with a
// 5 second HTTP timeout per request. For each host it keeps the samples of the last 6 minutes.
func RunHosts(ctx context.Context, st *Store, hosts []HostTarget, th HostThresholds, nicInclude *regexp.Regexp, every time.Duration) {
	// Per-host sample windows
	windows := make(map[string][]HostSample)

	client := &http.Client{
		Timeout: 5 * time.Second,
	}

	ticker := time.NewTicker(every)
	defer ticker.Stop()

	// Poll immediately first
	now := time.Now()
	for _, host := range hosts {
		pollHost(st, client, host, windows, th, nicInclude, now)
	}

	// Then poll at the interval
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			now := time.Now()
			for _, host := range hosts {
				pollHost(st, client, host, windows, th, nicInclude, now)
			}
		}
	}
}

// pollHost makes one scrape and evaluation for a single host.
func pollHost(st *Store, client *http.Client, host HostTarget, windows map[string][]HostSample, th HostThresholds, nicInclude *regexp.Regexp, now time.Time) {
	resp, err := client.Get(host.URL)
	if err != nil {
		st.SetComponent(Component{
			Name:   "host " + host.Name,
			OK:     false,
			Detail: err.Error(),
		})
		st.SetHost(HostState{
			Name:    host.Name,
			Level:   LevelUnknown,
			Reason:  "exporter unreachable: " + err.Error(),
			Updated: now,
			Disks:   []MetricState{},
			NICs:    []MetricState{},
		})
		return
	}
	defer resp.Body.Close()

	// Check for non-200 status
	if resp.StatusCode != http.StatusOK {
		detail := fmt.Sprintf("HTTP %d", resp.StatusCode)
		st.SetComponent(Component{
			Name:   "host " + host.Name,
			OK:     false,
			Detail: detail,
		})
		st.SetHost(HostState{
			Name:    host.Name,
			Level:   LevelUnknown,
			Reason:  "exporter unreachable: " + detail,
			Updated: now,
			Disks:   []MetricState{},
			NICs:    []MetricState{},
		})
		return
	}

	// Parse metrics
	sample, err := ParseNodeMetrics(resp.Body, now, nicInclude)
	if err != nil {
		st.SetComponent(Component{
			Name:   "host " + host.Name,
			OK:     false,
			Detail: err.Error(),
		})
		st.SetHost(HostState{
			Name:    host.Name,
			Level:   LevelUnknown,
			Reason:  "exporter unreachable: " + err.Error(),
			Updated: now,
			Disks:   []MetricState{},
			NICs:    []MetricState{},
		})
		return
	}

	// Append sample and trim old ones (6 minutes = 360 seconds)
	if windows[host.Name] == nil {
		windows[host.Name] = []HostSample{}
	}
	windows[host.Name] = append(windows[host.Name], sample)

	cutoff := now.Add(-6 * time.Minute)
	for len(windows[host.Name]) > 0 && windows[host.Name][0].At.Before(cutoff) {
		windows[host.Name] = windows[host.Name][1:]
	}

	// Evaluate and store
	hostState := EvalHost(host.Name, windows[host.Name], now, th)
	st.SetHost(hostState)

	// Build detail string
	detail := buildHostDetail(hostState)
	st.SetComponent(Component{
		Name:   "host " + host.Name,
		OK:     true,
		Detail: detail,
	})
}

// buildHostDetail creates a short summary like "cpu 12%, memory 40%, 2 disks, 1 NIC"
func buildHostDetail(hs HostState) string {
	var parts []string

	// CPU
	if hs.CPU.Level == LevelUnknown {
		parts = append(parts, "cpu n/a")
	} else {
		parts = append(parts, fmt.Sprintf("cpu %d%%", int(hs.CPU.Value+0.5)))
	}

	// Memory
	parts = append(parts, fmt.Sprintf("memory %d%%", int(hs.Memory.Value+0.5)))

	// Disks count
	parts = append(parts, fmt.Sprintf("%d disks", len(hs.Disks)))

	// NICs count
	parts = append(parts, fmt.Sprintf("%d NIC", len(hs.NICs)))
	if len(hs.NICs) != 1 {
		parts[len(parts)-1] += "s"
	}

	return strings.Join(parts, ", ")
}
