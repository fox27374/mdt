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
