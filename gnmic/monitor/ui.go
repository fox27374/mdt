package main

import (
	_ "embed"
	"net/http"
)

//go:embed index.html
var indexHTML []byte

// uiHandler serves index.html at exactly "/" (other paths under it return 404).
func uiHandler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Write(indexHTML)
	})
}
