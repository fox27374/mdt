package main

import (
	"sort"
	"sync"
	"time"
)

type SeenRecord struct {
	LastSeen time.Time
	Count    uint64
}

type Store struct {
	mu              sync.RWMutex
	started         time.Time
	targets         map[string]map[string]TargetConfig // source -> (key -> config)
	issues          map[string][]Issue                  // source -> issues
	components      map[string]Component                // name -> component
	seen            map[string]map[string]SeenRecord    // targetKey -> (sub -> record)
	hosts           map[string]HostState                // name -> host state
	setConfigCount  map[string]int64                    // source -> counter (for determining latest owner)
	maxSetConfigID  int64                               // monotonically increasing counter
	hasCollectorSet bool                                // true if any non-"config" source called SetConfig
}

func NewStore(started time.Time) *Store {
	return &Store{
		started:        started,
		targets:        make(map[string]map[string]TargetConfig),
		issues:         make(map[string][]Issue),
		components:     make(map[string]Component),
		seen:           make(map[string]map[string]SeenRecord),
		hosts:          make(map[string]HostState),
		setConfigCount: make(map[string]int64),
	}
}

// SetConfig replaces everything previously set by `source`.
func (s *Store) SetConfig(source string, targets []TargetConfig) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.maxSetConfigID++
	s.setConfigCount[source] = s.maxSetConfigID

	if source != "config" {
		s.hasCollectorSet = true
	}

	// Build map of targets keyed by name or address
	targetsByKey := make(map[string]TargetConfig)
	for _, t := range targets {
		key := s.targetKey(t)
		targetsByKey[key] = t
	}

	s.targets[source] = targetsByKey
}

// SetIssues replaces all issues previously set by `source`.
func (s *Store) SetIssues(source string, issues []Issue) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.issues[source] = make([]Issue, len(issues))
	copy(s.issues[source], issues)
}

// SetComponent inserts or replaces the component with the same Name.
func (s *Store) SetComponent(c Component) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.components[c.Name] = c
}

// SetHost inserts or replaces the host state with the same Name.
func (s *Store) SetHost(h HostState) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.hosts[h.Name] = h
}

// Seen records one received event for (target, sub).
func (s *Store) Seen(target, sub string, at time.Time) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if _, ok := s.seen[target]; !ok {
		s.seen[target] = make(map[string]SeenRecord)
	}

	record := s.seen[target][sub]
	record.Count++
	record.LastSeen = at
	s.seen[target][sub] = record
}

