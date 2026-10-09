package main

import (
	"fmt"
	"io"
	"regexp"
	"sort"
	"strings"
	"time"

	"github.com/prometheus/common/expfmt"
	"github.com/prometheus/common/model"
)

type HostLevel string

const (
	LevelOK      HostLevel = "OK"
	LevelWarn    HostLevel = "WARN"
	LevelCrit    HostLevel = "CRIT"
	LevelUnknown HostLevel = "UNKNOWN"
)

// WorseLevel returns the more severe level. Severity from low to high: OK, UNKNOWN, WARN, CRIT.
func WorseLevel(a, b HostLevel) HostLevel {
	severity := map[HostLevel]int{
		LevelOK:      0,
		LevelUnknown: 1,
		LevelWarn:    2,
		LevelCrit:    3,
	}
	if severity[a] > severity[b] {
		return a
	}
	return b
}

type HostThresholds struct {
	CPUWarn, CPUCrit   float64 // percent
	MemWarn, MemCrit   float64
	DiskWarn, DiskCrit float64
	NetWarn, NetCrit   float64
}

// DefaultHostThresholds: CPU 80/95, memory 85/95, disk 80/90, network 70/90.
func DefaultHostThresholds() HostThresholds {
	return HostThresholds{
		CPUWarn:  80,
		CPUCrit:  95,
		MemWarn:  85,
		MemCrit:  95,
		DiskWarn: 80,
		DiskCrit: 90,
		NetWarn:  70,
		NetCrit:  90,
	}
}

type MetricState struct {
	Name   string    `json:"name"`            // "cpu", "memory", a mount point, or an interface name
	Value  float64   `json:"value"`           // percent; 0 when Level is UNKNOWN
	Level  HostLevel `json:"level"`
	Detail string    `json:"detail,omitempty"`
}

type HostState struct {
	Name    string        `json:"name"`
	Level   HostLevel     `json:"level"`
	Reason  string        `json:"reason,omitempty"`
	CPU     MetricState   `json:"cpu"`
	Memory  MetricState   `json:"memory"`
	Disk    MetricState   `json:"disk"`    // the worst disk (copy of one entry of Disks)
	Network MetricState   `json:"network"` // the worst NIC (copy of one entry of NICs)
	Disks   []MetricState `json:"disks"`
	NICs    []MetricState `json:"nics"`
	// Containers is filled from the container exporter by the store at snapshot time.
	Containers []ContainerState `json:"containers"`
	MemTotal   float64          `json:"memTotal"` // bytes; used to tell a set memory limit from none
	Updated    time.Time        `json:"updated"`
}

type FSSample struct {
	Mount, Device, FSType string
	Size, Free, Avail     float64
}

type NICSample struct {
	Name       string
	RxBytes    float64
	TxBytes    float64
	SpeedBytes float64 // bytes per second, 0 if unknown
}

type HostSample struct {
	At                time.Time
	CPUIdle, CPUTotal float64 // seconds summed over all CPUs; idle is mode "idle", total is all modes
	MemTotal, MemAvail float64
	FS                []FSSample
	NICs              []NICSample
}

