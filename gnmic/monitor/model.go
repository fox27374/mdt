package main

import "time"

type Status string

const (
	StatusOK      Status = "OK"
	StatusWaiting Status = "WAITING"
	StatusStale   Status = "STALE"
	StatusNoData  Status = "NO_DATA"
	StatusError   Status = "ERROR"
)

// Worse returns the more severe of a and b. Severity order, lowest to highest:
// OK, WAITING, STALE, NO_DATA, ERROR.
func Worse(a, b Status) Status {
	// Severity mapping: OK=0, WAITING=1, STALE=2, NO_DATA=3, ERROR=4
	severity := map[Status]int{
		StatusOK:      0,
		StatusWaiting: 1,
		StatusStale:   2,
		StatusNoData:  3,
		StatusError:   4,
	}
	if severity[a] > severity[b] {
		return a
	}
	return b
}

// StaleWindow is how long a subscription may stay silent before it is stale:
// 3 * interval, but never less than 2 minutes.
func StaleWindow(interval time.Duration) time.Duration {
	window := 3 * interval
	minWindow := 2 * time.Minute
	if window < minWindow {
		return minWindow
	}
	return window
}

// EvalSub decides the status of one subscription. Rules, in this order:
// 1. errReason != ""            -> StatusError
// 2. lastSeen.IsZero():
//      now-started < StaleWindow(interval) -> StatusWaiting
//      otherwise                           -> StatusNoData
// 3. now-lastSeen > StaleWindow(interval)  -> StatusStale
// 4. otherwise                             -> StatusOK
func EvalSub(now, started, lastSeen time.Time, interval time.Duration, errReason string) Status {
	if errReason != "" {
		return StatusError
	}

	if lastSeen.IsZero() {
		elapsed := now.Sub(started)
		window := StaleWindow(interval)
		if elapsed < window {
			return StatusWaiting
		}
		return StatusNoData
	}

	elapsed := now.Sub(lastSeen)
	window := StaleWindow(interval)
	if elapsed > window {
		return StatusStale
	}

	return StatusOK
}

// Input types (filled by the collectors).
type SubConfig struct {
	Name     string
	Interval time.Duration // 0 means "unknown / not defined"
}

type TargetConfig struct {
	Name    string // configured target name, e.g. "ibk-lab-sw98"; empty if none
	Address string // e.g. "172.24.80.240:57400"
	Owner   string // collector name that owns the target, e.g. "gnmic-1"; empty if unknown
	Subs    []SubConfig
}

// Issue is an error reported by a collector-side source (for example the gnmic metrics scraper).
// Target may be a target name or an address. Sub empty means the issue concerns the whole target.
type Issue struct {
	Collector string
	Target    string
	Sub       string
	Reason    string
}

type Collector struct {
	Name string // e.g. "gnmic-1"
	URL  string // e.g. "http://gnmic-1:8800" (no trailing slash)
}

// ParseCollectors parses "gnmic-1=http://gnmic-1:8800,gnmic-2=http://gnmic-2:8800".
// It trims spaces and trailing slashes on URLs and returns an error for an empty string
// or for an entry without "=" or with an empty name or URL.
func ParseCollectors(s string) ([]Collector, error) {
	if s == "" {
		return nil, ErrEmptyString
	}

	var collectors []Collector
	entries := splitComma(s)
	for _, entry := range entries {
		entry = trimSpace(entry)
		if entry == "" {
			continue
		}

		parts := splitEqual(entry)
		if len(parts) != 2 {
			return nil, ErrMissingEqual
		}

		name := trimSpace(parts[0])
		url := trimSpace(parts[1])

		if name == "" || url == "" {
			return nil, ErrEmptyNameOrURL
		}

		// Trim trailing slash from URL
		url = trimTrailingSlash(url)

		collectors = append(collectors, Collector{
			Name: name,
			URL:  url,
		})
	}

	if len(collectors) == 0 {
		return nil, ErrEmptyString
	}

	return collectors, nil
}

// Output types (served as JSON by /api/status).
type SubState struct {
	Name     string     `json:"name"`
	Interval string     `json:"interval"` // time.Duration.String(), "0s" if unknown
	LastSeen *time.Time `json:"last_seen"` // nil if never seen
	Count    uint64     `json:"count"`
	Status   Status     `json:"status"`
	Reason   string     `json:"reason,omitempty"`
}

type TargetState struct {
	Name    string     `json:"name"`
	Address string     `json:"address"`
	Owner   string     `json:"owner"`
	Status  Status     `json:"status"`
	Reason  string     `json:"reason,omitempty"`
	Subs    []SubState `json:"subs"`
}

type Component struct {
	Name   string `json:"name"`
	OK     bool   `json:"ok"`
	Detail string `json:"detail"`
}

type Snapshot struct {
	Time       time.Time     `json:"time"`
	Components []Component   `json:"components"`
	Targets    []TargetState `json:"targets"`
	Hosts      []HostState   `json:"hosts"`
}

// Helper functions for string parsing
var (
	ErrEmptyString    = &ParseError{"empty string"}
	ErrMissingEqual   = &ParseError{"missing '=' in entry"}
	ErrEmptyNameOrURL = &ParseError{"empty name or URL"}
)

type ParseError struct {
	msg string
}

func (e *ParseError) Error() string {
	return e.msg
}

func splitComma(s string) []string {
	var result []string
	current := ""
	for _, ch := range s {
		if ch == ',' {
			result = append(result, current)
			current = ""
		} else {
			current += string(ch)
		}
	}
	if current != "" {
		result = append(result, current)
	}
	return result
}

func splitEqual(s string) []string {
	var result []string
	current := ""
	for _, ch := range s {
		if ch == '=' {
			result = append(result, current)
			current = ""
		} else {
			current += string(ch)
		}
	}
	if current != "" {
		result = append(result, current)
	}
	return result
}

func trimSpace(s string) string {
	// Manual trim to avoid unicode.IsSpace
	start := 0
	end := len(s)
	for start < end && s[start] == ' ' || s[start] == '\t' || s[start] == '\n' || s[start] == '\r' {
		start++
	}
	for end > start && s[end-1] == ' ' || s[end-1] == '\t' || s[end-1] == '\n' || s[end-1] == '\r' {
		end--
	}
	return s[start:end]
}

func trimTrailingSlash(s string) string {
	if len(s) > 0 && s[len(s)-1] == '/' {
		return s[:len(s)-1]
	}
	return s
}
