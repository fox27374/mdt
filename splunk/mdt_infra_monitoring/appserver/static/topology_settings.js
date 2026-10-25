// Network Overview, tab "Topology settings": list, add and delete mdt_device_roles entries straight in the KV store (REST),
// so no outputlookup searches (Splunk flags those as risky in dashboards).
// The tab's panel is rendered only when shown, so events are delegated and the list reloads when the tab opens.
require(["jquery", "splunkjs/mvc", "splunkjs/mvc/simplexml/ready!"], function ($, mvc) {
    var service = mvc.createService({ owner: "nobody", app: "mdt_infra_monitoring" });
    var path = "storage/collections/data/mdt_device_roles";
    var tokens = mvc.Components.get("default");
    var entries = [];

    function msg(text) { $("#roles-msg").text(text || ""); }

    function call(method, sub, body, done) {
        service.request(path + (sub ? "/" + encodeURIComponent(sub) : ""), method, null, null,
            body ? JSON.stringify(body) : null, { "Content-Type": "application/json" },
            function (err, res) {
                if (err) { msg("Error: " + ((err.data && err.data.messages && err.data.messages[0].text) || err.status)); return; }
                done(res.data);
            });
    }

    function load() {
        call("GET", null, null, function (data) {
            entries = (typeof data === "string" ? JSON.parse(data) : data) || [];
            entries.sort(function (a, b) { return a.pattern < b.pattern ? -1 : 1; });
            var tbody = $("#roles-table tbody").empty();
            entries.forEach(function (e) {
                var del = $("<a href='#' class='roles-del'>Delete</a>").data("entry", e);
                tbody.append($("<tr>").append($("<td>").text(e.pattern), $("<td>").text(e.role), $("<td>").append(del)));
            });
            if (!entries.length) tbody.append($("<tr>").append($("<td colspan='3'>").text("No entries: layout comes from the links only.")));
        });
    }

    $(document).on("click", ".roles-del", function () {
        var e = $(this).data("entry");
        call("DELETE", e._key, null, function () { msg("Deleted " + e.pattern); load(); });
        return false;
    });

    $(document).on("click", "#roles-add", function () {
        var pattern = $.trim($("#roles-pattern").val()), role = $("#roles-role").val();
        if (!/^[A-Za-z0-9*._:-]+$/.test(pattern)) { msg("Pattern: letters, digits, * . _ : - only"); return; }
        var same = entries.filter(function (e) { return e.pattern === pattern; })[0];
        call("POST", same && same._key, { pattern: pattern, role: role }, function () {
            msg((same ? "Changed " : "Added ") + pattern + " = " + role);
            $("#roles-pattern").val("");
            load();
        });
    });
    $(document).on("keydown", "#roles-pattern", function (ev) { if (ev.key === "Enter") $("#roles-add").click(); });

    tokens.on("change:tab", function () { if (tokens.get("tab") === "settings") setTimeout(load, 0); });
    load();
});