// Snapshot returns the current state as a Snapshot.
func (s *Store) Snapshot(now time.Time) Snapshot {
	s.mu.RLock()
	defer s.mu.RUnlock()

	snap := Snapshot{
		Time:       now,
		Components: make([]Component, 0),
		Targets:    make([]TargetState, 0),
	}

	// Merge all targets from all sources by key
	targetsByKey := make(map[string]*mergedTarget)
	addresses := make(map[string]string) // key -> address

	for source := range s.targets {
		for _, targetCfg := range s.targets[source] {
			key := s.targetKey(targetCfg)

			if _, exists := targetsByKey[key]; !exists {
				targetsByKey[key] = &mergedTarget{
					Key:            key,
					Addresses:      make(map[string]bool),
					SubsBySource:   make(map[string]map[string]SubConfig), // source -> (subname -> config)
					Owners:         make(map[string]int64),                // collector -> setConfigCount
					TargetCfgByOwn: make(map[string]TargetConfig),        // owner -> targetconfig
				}
			}

			merged := targetsByKey[key]

			// Track addresses
			if targetCfg.Address != "" {
				merged.Addresses[targetCfg.Address] = true
				addresses[key] = targetCfg.Address
			}

			// Track subs by source
			if _, ok := merged.SubsBySource[source]; !ok {
				merged.SubsBySource[source] = make(map[string]SubConfig)
			}
			for _, sub := range targetCfg.Subs {
				merged.SubsBySource[source][sub.Name] = sub
			}

			// Track owners and their target configs
			if source != "config" && targetCfg.Owner != "" {
				merged.Owners[targetCfg.Owner] = s.setConfigCount[source]
				merged.TargetCfgByOwn[targetCfg.Owner] = targetCfg
			}
		}
	}

	// Build target states
	for _, merged := range targetsByKey {
		addr := addresses[merged.Key]

		// Determine owner (most recent collector SetConfig)
		var owner string
		var maxCount int64
		for o, count := range merged.Owners {
			if count > maxCount {
				maxCount = count
				owner = o
			}
		}

		// Get config subs (if any)
		configSubs := merged.SubsBySource["config"]

		// Get owner subs (if any)
		var ownerSubs map[string]SubConfig
		if owner != "" {
			ownerSubs = merged.SubsBySource[owner]
		}

		// Build the union of subs
		unionSubs := make(map[string]SubConfig)
		if ownerSubs != nil {
			for name, sub := range ownerSubs {
				unionSubs[name] = sub
			}
		}
		if configSubs != nil {
			for name, sub := range configSubs {
				// If not in owner, or if we need to include from config
				if _, ok := unionSubs[name]; !ok {
					unionSubs[name] = sub
				} else {
					// If in both, use owner's interval if > 0, else config's
					ownerInterval := unionSubs[name].Interval
					configInterval := sub.Interval
					if ownerInterval == 0 {
						// Owner doesn't have explicit interval, use config's
						cfg := unionSubs[name]
						cfg.Interval = configInterval
						unionSubs[name] = cfg
					}
				}
			}
		}

		// Build target-level reason
		var targetReasons []string

		// Rule 5a: no owner and at least one collector has called SetConfig
		if owner == "" && s.hasCollectorSet {
			targetReasons = append(targetReasons, "no collector owns this target")
		}

		// Rule 5b: matching target-level issues
		for source := range s.issues {
			for _, issue := range s.issues[source] {
				if issue.Sub == "" && s.matchesTarget(issue, merged.Key, addr, owner) {
					targetReasons = append(targetReasons, issue.Reason)
				}
			}
		}

		// Build subs
		subStates := make([]SubState, 0)
		for subName := range unionSubs {
			subCfg := unionSubs[subName]

			// Determine sub reason (rule 4)
			var subReason string

			// Rule 4a: sub is in config source with Interval == 0
			if configSub, inConfig := configSubs[subName]; inConfig && configSub.Interval == 0 {
				subReason = "subscription is not defined in mdt.yaml"
			}

			// Rule 4b: target has owner, sub in config, not in owner's list
			if subReason == "" && owner != "" {
				if _, inConfig := configSubs[subName]; inConfig {
					if _, inOwner := ownerSubs[subName]; !inOwner {
						subReason = "configured but not running on " + owner
					}
				}
			}

			// Rule 4c: matching issues
			if subReason == "" {
				for source := range s.issues {
					for _, issue := range s.issues[source] {
						if issue.Sub == subName && s.matchesTarget(issue, merged.Key, addr, owner) {
							subReason = issue.Reason
							break
						}
					}
					if subReason != "" {
						break
					}
				}
			}

			// Determine interval (rule 3)
			interval := subCfg.Interval
			if ownerSubs != nil {
				if ownerSub, ok := ownerSubs[subName]; ok && ownerSub.Interval > 0 {
					interval = ownerSub.Interval
				}
			}

			// Look up seen data (rule 6)
			var lastSeen *time.Time
			var count uint64
			if record, ok := s.seen[merged.Key][subName]; ok {
				lastSeen = &record.LastSeen
				count = record.Count
			}
			// Also check address
			if addr != "" && addr != merged.Key {
				if record, ok := s.seen[addr][subName]; ok {
					count += record.Count
					if lastSeen == nil || record.LastSeen.After(*lastSeen) {
						lastSeen = &record.LastSeen
					}
				}
			}

			// Eval status (rule 7)
			status := EvalSub(now, s.started, func() time.Time {
				if lastSeen == nil {
					return time.Time{}
				}
				return *lastSeen
			}(), interval, subReason)

			// Format reason (rule 7)
			var reason string
			switch status {
			case StatusError:
				reason = subReason
			case StatusStale:
				if lastSeen != nil {
					d := now.Sub(*lastSeen).Round(time.Second)
					reason = "no data for " + d.String()
				}
			case StatusNoData:
				reason = "no data received"
			}

			subStates = append(subStates, SubState{
				Name:     subName,
				Interval: interval.String(),
				LastSeen: lastSeen,
				Count:    count,
				Status:   status,
				Reason:   reason,
			})
		}

		// Sort subs by name
		sort.Slice(subStates, func(i, j int) bool {
			return subStates[i].Name < subStates[j].Name
		})

		// Determine target status (rule 8)
		targetStatus := StatusOK
		for _, sub := range subStates {
			targetStatus = Worse(targetStatus, sub.Status)
		}

		// If target has a reason, status is ERROR
		if len(targetReasons) > 0 {
			targetStatus = StatusError
		}

		snap.Targets = append(snap.Targets, TargetState{
			Name:    merged.Key,
			Address: addr,
			Owner:   owner,
			Status:  targetStatus,
			Reason:  joinReasons(targetReasons),
			Subs:    subStates,
		})
	}

	// Sort targets by name, then address (rule 9)
	sort.Slice(snap.Targets, func(i, j int) bool {
		if snap.Targets[i].Name != snap.Targets[j].Name {
			return snap.Targets[i].Name < snap.Targets[j].Name
		}
		return snap.Targets[i].Address < snap.Targets[j].Address
	})

	// Build components
	for _, comp := range s.components {
		snap.Components = append(snap.Components, comp)
	}

	// Sort components by name (rule 9)
	sort.Slice(snap.Components, func(i, j int) bool {
		return snap.Components[i].Name < snap.Components[j].Name
	})

	// Build hosts
	snap.Hosts = make([]HostState, 0)
	for _, host := range s.hosts {
		// Make a deep copy of the host state
		hostCopy := host
		// Copy the slices to prevent caller from modifying store data
		hostCopy.Disks = make([]MetricState, len(host.Disks))
		copy(hostCopy.Disks, host.Disks)
		hostCopy.NICs = make([]MetricState, len(host.NICs))
		copy(hostCopy.NICs, host.NICs)
		snap.Hosts = append(snap.Hosts, hostCopy)
	}

	// Sort hosts by level severity descending, then by name ascending
	sort.Slice(snap.Hosts, func(i, j int) bool {
		levelCmp := WorseLevel(snap.Hosts[i].Level, snap.Hosts[j].Level)
		if snap.Hosts[i].Level == snap.Hosts[j].Level {
			// Same level, sort by name ascending
			return snap.Hosts[i].Name < snap.Hosts[j].Name
		}
		// Different levels: return true if snap.Hosts[i] is worse (more severe)
		// WorseLevel returns the more severe level, so if it returns snap.Hosts[i].Level,
		// then snap.Hosts[i] is worse than snap.Hosts[j]
		return levelCmp == snap.Hosts[i].Level
	})

	return snap
}

// Helper: get target key (Name if present, else Address)
func (s *Store) targetKey(t TargetConfig) string {
	if t.Name != "" {
		return t.Name
	}
	return t.Address
}

// Helper: check if an issue matches a target
func (s *Store) matchesTarget(issue Issue, key, addr, owner string) bool {
	issueTarget := issue.Target
	// Issue matches if target matches key or addr
	if issueTarget != key && issueTarget != addr {
		return false
	}

	// Issue collector must be owner or issue from owner's collector
	if issue.Collector != owner && owner != "" {
		return false
	}

	return true
}

// Helper: join reasons with "; "
func joinReasons(reasons []string) string {
	if len(reasons) == 0 {
		return ""
	}
	result := reasons[0]
	for _, r := range reasons[1:] {
		result += "; " + r
	}
	return result
}

// Helper: merged target data during snapshot
type mergedTarget struct {
	Key            string
	Addresses      map[string]bool
	SubsBySource   map[string]map[string]SubConfig // source -> (subname -> config)
	Owners         map[string]int64                 // collector -> setConfigCount
	TargetCfgByOwn map[string]TargetConfig         // owner -> targetconfig
}
