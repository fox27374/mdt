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
	})

	t.Run("GET /nope returns 404", func(t *testing.T) {
		w := httptest.NewRecorder()
		r := httptest.NewRequest("GET", "/nope", nil)
		handler.ServeHTTP(w, r)

		if w.Code != http.StatusNotFound {
			t.Errorf("expected status 404, got %d", w.Code)
		}
	})
}
