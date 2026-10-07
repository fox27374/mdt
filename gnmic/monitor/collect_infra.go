package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// InfraConfig holds the configuration for infrastructure health checks.
type InfraConfig struct {
	ConsulURL  string      // "http://consul:8500"
	NATSMonURL string      // "http://nats:8222"
	OutputURL  string      // "http://gnmic-output:9273/metrics"
	Collectors []Collector // expected collector instances, e.g. gnmic-1, gnmic-2
}

// natsPrev remembers the previous /varz sample to compute a message rate.
type natsPrev struct {
	inMsgs int64
	time   time.Time
}

// checkConsul returns Component{Name: "consul"}. OK only if ALL of these hold:
//   - GET <base>/v1/status/leader returns a non-empty leader string
//   - GET <base>/v1/agent/members: every member has Status == 1 (alive)
//   - GET <base>/v1/health/service/gnmic-api lists, for every expected collector name,
//     an instance whose Service.Tags contains "instance-name=<collector name>" and whose
//     Checks are all "passing"
//
// Detail when OK: "leader <leader>, <n> members alive, <k>/<k> collectors passing".
// Detail when not OK: the first failing reason.
func checkConsul(ctx context.Context, hc *http.Client, base string, expected []Collector) Component {
	// Check 1: Get leader
	leaderResp, err := doGet(ctx, hc, base+"/v1/status/leader")
	if err != nil {
		return Component{Name: "consul", OK: false, Detail: err.Error()}
	}
	defer leaderResp.Body.Close()

	if leaderResp.StatusCode != http.StatusOK {
		return Component{Name: "consul", OK: false, Detail: fmt.Sprintf("HTTP %d", leaderResp.StatusCode)}
	}

	leaderBody, err := io.ReadAll(leaderResp.Body)
	if err != nil {
		return Component{Name: "consul", OK: false, Detail: fmt.Sprintf("read leader: %v", err)}
	}

	var leader string
	if err := json.Unmarshal(leaderBody, &leader); err != nil {
		return Component{Name: "consul", OK: false, Detail: fmt.Sprintf("parse leader: %v", err)}
	}

	if leader == "" {
		return Component{Name: "consul", OK: false, Detail: "no leader"}
	}

	// Check 2: Get members
	membersResp, err := doGet(ctx, hc, base+"/v1/agent/members")
	if err != nil {
		return Component{Name: "consul", OK: false, Detail: err.Error()}
	}
	defer membersResp.Body.Close()

	if membersResp.StatusCode != http.StatusOK {
		return Component{Name: "consul", OK: false, Detail: fmt.Sprintf("HTTP %d", membersResp.StatusCode)}
	}

	membersBody, err := io.ReadAll(membersResp.Body)
	if err != nil {
		return Component{Name: "consul", OK: false, Detail: fmt.Sprintf("read members: %v", err)}
	}

	var members []map[string]interface{}
	if err := json.Unmarshal(membersBody, &members); err != nil {
		return Component{Name: "consul", OK: false, Detail: fmt.Sprintf("parse members: %v", err)}
	}

	aliveCount := 0
	for _, member := range members {
		if status, ok := member["Status"].(float64); ok && int(status) == 1 {
			aliveCount++
		} else if _, ok := member["Status"].(float64); ok {
			// This member is not alive
			if name, ok := member["Name"].(string); ok {
				return Component{Name: "consul", OK: false, Detail: fmt.Sprintf("member %s not alive", name)}
			}
			return Component{Name: "consul", OK: false, Detail: "member not alive"}
		}
	}

	// Check 3: Get health for gnmic-api service
	healthResp, err := doGet(ctx, hc, base+"/v1/health/service/mdt-gnmic-api")
	if err != nil {
		return Component{Name: "consul", OK: false, Detail: err.Error()}
	}
	defer healthResp.Body.Close()

	if healthResp.StatusCode != http.StatusOK {
		return Component{Name: "consul", OK: false, Detail: fmt.Sprintf("HTTP %d", healthResp.StatusCode)}
	}

	healthBody, err := io.ReadAll(healthResp.Body)
	if err != nil {
		return Component{Name: "consul", OK: false, Detail: fmt.Sprintf("read health: %v", err)}
	}

	var healthEntries []map[string]interface{}
	if err := json.Unmarshal(healthBody, &healthEntries); err != nil {
		return Component{Name: "consul", OK: false, Detail: fmt.Sprintf("parse health: %v", err)}
	}

	// Build a map of collectors we found
	foundCollectors := make(map[string]bool)
	for _, entry := range healthEntries {
		service, ok := entry["Service"].(map[string]interface{})
		if !ok {
			continue
		}

		// Extract tags
		tagsList, ok := service["Tags"].([]interface{})
		if !ok {
			continue
		}

		// Find instance-name tag
		var instanceName string
		for _, tag := range tagsList {
			tagStr, ok := tag.(string)
			if !ok {
				continue
			}
			if strings.HasPrefix(tagStr, "instance-name=") {
				instanceName = strings.TrimPrefix(tagStr, "instance-name=")
				break
			}
		}

		if instanceName == "" {
			continue
		}

		// Check if all checks are passing
		checks, ok := entry["Checks"].([]interface{})
		if !ok {
			continue
		}

		allPassing := true
		for _, check := range checks {
			checkMap, ok := check.(map[string]interface{})
			if !ok {
				allPassing = false
				break
			}
			status, ok := checkMap["Status"].(string)
			if !ok || status != "passing" {
				allPassing = false
				break
			}
		}

		if allPassing {
			foundCollectors[instanceName] = true
		}
	}

	// Check if all expected collectors were found and passing
	passingCount := 0
	for _, col := range expected {
		if foundCollectors[col.Name] {
			passingCount++
		} else {
			return Component{
				Name:   "consul",
				OK:     false,
				Detail: fmt.Sprintf("collector %s not registered or failing", col.Name),
			}
		}
	}

	totalCollectors := len(expected)
	detail := fmt.Sprintf("leader %s, %d members alive, %d/%d collectors passing", leader, aliveCount, passingCount, totalCollectors)
	return Component{Name: "consul", OK: true, Detail: detail}
}

