// Nickets Data Reporter - Popup UI

var defaults = {
    api_url: 'http://127.0.0.1:7890',
    api_key: 'nk$d4t4#2026!',
    va_name: '',
    profile_id: '',
    enabled: true,
    report_queue: true,
    report_purchases: true,
};

function loadConfig() {
    chrome.storage.local.get(['ndr_config', 'ndr_stats'], function(result) {
        var cfg = Object.assign({}, defaults, result.ndr_config || {});
        document.getElementById('api-url').value = cfg.api_url;
        document.getElementById('api-key').value = cfg.api_key;
        document.getElementById('profile-id').value = cfg.profile_id;
        document.getElementById('va-name').value = cfg.va_name;
        document.getElementById('toggle-enabled').checked = cfg.enabled;
        document.getElementById('toggle-queue').checked = cfg.report_queue;
        document.getElementById('toggle-purchases').checked = cfg.report_purchases;

        var stats = result.ndr_stats || {};
        document.getElementById('stat-queue').textContent = stats.queue_count || 0;
        document.getElementById('stat-purchase').textContent = stats.purchase_count || 0;
    });
}

document.getElementById('btn-save').addEventListener('click', function() {
    var cfg = {
        api_url: document.getElementById('api-url').value.trim().replace(/\/+$/, ''),
        api_key: document.getElementById('api-key').value.trim(),
        profile_id: document.getElementById('profile-id').value.trim(),
        va_name: document.getElementById('va-name').value.trim(),
        enabled: document.getElementById('toggle-enabled').checked,
        report_queue: document.getElementById('toggle-queue').checked,
        report_purchases: document.getElementById('toggle-purchases').checked,
    };

    chrome.storage.local.set({ ndr_config: cfg }, function() {
        var statusEl = document.getElementById('status');

        fetch(cfg.api_url + '/api/status', {
            headers: { 'X-API-Key': cfg.api_key }
        })
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.status === 'ok') {
                statusEl.textContent = 'Connected to ' + d.app + ' v' + d.version;
                statusEl.className = 'status';
            } else {
                statusEl.textContent = 'API responded but status not ok';
                statusEl.className = 'status err';
            }
        })
        .catch(function(e) {
            statusEl.textContent = 'Saved. Cannot reach API: ' + e.message;
            statusEl.className = 'status err';
        });
    });
});

document.getElementById('btn-dash').addEventListener('click', function() {
    var url = document.getElementById('api-url').value.trim().replace(/\/+$/, '');
    chrome.tabs.create({ url: url || 'http://127.0.0.1:7890' });
});

loadConfig();
