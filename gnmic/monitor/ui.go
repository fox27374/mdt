package main

import (
	"bytes"
	_ "embed"
	"net/http"
	"strings"
)

//go:embed VERSION
var versionFile string

// version is the release number from the VERSION file.
var version = strings.TrimSpace(versionFile)

//go:embed index.html
var indexTemplate []byte

// indexHTML is index.html with the version filled in.
var indexHTML = bytes.ReplaceAll(indexTemplate, []byte("__VERSION__"), []byte(version))

//go:embed topology.js
var topologyJS []byte

// uiHandler serves index.html at exactly "/" (other paths under it return 404).
func uiHandler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/":
			w.Header().Set("Content-Type", "text/html; charset=utf-8")
			w.Write(indexHTML)
		case "/topology.js":
			w.Header().Set("Content-Type", "text/javascript; charset=utf-8")
			w.Write(topologyJS)
		default:
			http.NotFound(w, r)
		}
	})
}
