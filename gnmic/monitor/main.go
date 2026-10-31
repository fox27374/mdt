package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"os/signal"
	"regexp"
	"syscall"
	"time"
)

// env reads an environment variable, returning def if unset.
func env(key, def string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return def
}

// defaultHostSpecs returns the HOSTS and CONTAINER_EXPORTERS values. The local host name comes from
// LOCAL_HOST_NAME (default "docker-host"). Explicit values win. CONTAINER_EXPORTERS defaults to the local
// podman-exporter only when LOCAL_CONTAINER_EXPORTER is set (compose.yaml sets it; nested compose defaults do not parse).
func defaultHostSpecs(get func(string) string) (hosts, containerExporters string) {
	name := "docker-host"
	if v := get("LOCAL_HOST_NAME"); v != "" {
		name = v
	}
	hosts = get("HOSTS")
	if hosts == "" {
		hosts = name + "=http://host.containers.internal:9100"
	}
	containerExporters = get("CONTAINER_EXPORTERS")
	if containerExporters == "" && get("LOCAL_CONTAINER_EXPORTER") != "" {
		containerExporters = name + "=http://host.containers.internal:9882"
	}
	return hosts, containerExporters
}

// otelURLs returns the collector health and metrics URLs. A variable that is not set takes its compose
// default; a variable set to the empty string turns that check off. Both empty disables the collector check.
func otelURLs(lookup func(key string) (string, bool)) (health, metrics string) {
	return otelURL(lookup, "OTEL_HEALTH_URL", "http://otel-collector:13133/"),
		otelURL(lookup, "OTEL_METRICS_URL", "http://otel-collector:8888/metrics")
}

func otelURL(lookup func(key string) (string, bool), key, def string) string {
	if v, ok := lookup(key); ok {
		return v
	}
	return def
}

// statusHandler returns an HTTP handler that serves the current snapshot as JSON.
func statusHandler(st *Store) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(w).Encode(st.Snapshot(time.Now())); err != nil {
			log.Printf("error encoding snapshot: %v", err)
		}
	}
}

func main() {
	// Read environment variables
	listen := env("LISTEN", ":8080")
	collectorsStr := env("COLLECTORS", "gnmic-1=http://gnmic-1:8800,gnmic-2=http://gnmic-2:8800")
	natsURL := env("NATS_URL", "nats://nats:4222")
	natsSubject := env("NATS_SUBJECT", "mdt")
	natsMonURL := env("NATS_MON_URL", "http://nats:8222")
	consulURL := env("CONSUL_URL", "http://consul:8500")
	clusterName := env("CLUSTER_NAME", "mdt")
	outputURL := env("OUTPUT_URL", "http://gnmic-output:9273/metrics")
	mdtConfig := env("MDT_CONFIG", "/app/config/mdt.yaml")
	pollIntervalStr := env("POLL_INTERVAL", "15s")
	hostsStr, containerExportersStr := defaultHostSpecs(os.Getenv)
	hostNICIncludeStr := env("HOST_NIC_INCLUDE", "^(en|eth|em|bond|ib)[a-z0-9]*$")
	containerIncludeStr := env("CONTAINER_INCLUDE", "")

	// Parse collectors
	cols, err := ParseCollectors(collectorsStr)
	if err != nil {
		log.Fatalf("parse collectors: %v", err)
	}

	// Parse poll interval
	poll, err := time.ParseDuration(pollIntervalStr)
	if err != nil {
		log.Fatalf("parse poll interval: %v", err)
	}

	// Parse hosts
	hosts, err := ParseHosts(hostsStr)
	if err != nil {
		log.Fatalf("parse hosts: %v", err)
	}

	// Parse thresholds
	th, err := ParseThresholds(os.Getenv)
	if err != nil {
		log.Fatalf("parse thresholds: %v", err)
	}

	// Parse OpenTelemetry collector thresholds
	otelTh, err := ParseOtelThresholds(os.Getenv)
	if err != nil {
		log.Fatalf("parse otel thresholds: %v", err)
	}
	otelHealthURL, otelMetricsURL := otelURLs(os.LookupEnv)

	// Parse container exporters (host name = podman exporter URL)
	containerExporters, err := ParseHosts(containerExportersStr)
	if err != nil {
		log.Fatalf("parse CONTAINER_EXPORTERS: %v", err)
	}

	// Compile container include pattern (empty matches all containers)
	containerInclude, err := regexp.Compile(containerIncludeStr)
	if err != nil {
		log.Fatalf("compile CONTAINER_INCLUDE pattern: %v", err)
	}

	// Compile NIC include pattern
	hostNICInclude, err := regexp.Compile(hostNICIncludeStr)
	if err != nil {
		log.Fatalf("compile HOST_NIC_INCLUDE pattern: %v", err)
	}

	// Create store
	st := NewStore(time.Now())

	// Set up signal handling
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// Start collectors in goroutines
	go RunAPI(ctx, st, cols, poll)
	go RunConfig(ctx, st, mdtConfig, 60*time.Second)
	go RunNATS(ctx, st, natsURL, natsSubject)
	go RunMetrics(ctx, st, cols, poll)
	go RunInfra(ctx, st, InfraConfig{
		ConsulURL:  consulURL,
		NATSMonURL: natsMonURL,
		OutputURL:  outputURL,
		Collectors: cols,
		LockPrefix: "gnmic/" + clusterName + "/targets/",
	}, poll)
	if otelHealthURL != "" || otelMetricsURL != "" {
		go RunOtel(ctx, st, OtelConfig{
			HealthURL:  otelHealthURL,
			MetricsURL: otelMetricsURL,
			Thresholds: otelTh,
		}, poll)
	}
	if len(hosts) > 0 {
		go RunHosts(ctx, st, hosts, th, hostNICInclude, poll)
	}
	if len(containerExporters) > 0 {
		go RunContainers(ctx, st, containerExporters, containerInclude, poll)
	}

	// Set up HTTP routes
	mux := http.NewServeMux()
	mux.Handle("GET /", uiHandler())
	mux.HandleFunc("GET /api/status", statusHandler(st))
	mux.HandleFunc("GET /api/metrics", metricsHandler(outputURL))
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("ok"))
	})

	// Start HTTP server
	server := &http.Server{
		Addr:    listen,
		Handler: mux,
	}

	// Log startup
	log.Printf("listening on %s", listen)

	// Start server in a goroutine
	serverErr := make(chan error, 1)
	go func() {
		serverErr <- server.ListenAndServe()
	}()

	// Wait for shutdown signal or server error
	select {
	case <-ctx.Done():
		// Graceful shutdown
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := server.Shutdown(shutdownCtx); err != nil {
			log.Printf("server shutdown error: %v", err)
		}
	case err := <-serverErr:
		if err != http.ErrServerClosed {
			log.Fatalf("server error: %v", err)
		}
	}
}