// ParseNodeMetrics reads Prometheus text with expfmt and fills the sample
func ParseNodeMetrics(body io.Reader, at time.Time, nicInclude *regexp.Regexp) (HostSample, error) {
	parser := expfmt.NewTextParser(model.UTF8Validation)
	families, err := parser.TextToMetricFamilies(body)
	if err != nil {
		return HostSample{}, fmt.Errorf("parse node metrics: %w", err)
	}

	sample := HostSample{
		At:   at,
		FS:   []FSSample{},
		NICs: []NICSample{},
	}

	// Default NIC pattern if not provided
	if nicInclude == nil {
		nicInclude = regexp.MustCompile(`^(en|eth|em|bond|ib)[a-z0-9]*$`)
	}

	// Build intermediate maps to collect data by key
	cpuData := make(map[string]float64) // cpu:mode -> value

	for _, family := range families {
		if family == nil || family.Name == nil {
			continue
		}

		name := *family.Name

		switch name {
		case "node_cpu_seconds_total":
			for _, metric := range family.Metric {
				if metric == nil || metric.Counter == nil {
					continue
				}
				cpu := getLabelValue(metric, "cpu")
				mode := getLabelValue(metric, "mode")
				if cpu != "" && mode != "" {
					key := cpu + ":" + mode
					cpuData[key] = metric.Counter.GetValue()
				}
			}

		case "node_memory_MemTotal_bytes":
			for _, metric := range family.Metric {
				if metric == nil || metric.Gauge == nil {
					continue
				}
				sample.MemTotal = metric.Gauge.GetValue()
			}

		case "node_memory_MemAvailable_bytes":
			for _, metric := range family.Metric {
				if metric == nil || metric.Gauge == nil {
					continue
				}
				sample.MemAvail = metric.Gauge.GetValue()
			}
		}
	}

	// Collect filesystem data
	fsSize := make(map[string]map[string]float64)    // device:fstype:mount -> size
	fsFree := make(map[string]map[string]float64)    // device:fstype:mount -> free
	fsAvail := make(map[string]map[string]float64)   // device:fstype:mount -> avail

	// Re-scan for filesystem metrics with a simpler approach
	for _, family := range families {
		if family == nil || family.Name == nil {
			continue
		}

		name := *family.Name

		switch name {
		case "node_filesystem_size_bytes":
			for _, metric := range family.Metric {
				if metric == nil || metric.Gauge == nil {
					continue
				}
				device := getLabelValue(metric, "device")
				fstype := getLabelValue(metric, "fstype")
				mountpoint := getLabelValue(metric, "mountpoint")
				if device != "" && fstype != "" && mountpoint != "" {
					key := device + ":" + fstype + ":" + mountpoint
					if fsSize[key] == nil {
						fsSize[key] = make(map[string]float64)
					}
					fsSize[key]["val"] = metric.Gauge.GetValue()
				}
			}

		case "node_filesystem_free_bytes":
			for _, metric := range family.Metric {
				if metric == nil || metric.Gauge == nil {
					continue
				}
				device := getLabelValue(metric, "device")
				fstype := getLabelValue(metric, "fstype")
				mountpoint := getLabelValue(metric, "mountpoint")
				if device != "" && fstype != "" && mountpoint != "" {
					key := device + ":" + fstype + ":" + mountpoint
					if fsFree[key] == nil {
						fsFree[key] = make(map[string]float64)
					}
					fsFree[key]["val"] = metric.Gauge.GetValue()
				}
			}

		case "node_filesystem_avail_bytes":
			for _, metric := range family.Metric {
				if metric == nil || metric.Gauge == nil {
					continue
				}
				device := getLabelValue(metric, "device")
				fstype := getLabelValue(metric, "fstype")
				mountpoint := getLabelValue(metric, "mountpoint")
				if device != "" && fstype != "" && mountpoint != "" {
					key := device + ":" + fstype + ":" + mountpoint
					if fsAvail[key] == nil {
						fsAvail[key] = make(map[string]float64)
					}
					fsAvail[key]["val"] = metric.Gauge.GetValue()
				}
			}
		}
	}

	// Filter filesystems: device starts with /dev/, fstype not squashfs, size > 0
	// For duplicate devices, keep shortest mount point
	deviceMounts := make(map[string]FSSample) // device -> best FSSample (shortest mount)

	for key, sizeData := range fsSize {
		parts := strings.Split(key, ":")
		if len(parts) != 3 {
			continue
		}
		device, fstype, mountpoint := parts[0], parts[1], parts[2]

		// Filter checks
		if !strings.HasPrefix(device, "/dev/") {
			continue
		}
		if fstype == "squashfs" {
			continue
		}
		size := sizeData["val"]
		if size <= 0 {
			continue
		}

		free := fsFree[key]["val"]
		avail := fsAvail[key]["val"]

		fs := FSSample{
			Mount:  mountpoint,
			Device: device,
			FSType: fstype,
			Size:   size,
			Free:   free,
			Avail:  avail,
		}

		// Keep the shortest mount point for each device
		if existing, ok := deviceMounts[device]; !ok || len(mountpoint) < len(existing.Mount) {
			deviceMounts[device] = fs
		}
	}

	// Add to sample
	for _, fs := range deviceMounts {
		sample.FS = append(sample.FS, fs)
	}

	// Sort FS by mount point
	sort.Slice(sample.FS, func(i, j int) bool {
		return sample.FS[i].Mount < sample.FS[j].Mount
	})

	// Handle network interfaces
	nicRx := make(map[string]float64)    // device -> rx_bytes
	nicTx := make(map[string]float64)    // device -> tx_bytes
	nicSpeed := make(map[string]float64) // device -> speed_bytes

	for _, family := range families {
		if family == nil || family.Name == nil {
			continue
		}

		name := *family.Name

		switch name {
		case "node_network_receive_bytes_total":
			for _, metric := range family.Metric {
				if metric == nil || metric.Counter == nil {
					continue
				}
				device := getLabelValue(metric, "device")
				if device != "" {
					nicRx[device] = metric.Counter.GetValue()
				}
			}

		case "node_network_transmit_bytes_total":
			for _, metric := range family.Metric {
				if metric == nil || metric.Counter == nil {
					continue
				}
				device := getLabelValue(metric, "device")
				if device != "" {
					nicTx[device] = metric.Counter.GetValue()
				}
			}

		case "node_network_speed_bytes":
			for _, metric := range family.Metric {
				if metric == nil || metric.Gauge == nil {
					continue
				}
				device := getLabelValue(metric, "device")
				if device != "" {
					speed := metric.Gauge.GetValue()
					// Negative speed means unknown, convert to 0
					if speed < 0 {
						speed = 0
					}
					nicSpeed[device] = speed
				}
			}
		}
	}

	// Filter NICs by pattern and collect
	for device, rx := range nicRx {
		if !nicInclude.MatchString(device) {
			continue
		}
		tx := nicTx[device]
		speed := nicSpeed[device]
		sample.NICs = append(sample.NICs, NICSample{
			Name:       device,
			RxBytes:    rx,
			TxBytes:    tx,
			SpeedBytes: speed,
		})
	}

	// Sort NICs by name
	sort.Slice(sample.NICs, func(i, j int) bool {
		return sample.NICs[i].Name < sample.NICs[j].Name
	})

	// Sum all modes for all CPUs
	allCPUsTotal := 0.0
	allCPUsIdle := 0.0

	for key, val := range cpuData {
		parts := strings.Split(key, ":")
		if len(parts) == 2 && parts[1] == "idle" {
			allCPUsIdle += val
		}
		allCPUsTotal += val
	}

	sample.CPUTotal = allCPUsTotal
	sample.CPUIdle = allCPUsIdle

	// Validate required metrics
	if sample.CPUTotal == 0 {
		return HostSample{}, fmt.Errorf("parse node metrics: missing or empty node_cpu_seconds_total")
	}
	if sample.MemTotal == 0 {
		return HostSample{}, fmt.Errorf("parse node metrics: missing or empty node_memory_MemTotal_bytes")
	}

	return sample, nil
}

