// Published as visualization.js. Studio loads that file from /static/@<splunk build>/..., which browsers
// cache for a year and which only changes with a Splunk upgrade, so it only loads the real bundle
// (faceplate.js) with a fresh query string.
// ponytail: no caching of faceplate.js (~9 KB per dashboard load); use a content hash once it grows.
(function () {
    var s = document.createElement('script');
    s.src = '/static/app/mdt_infra_monitoring/visualizations/port_faceplate/faceplate.js?t=' + Date.now();
    document.head.appendChild(s);
})();