// checkNATS returns Component{Name: "nats"}. OK only if:
//   - GET <base>/healthz returns HTTP 200
//   - GET <base>/varz parses successfully
//
// Detail when OK: "<connections> connections, <rate> msg/s in" where rate is
// (in_msgs - prev.in_msgs) / seconds since prev, printed with one decimal;
// on the first call (prev empty) print "rate n/a".
// Update prev in place.
// Detail when not OK: the request error or status.
func checkNATS(ctx context.Context, hc *http.Client, base string, prev *natsPrev, now time.Time) Component {
	// Check healthz
	healthResp, err := doGet(ctx, hc, base+"/healthz")
	if err != nil {
		return Component{Name: "nats", OK: false, Detail: err.Error()}
	}
	defer healthResp.Body.Close()

	if healthResp.StatusCode != http.StatusOK {
		return Component{Name: "nats", OK: false, Detail: fmt.Sprintf("HTTP %d", healthResp.StatusCode)}
	}

	// Get varz
	varzResp, err := doGet(ctx, hc, base+"/varz")
	if err != nil {
		return Component{Name: "nats", OK: false, Detail: err.Error()}
	}
	defer varzResp.Body.Close()

	if varzResp.StatusCode != http.StatusOK {
		return Component{Name: "nats", OK: false, Detail: fmt.Sprintf("HTTP %d", varzResp.StatusCode)}
	}

	varzBody, err := io.ReadAll(varzResp.Body)
	if err != nil {
		return Component{Name: "nats", OK: false, Detail: fmt.Sprintf("read varz: %v", err)}
	}

	var varzData map[string]interface{}
	if err := json.Unmarshal(varzBody, &varzData); err != nil {
		return Component{Name: "nats", OK: false, Detail: fmt.Sprintf("parse varz: %v", err)}
	}

	// Extract connections and in_msgs
	connections := int64(0)
	inMsgs := int64(0)

	if conn, ok := varzData["connections"].(float64); ok {
		connections = int64(conn)
	}

	if msgs, ok := varzData["in_msgs"].(float64); ok {
		inMsgs = int64(msgs)
	}

	// Compute rate
	var rateStr string
	if prev.time.IsZero() {
		rateStr = "rate n/a"
	} else {
		elapsed := now.Sub(prev.time).Seconds()
		if elapsed > 0 {
			rate := float64(inMsgs-prev.inMsgs) / elapsed
			rateStr = fmt.Sprintf("rate %.1f msg/s in", rate)
		} else {
			rateStr = "rate n/a"
		}
	}

	// Update prev
	prev.inMsgs = inMsgs
	prev.time = now

	detail := fmt.Sprintf("%d connections, %s", connections, rateStr)
	return Component{Name: "nats", OK: true, Detail: detail}
}

// checkOutput returns Component{Name: "gnmic-output"}: OK if GET <url> returns HTTP 200,
// Detail "serving metrics" (or the error / status code when not OK).
func checkOutput(ctx context.Context, hc *http.Client, url string) Component {
	resp, err := doGet(ctx, hc, url)
	if err != nil {
		return Component{Name: "gnmic-output", OK: false, Detail: err.Error()}
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return Component{Name: "gnmic-output", OK: false, Detail: fmt.Sprintf("HTTP %d", resp.StatusCode)}
	}

	return Component{Name: "gnmic-output", OK: true, Detail: "serving metrics"}
}

// RunInfra runs the three checks every `every` (first run immediately, 5 second HTTP timeout)
// until ctx is done, calling st.SetComponent for each result.
func RunInfra(ctx context.Context, st *Store, cfg InfraConfig, every time.Duration) {
	hc := &http.Client{
		Timeout: 5 * time.Second,
	}

	var natsPrevState natsPrev

	ticker := time.NewTicker(every)
	defer ticker.Stop()

	// Run immediately first
	runInfraChecks(ctx, st, hc, cfg, &natsPrevState)

	// Then run at the interval
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			runInfraChecks(ctx, st, hc, cfg, &natsPrevState)
		}
	}
}

// runInfraChecks runs all three infrastructure checks
func runInfraChecks(ctx context.Context, st *Store, hc *http.Client, cfg InfraConfig, natsPrevState *natsPrev) {
	now := time.Now()

	// Check Consul
	consulResult := checkConsul(ctx, hc, cfg.ConsulURL, cfg.Collectors)
	st.SetComponent(consulResult)

	// Check NATS
	natsResult := checkNATS(ctx, hc, cfg.NATSMonURL, natsPrevState, now)
	st.SetComponent(natsResult)

	// Check Output
	outputResult := checkOutput(ctx, hc, cfg.OutputURL)
	st.SetComponent(outputResult)
}

// doGet performs an HTTP GET request with the given context
func doGet(ctx context.Context, hc *http.Client, url string) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}
	return hc.Do(req)
}