// EvalHost evaluates host state from samples
func EvalHost(name string, samples []HostSample, now time.Time, th HostThresholds) HostState {
	state := HostState{
		Name:    name,
		Level:   LevelUnknown,
		Disks:   []MetricState{},
		NICs:    []MetricState{},
		Updated: now,
	}

	if len(samples) == 0 {
		state.Level = LevelUnknown
		state.Reason = "no data"
		return state
	}

	// The newest sample is the last one
	newest := samples[len(samples)-1]
	state.Updated = newest.At
	state.MemTotal = newest.MemTotal

	// Evaluate CPU
	state.CPU = evalCPU(samples, th)

	// Evaluate Memory
	state.Memory = evalMemory(newest, th)

	// Evaluate Disks
	state.Disks = evalDisks(newest, th)
	if len(state.Disks) > 0 {
		state.Disk = findWorstMetric(state.Disks)
	} else {
		state.Disk = MetricState{
			Name:   "disk",
			Level:  LevelUnknown,
			Detail: "none found",
		}
	}

	// Evaluate NICs
	state.NICs = evalNICs(samples, th)
	if len(state.NICs) > 0 {
		state.Network = findWorstMetric(state.NICs)
	} else {
		state.Network = MetricState{
			Name:   "network",
			Level:  LevelUnknown,
			Detail: "none found",
		}
	}

	// Determine overall host level
	allMetrics := []MetricState{state.CPU, state.Memory}
	allMetrics = append(allMetrics, state.Disks...)
	allMetrics = append(allMetrics, state.NICs...)

	state.Level = aggregateLevel(allMetrics)

	// Build reason string
	if state.Level != LevelOK && state.Level != LevelUnknown {
		state.Reason = buildReason(allMetrics)
	}

	return state
}

// evalCPU evaluates CPU utilization from samples
func evalCPU(samples []HostSample, th HostThresholds) MetricState {
	metric := MetricState{Name: "cpu"}

	if len(samples) == 0 {
		metric.Level = LevelUnknown
		return metric
	}

	newest := samples[len(samples)-1]

	// Find oldest sample within 5 minutes
	fiveMinAgo := newest.At.Add(-5 * time.Minute)
	var reference HostSample
	referenceFound := false

	for _, s := range samples {
		if s.At.After(fiveMinAgo) || s.At.Equal(fiveMinAgo) {
			reference = s
			referenceFound = true
			break
		}
	}

	// If no reference or reference is the newest, CPU is UNKNOWN
	if !referenceFound || reference.At.Equal(newest.At) {
		metric.Level = LevelUnknown
		return metric
	}

	// Calculate deltas
	deltaIdle := newest.CPUIdle - reference.CPUIdle
	deltaTotal := newest.CPUTotal - reference.CPUTotal

	if deltaTotal <= 0 || deltaIdle < 0 {
		metric.Level = LevelUnknown
		return metric
	}

	// Calculate CPU utilization
	cpuUsage := 100.0 * (1.0 - deltaIdle/deltaTotal)
	cpuUsage = clamp(cpuUsage, 0, 100)

	metric.Value = cpuUsage
	metric.Level = levelFor(cpuUsage, th.CPUWarn, th.CPUCrit)

	return metric
}

