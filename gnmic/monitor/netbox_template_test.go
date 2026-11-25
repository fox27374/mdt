package main

import (
	"bytes"
	"encoding/json"
	"os"
	"strings"
	"testing"
	"text/template"
)

// renderNetBoxTemplate renders the gnmic loader template on a NetBox device list, with the gnmic template
// functions the template uses (split, toJSON) stubbed the way gnmic has them.
func renderNetBoxTemplate(t *testing.T, fixture string) string {
	t.Helper()
	data, err := os.ReadFile(fixture)
	if err != nil {
		t.Fatalf("failed to read fixture: %v", err)
	}
	var input interface{}
	if err := json.Unmarshal(data, &input); err != nil {
		t.Fatalf("fixture is not JSON: %v", err)
	}
	tmpl, err := template.New("netbox-targets.tmpl").Funcs(template.FuncMap{
		"split":  strings.Split,
		"toJSON": func(v interface{}) (string, error) { b, err := json.Marshal(v); return string(b), err },
	}).ParseFiles("../config/netbox-targets.tmpl")
	if err != nil {
		t.Fatalf("parse template: %v", err)
	}
	var out bytes.Buffer
	if err := tmpl.Execute(&out, input); err != nil {
		t.Fatalf("execute template: %v", err)
	}
	return out.String()
}

func TestNetBoxTemplateTargets(t *testing.T) {
	out := renderNetBoxTemplate(t, "testdata/netbox_devices.json")

	var targets map[string]map[string]interface{}
	if err := json.Unmarshal([]byte(out), &targets); err != nil {
		t.Fatalf("output is not valid JSON: %v\n%s", err, out)
	}

	// Skipped: ibk-lab-spare01 (no primary_ip4), ibk-lab-noprofile01 (no mdt_profile).
	if len(targets) != 7 {
		t.Fatalf("expected 7 targets, got %d: %v", len(targets), targets)
	}
	for _, skipped := range []string{"ibk-lab-spare01", "ibk-lab-noprofile01"} {
		if _, ok := targets[skipped]; ok {
			t.Errorf("%s must be skipped", skipped)
		}
	}

	// Address, site (nts-innsbruck-lab -> ibk-lab), mgmt_ip and subscription count per profile.
	cases := []struct {
		name, address, site, mgmtIP string
		subs                        int
	}{
		{"ibk-lab-sw98", "172.24.80.240:57400", "ibk-lab", "172.24.80.240", 10},
		{"ibk-lab-border01", "172.24.80.231:57400", "ibk-lab", "172.24.80.231", 9},
		{"ibk-lab-edge01", "10.20.0.40:57400", "ibk-lab", "10.20.0.40", 10},
		{"ntsnxsw01", "172.24.80.195:57400", "ibk-lab", "172.24.80.195", 10},
		{"ibk-lab-ewlc01", "172.24.89.147:57400", "ibk-lab", "172.24.89.147", 7},
		{"Lab-IBK-PA560-1", "172.24.88.156:9339", "ibk-lab", "172.24.88.156", 9},
		{"nk-home-ewlc01", "172.24.88.161:57400", "nk-home", "172.24.88.161", 7},
	}
	for _, c := range cases {
		tgt, ok := targets[c.name]
		if !ok {
			t.Errorf("%s missing", c.name)
			continue
		}
		if tgt["name"] != c.name {
			t.Errorf("%s: name %v", c.name, tgt["name"])
		}
		if tgt["address"] != c.address {
			t.Errorf("%s: address %v, want %s", c.name, tgt["address"], c.address)
		}
		tags := tgt["event-tags"].(map[string]interface{})
		if tags["site"] != c.site || tags["mgmt_ip"] != c.mgmtIP {
			t.Errorf("%s: event-tags %v", c.name, tags)
		}
		if subs := tgt["subscriptions"].([]interface{}); len(subs) != c.subs {
			t.Errorf("%s: %d subscriptions, want %d", c.name, len(subs), c.subs)
		}
	}

	// Per-profile extra fields.
	pa := targets["Lab-IBK-PA560-1"]
	if pa["username"] != "${FW_USERNAME}" || pa["password"] != "${FW_PASSWORD}" {
		t.Errorf("panos credentials: %v / %v", pa["username"], pa["password"])
	}
	nx := targets["ntsnxsw01"]
	if nx["tls-ca"] != "/app/config/ca.pem" || nx["skip-verify"] != false {
		t.Errorf("nxos tls fields: %v / %v", nx["tls-ca"], nx["skip-verify"])
	}
	if _, ok := targets["ibk-lab-sw98"]["tls-ca"]; ok {
		t.Errorf("iosxe target must not carry tls-ca")
	}
}

func TestNetBoxTemplateNoTargetsIsInvalidJSON(t *testing.T) {
	out := renderNetBoxTemplate(t, "testdata/netbox_devices_empty.json")
	if strings.TrimSpace(out) != "netbox returned no monitoring targets" {
		t.Fatalf("expected the deliberate invalid output, got %q", out)
	}
	var v interface{}
	if err := json.Unmarshal([]byte(out), &v); err == nil {
		t.Fatalf("empty NetBox answer must not render as valid JSON")
	}
}
