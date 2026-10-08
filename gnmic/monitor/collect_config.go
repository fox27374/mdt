package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"sort"
	"time"

	"gopkg.in/yaml.v3"
)

// ParseConfig reads a gnmic collector config (YAML) and returns the intended targets.
// The relevant YAML shape:
//   targets:
//     <address>:
//       name: <name>            (optional)
//       subscriptions: [a, b]
//   subscriptions:
//     <sub-name>:
//       sample-interval: 30s    (optional, a Go duration string)
// Result, sorted by Address: one TargetConfig per target with Name (the `name` field, or the address
// if missing), Address (the map key), Owner "" and Subs in the order listed.
// Sub Interval: the parsed sample-interval of the defined subscription; 10s if the subscription is
// defined but has no sample-interval; 0 if the subscription name is NOT defined under `subscriptions:`.
// A defined subscription with an unparsable sample-interval makes ParseConfig return an error.
func ParseConfig(data []byte) ([]TargetConfig, error) {
	var raw map[string]interface{}
	if err := yaml.Unmarshal(data, &raw); err != nil {
		return nil, err
	}

	// Extract subscriptions map
	subsMap := make(map[string]time.Duration)
	if subsRaw, ok := raw["subscriptions"]; ok {
		if subsYAML, ok := subsRaw.(map[string]interface{}); ok {
			for subName, subCfg := range subsYAML {
				if subCfgMap, ok := subCfg.(map[string]interface{}); ok {
					if sampleIntervalRaw, ok := subCfgMap["sample-interval"]; ok && sampleIntervalRaw != nil {
						intervalStr := fmt.Sprintf("%v", sampleIntervalRaw)
						duration, err := time.ParseDuration(intervalStr)
						if err != nil {
							return nil, fmt.Errorf("unparsable sample-interval for subscription %q: %v", subName, err)
						}
						subsMap[subName] = duration
					} else {
						// Defined but no sample-interval (or nil) -> 10s
						subsMap[subName] = 10 * time.Second
					}
				}
			}
		}
	}

	// Extract targets
	var targets []TargetConfig
	if targetsRaw, ok := raw["targets"]; ok {
		if targetsYAML, ok := targetsRaw.(map[string]interface{}); ok {
			for address, targetCfg := range targetsYAML {
				targetCfgMap, ok := targetCfg.(map[string]interface{})
				if !ok {
					continue
				}

				// Get target name
				name := address
				if nameRaw, ok := targetCfgMap["name"]; ok {
					if nameStr, ok := nameRaw.(string); ok {
						name = nameStr
					}
				}

				// Get subscriptions
				var subs []SubConfig
				if subsListRaw, ok := targetCfgMap["subscriptions"]; ok {
					if subsList, ok := subsListRaw.([]interface{}); ok {
						for _, subRaw := range subsList {
							if subName, ok := subRaw.(string); ok {
								// Look up the subscription interval
								interval := time.Duration(0)
								if duration, ok := subsMap[subName]; ok {
									interval = duration
								}
								subs = append(subs, SubConfig{
									Name:     subName,
									Interval: interval,
								})
							}
						}
					}
				} else {
					// No explicit subscriptions list: use ALL defined subscriptions (gnmic's rule)
					for subName, interval := range subsMap {
						subs = append(subs, SubConfig{
							Name:     subName,
							Interval: interval,
						})
					}
					// Sort by name for consistent ordering
					sort.Slice(subs, func(i, j int) bool {
						return subs[i].Name < subs[j].Name
					})
				}

				targets = append(targets, TargetConfig{
					Name:    name,
					Address: address,
					Owner:   "",
					Subs:    subs,
				})
			}
		}
	}

	// Sort by Address
	sort.Slice(targets, func(i, j int) bool {
		return targets[i].Address < targets[j].Address
	})

	return targets, nil
}

// RunConfig reads the file at `path` immediately and then every `every` until ctx is done.
// On success: st.SetConfig("config", targets). On failure (unreadable file or bad YAML): log one line
// with the standard `log` package and keep the previous data.
func RunConfig(ctx context.Context, st *Store, path string, every time.Duration) {
	ticker := time.NewTicker(every)
	defer ticker.Stop()

	// Read immediately
	readAndSet := func() {
		data, err := readFile(path)
		if err != nil {
			log.Printf("failed to read config file %s: %v", path, err)
			return
		}

		targets, err := ParseConfig(data)
		if err != nil {
			log.Printf("failed to parse config file %s: %v", path, err)
			return
		}

		st.SetConfig("config", targets)
	}

	readAndSet()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			readAndSet()
		}
	}
}

// Helper function to read file
func readFile(path string) ([]byte, error) {
	return os.ReadFile(path)
}