// evalMemory evaluates memory utilization
func evalMemory(sample HostSample, th HostThresholds) MetricState {
	metric := MetricState{Name: "memory"}

	if sample.MemTotal == 0 {
		metric.Level = LevelUnknown
		return metric
	}

	usage := 100.0 * (1.0 - sample.MemAvail/sample.MemTotal)
	usage = clamp(usage, 0, 100)

	metric.Value = usage
	metric.Level = levelFor(usage, th.MemWarn, th.MemCrit)

	return metric
}

// evalDisks evaluates disk utilization
func evalDisks(sample HostSample, th HostThresholds) []MetricState {
	var disks []MetricState

	for _, fs := range sample.FS {
		used := fs.Size - fs.Free
		denom := used + fs.Avail
		var usage float64
		if denom > 0 {
			usage = 100.0 * used / denom
		}
		usage = clamp(usage, 0, 100)

		detail := fmt.Sprintf("%s %s, %s free", fs.Device, fs.FSType, formatBytes(fs.Avail))

		disk := MetricState{
			Name:   fs.Mount,
			Value:  usage,
			Level:  levelFor(usage, th.DiskWarn, th.DiskCrit),
			Detail: detail,
		}
		disks = append(disks, disk)
	}

	return disks
}

// evalNICs evaluates network interface utilization
func evalNICs(samples []HostSample, th HostThresholds) []MetricState {
	var nics []MetricState

	if len(samples) == 0 {
		return nics
	}

	newest := samples[len(samples)-1]

	// For each NIC in the newest sample
	for _, nic := range newest.NICs {
		metric := MetricState{Name: nic.Name}

		// Find reference (oldest sample within 1 minute with this NIC)
		oneMinAgo := newest.At.Add(-1 * time.Minute)
		var refSample *HostSample
		var refNIC *NICSample

		// Find the oldest sample within the 1-minute window
		for i := 0; i < len(samples); i++ {
			s := &samples[i]
			// Check if this sample is within the window (>= oneMinAgo, <= newest.At)
			if (s.At.After(oneMinAgo) || s.At.Equal(oneMinAgo)) && (s.At.Before(newest.At) || s.At.Equal(newest.At)) {
				// Look for this NIC in this sample
				for j := range s.NICs {
					if s.NICs[j].Name == nic.Name {
						refSample = s
						refNIC = &s.NICs[j]
						// Once we set it, we keep it as we iterate forward
						// The last match will be the newest, but we want the oldest
						// So let's continue without breaking
					}
				}
			}
		}

		// We want the OLDEST one, so let's restart
		refSample = nil
		refNIC = nil
		for i := 0; i < len(samples); i++ {
			s := &samples[i]
			// Check if this sample is within the window
			if (s.At.After(oneMinAgo) || s.At.Equal(oneMinAgo)) && (s.At.Before(newest.At) || s.At.Equal(newest.At)) {
				// Look for this NIC in this sample
				for j := range s.NICs {
					if s.NICs[j].Name == nic.Name {
						if refSample == nil {
							// First (oldest) match found
							refSample = s
							refNIC = &s.NICs[j]
						}
						break
					}
				}
			}
		}

		// Check if we have a usable reference
		if refSample == nil || refNIC == nil {
			metric.Level = LevelUnknown
			metric.Detail = "no rate yet"
			nics = append(nics, metric)
			continue
		}

		// Check time delta
		timeDelta := newest.At.Sub(refSample.At).Seconds()
		if timeDelta <= 0 {
			metric.Level = LevelUnknown
			metric.Detail = "no rate yet"
			nics = append(nics, metric)
			continue
		}

		// Check for counter wraparound
		deltaRx := nic.RxBytes - refNIC.RxBytes
		deltaTx := nic.TxBytes - refNIC.TxBytes

		if deltaRx < 0 || deltaTx < 0 {
			metric.Level = LevelUnknown
			metric.Detail = "counter wrapped"
			nics = append(nics, metric)
			continue
		}

		// Check link speed
		if nic.SpeedBytes == 0 {
			metric.Level = LevelUnknown
			metric.Detail = "link speed unknown"
			nics = append(nics, metric)
			continue
		}

		// Calculate bit rates
		rxRate := 8 * deltaRx / timeDelta // bits per second
		txRate := 8 * deltaTx / timeDelta  // bits per second
		maxRate := rxRate
		if txRate > maxRate {
			maxRate = txRate
		}

		// Calculate utilization as percentage
		linkCapacity := nic.SpeedBytes * 8 // bits per second
		usage := 100.0 * maxRate / linkCapacity
		usage = clamp(usage, 0, 100)

		metric.Value = usage
		metric.Level = levelFor(usage, th.NetWarn, th.NetCrit)
		metric.Detail = fmt.Sprintf("rx %s, tx %s of %s", formatBitRate(rxRate), formatBitRate(txRate), formatBitRate(linkCapacity))

		nics = append(nics, metric)
	}

	return nics
}

