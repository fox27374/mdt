package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestUIHandler(t *testing.T) {
	handler := uiHandler()

	t.Run("GET / returns 200 with HTML", func(t *testing.T) {
		w := httptest.NewRecorder()
		r := httptest.NewRequest("GET", "/", nil)
		handler.ServeHTTP(w, r)

		if w.Code != http.StatusOK {
			t.Errorf("expected status 200, got %d", w.Code)
		}

		ct := w.Header().Get("Content-Type")
		if !strings.Contains(ct, "text/html") {
			t.Errorf("expected Content-Type to contain 'text/html', got %s", ct)
		}

		body := w.Body.String()
		if !strings.Contains(body, "<title>gnmic monitor</title>") {
			t.Error("expected body to contain '<title>gnmic monitor</title>'")
		}

		if !strings.Contains(body, "/api/status") {
			t.Error("expected body to contain '/api/status'")
		}

		if !strings.Contains(body, "/topology.js") {
			t.Error("expected body to contain '/topology.js'")
		}

		if !strings.Contains(body, "drop-shadow(0 0 6px var(--ok))") {
			t.Error("expected body to contain status glow rule")
		}

		if !strings.Contains(body, "id=\"topologyView\"") {
			t.Error("expected body to contain 'id=\"topologyView\"'")
		}

		if !strings.Contains(body, "id=\"tableView\"") {
			t.Error("expected body to contain 'id=\"tableView\"'")
		}

		if !strings.Contains(body, "id=\"topologySvg\"") {
			t.Error("expected body to contain 'id=\"topologySvg\"'")
		}

		if !strings.Contains(body, "id=\"btnTopology\"") {
			t.Error("expected body to contain 'id=\"btnTopology\"'")
		}

		if !strings.Contains(body, "id=\"btnTable\"") {
			t.Error("expected body to contain 'id=\"btnTable\"'")
		}

		if !strings.Contains(body, "function showView") {
			t.Error("expected body to contain 'function showView'")
		}

		if !strings.Contains(body, "function renderTopology") {
			t.Error("expected body to contain 'function renderTopology'")
		}

		if !strings.Contains(body, "createElementNS") {
			t.Error("expected body to contain 'createElementNS'")
		}

		if !strings.Contains(body, "buildTopology(") {
			t.Error("expected body to contain 'buildTopology('")
		}

		if !strings.Contains(body, "id=\"topologyLegend\"") {
			t.Error("expected body to contain 'id=\"topologyLegend\"'")
		}

		if !strings.Contains(body, "edge-error") {
			t.Error("expected body to contain 'edge-error'")
		}

		if !strings.Contains(body, "st-no-data") {
			t.Error("expected body to contain 'st-no-data'")
		}

		if !strings.Contains(body, "id=\"topologyTooltip\"") {
			t.Error("expected body to contain 'id=\"topologyTooltip\"'")
		}

		if !strings.Contains(body, "dataset.name") {
			t.Error("expected body to contain 'dataset.name'")
		}

		if !strings.Contains(body, "scrollIntoView") {
			t.Error("expected body to contain 'scrollIntoView'")
		}

		if !strings.Contains(body, "closest(") {
			t.Error("expected body to contain 'closest('")
		}

		if !strings.Contains(body, "class=\"tooltip\"") {
			t.Error("expected body to contain 'class=\"tooltip\"'")
		}

		if !strings.Contains(body, "id=\"hostsPanel\"") {
			t.Error("expected body to contain 'id=\"hostsPanel\"'")
		}

		if !strings.Contains(body, "id=\"hostsTable\"") {
			t.Error("expected body to contain 'id=\"hostsTable\"'")
		}

		if !strings.Contains(body, "id=\"hostsSummary\"") {
			t.Error("expected body to contain 'id=\"hostsSummary\"'")
		}

		if !strings.Contains(body, "function renderHosts") {
			t.Error("expected body to contain 'function renderHosts'")
		}

		if !strings.Contains(body, "expandedHosts") {
			t.Error("expected body to contain 'expandedHosts'")
		}

		if !strings.Contains(body, "level-crit") {
			t.Error("expected body to contain 'level-crit'")
		}

		if !strings.Contains(body, "level-warn") {
			t.Error("expected body to contain 'level-warn'")
		}

		// Test that legend includes all required status classes
		if !strings.Contains(body, "st-waiting") {
			t.Error("expected body to contain 'st-waiting' for legend")
		}

		if !strings.Contains(body, "st-stale") {
			t.Error("expected body to contain 'st-stale' for legend")
		}

		if !strings.Contains(body, "st-no-data") {
			t.Error("expected body to contain 'st-no-data' for legend")
		}

		// Test that legend dot CSS rules are defined for all statuses
		if !strings.Contains(body, ".legend-dot.ok") {
			t.Error("expected body to contain '.legend-dot.ok' CSS rule")
		}

		if !strings.Contains(body, ".legend-dot.waiting") {
			t.Error("expected body to contain '.legend-dot.waiting' CSS rule")
		}

		if !strings.Contains(body, ".legend-dot.stale") {
			t.Error("expected body to contain '.legend-dot.stale' CSS rule")
		}

		if !strings.Contains(body, ".legend-dot.no-data") {
			t.Error("expected body to contain '.legend-dot.no-data' CSS rule")
		}

		if !strings.Contains(body, ".legend-dot.error") {
			t.Error("expected body to contain '.legend-dot.error' CSS rule")
		}

		// Test that SVG text elements have fill rules in CSS
		if !strings.Contains(body, ".node text {") {
			t.Error("expected body to contain '.node text {' CSS rule")
		}

		// Check for fill in node text rule
		if !strings.Contains(body, "fill: var(--text)") {
			t.Error("expected body to contain 'fill: var(--text)' in node text rule")
		}

		// Test that SVG heading text has explicit fill color set
		if !strings.Contains(body, "text.setAttribute(\"fill\"") {
			t.Error("expected body to contain setAttribute for SVG text fill")
		}

		// Test that arrowhead markers are defined with proper colors
		if !strings.Contains(body, "arrowhead-normal") {
			t.Error("expected body to contain 'arrowhead-normal' marker")
		}

		if !strings.Contains(body, "arrowhead-error") {
			t.Error("expected body to contain 'arrowhead-error' marker")
		}

		if !strings.Contains(body, "arrowhead-stale") {
			t.Error("expected body to contain 'arrowhead-stale' marker")
		}

		// Test favicon link is present
		if !strings.Contains(body, "rel=\"icon\"") {
			t.Error("expected body to contain 'rel=\"icon\"'")
		}

		if !strings.Contains(body, "image/svg+xml") {
			t.Error("expected body to contain 'image/svg+xml'")
		}

		// Test new logo has the green circle
		if !strings.Contains(body, "%2334d399") {
			t.Error("expected body to contain green color '%2334d399' in favicon")
		}

		// Test header logo has the green circle (in unencoded form in the SVG)
		if !strings.Contains(body, "fill=\"#34d399\"") {
			t.Error("expected body to contain green color 'fill=\"#34d399\"' in header logo")
		}

		// Test old netanchor logo patterns are gone
		if strings.Contains(body, "M32 16 V34") {
			t.Error("expected old netanchor logo pattern 'M32 16 V34' to be gone")
		}

		if strings.Contains(body, "M32 34 L16 48") {
			t.Error("expected old netanchor logo pattern 'M32 34 L16 48' to be gone")
		}

		if strings.Contains(body, "M32 34 L48 48") {
			t.Error("expected old netanchor logo pattern 'M32 34 L48 48' to be gone")
		}

		if strings.Contains(body, "M32 34 V52") {
			t.Error("expected old netanchor logo pattern 'M32 34 V52' to be gone")
		}
	})

	t.Run("GET /topology.js returns 200 with JavaScript", func(t *testing.T) {
		w := httptest.NewRecorder()
		r := httptest.NewRequest("GET", "/topology.js", nil)
		handler.ServeHTTP(w, r)

		if w.Code != http.StatusOK {
			t.Errorf("expected status 200, got %d", w.Code)
		}

		ct := w.Header().Get("Content-Type")
		if !strings.Contains(ct, "javascript") {
			t.Errorf("expected Content-Type to contain 'javascript', got %s", ct)
		}

		body := w.Body.String()
		if !strings.Contains(body, "buildTopology") {
			t.Error("expected body to contain 'buildTopology'")
		}
	})

	t.Run("GET /nope returns 404", func(t *testing.T) {
		w := httptest.NewRecorder()
		r := httptest.NewRequest("GET", "/nope", nil)
		handler.ServeHTTP(w, r)

		if w.Code != http.StatusNotFound {
			t.Errorf("expected status 404, got %d", w.Code)
		}
	})

	t.Run("GET /topology.jsx returns 404", func(t *testing.T) {
		w := httptest.NewRecorder()
		r := httptest.NewRequest("GET", "/topology.jsx", nil)
		handler.ServeHTTP(w, r)

		if w.Code != http.StatusNotFound {
			t.Errorf("expected status 404, got %d", w.Code)
		}
	})
}