// Helper functions

func levelFor(value, warn, crit float64) HostLevel {
	if value >= crit {
		return LevelCrit
	}
	if value >= warn {
		return LevelWarn
	}
	return LevelOK
}

func clamp(value, min, max float64) float64 {
	if value < min {
		return min
	}
	if value > max {
		return max
	}
	return value
}

func formatBytes(b float64) string {
	const (
		KB = 1024
		MB = 1024 * KB
		GB = 1024 * MB
		TB = 1024 * GB
	)

	switch {
	case b >= TB:
		return fmt.Sprintf("%.1f TiB", b/TB)
	case b >= GB:
		return fmt.Sprintf("%.1f GiB", b/GB)
	case b >= MB:
		return fmt.Sprintf("%.1f MiB", b/MB)
	case b >= KB:
		return fmt.Sprintf("%.1f KiB", b/KB)
	default:
		return fmt.Sprintf("%.1f B", b)
	}
}

func formatBitRate(bitsSec float64) string {
	const (
		Kbit = 1000
		Mbit = 1000 * Kbit
		Gbit = 1000 * Mbit
	)

	switch {
	case bitsSec >= Gbit:
		return fmt.Sprintf("%.1f Gbit/s", bitsSec/Gbit)
	case bitsSec >= Mbit:
		return fmt.Sprintf("%.1f Mbit/s", bitsSec/Mbit)
	case bitsSec >= Kbit:
		return fmt.Sprintf("%.1f Kbit/s", bitsSec/Kbit)
	default:
		return fmt.Sprintf("%.0f bit/s", bitsSec)
	}
}

func findWorstMetric(metrics []MetricState) MetricState {
	if len(metrics) == 0 {
		return MetricState{}
	}

	worst := metrics[0]
	for i := 1; i < len(metrics); i++ {
		if WorseLevel(metrics[i].Level, worst.Level) == metrics[i].Level {
			worst = metrics[i]
		} else if WorseLevel(metrics[i].Level, worst.Level) == worst.Level && metrics[i].Level == worst.Level && metrics[i].Value > worst.Value {
			// Same level, pick higher value
			worst = metrics[i]
		}
	}

	return worst
}

func aggregateLevel(metrics []MetricState) HostLevel {
	hasNonUnknown := false
	worstLevel := LevelOK

	for _, m := range metrics {
		if m.Level != LevelUnknown {
			hasNonUnknown = true
			worstLevel = WorseLevel(worstLevel, m.Level)
		}
	}

	if !hasNonUnknown {
		return LevelUnknown
	}

	return worstLevel
}

func buildReason(metrics []MetricState) string {
	// Collect non-OK metrics
	var nonOK []MetricState
	for _, m := range metrics {
		if m.Level != LevelOK && m.Level != LevelUnknown {
			nonOK = append(nonOK, m)
		}
	}

	if len(nonOK) == 0 {
		return ""
	}

	// Sort by level (worst first), then by value (highest first)
	sort.Slice(nonOK, func(i, j int) bool {
		if WorseLevel(nonOK[i].Level, nonOK[j].Level) != nonOK[i].Level {
			return false // nonOK[j] is worse
		}
		if WorseLevel(nonOK[i].Level, nonOK[j].Level) != nonOK[j].Level {
			return true // nonOK[i] is worse
		}
		// Same level, sort by value descending
		return nonOK[i].Value > nonOK[j].Value
	})

	// Take up to 3
	if len(nonOK) > 3 {
		nonOK = nonOK[:3]
	}

	// Build reason string
	var parts []string
	for _, m := range nonOK {
		parts = append(parts, fmt.Sprintf("%s %d%% %s", m.Name, int(m.Value+0.5), m.Level))
	}

	return strings.Join(parts, "; ")
}
