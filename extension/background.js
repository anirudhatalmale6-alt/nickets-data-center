// Nickets Data Reporter - Background Service Worker
// Receives queue/purchase events from content scripts and sends to Data Center API

const DEFAULT_API_URL = 'https://nickets.xyz/dashboard';
const DEFAULT_API_KEY = 'nk$d4t4#2026!';

let config = {
    api_url: DEFAULT_API_URL,
    api_key: DEFAULT_API_KEY,
    va_name: '',
    profile_id: '',
    enabled: true,
    report_queue: true,
    report_purchases: true,
};

let queueBuffer = [];
let flushTimer = null;
const FLUSH_INTERVAL = 5000;
const MAX_BUFFER = 50;

chrome.storage.local.get(['ndr_config'], function(result) {
    if (result.ndr_config) {
        Object.assign(config, result.ndr_config);
    }
});

chrome.storage.onChanged.addListener(function(changes) {
    if (changes.ndr_config) {
        Object.assign(config, changes.ndr_config.newValue || {});
    }
});

function apiPost(endpoint, data) {
    if (!config.enabled) return Promise.resolve(null);

    return fetch(config.api_url + endpoint, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-API-Key': config.api_key,
        },
        body: JSON.stringify(data),
    })
    .then(function(r) { return r.json(); })
    .catch(function(e) {
        console.log('[NDR] API error:', e.message);
        return null;
    });
}

function flushQueueBuffer() {
    if (queueBuffer.length === 0) return;

    var events = queueBuffer.splice(0, MAX_BUFFER);
    apiPost('/api/queue/bulk', { events: events }).then(function(result) {
        if (result && result.ok) {
            console.log('[NDR] Flushed ' + result.logged + ' queue events');
        } else if (events.length > 0) {
            queueBuffer.unshift.apply(queueBuffer, events);
        }
    });
}

function scheduleFlush() {
    if (flushTimer) return;
    flushTimer = setTimeout(function() {
        flushTimer = null;
        flushQueueBuffer();
    }, FLUSH_INTERVAL);
}

chrome.runtime.onMessage.addListener(function(msg, sender) {
    if (!msg || !msg.type) return;

    var tabId = sender.tab ? sender.tab.id : 0;
    var profileId = config.profile_id || ('tab-' + tabId);

    if (msg.type === 'queue_update' && config.report_queue) {
        queueBuffer.push({
            profile_id: profileId,
            profile_name: config.profile_id || '',
            va_name: config.va_name,
            queue_position: msg.data.queue_position,
            event_name: msg.data.event_name || '',
            event_url: msg.data.event_url || '',
            status: msg.data.status || '',
            source: 'extension',
        });

        if (queueBuffer.length >= MAX_BUFFER) {
            flushQueueBuffer();
        } else {
            scheduleFlush();
        }

        chrome.action.setBadgeText({ text: String(msg.data.queue_position), tabId: tabId });
        chrome.action.setBadgeBackgroundColor({
            color: msg.data.queue_position < 500 ? '#3fb950' :
                   msg.data.queue_position < 5000 ? '#d29922' : '#f85149',
            tabId: tabId
        });
    }

    if (msg.type === 'purchase' && config.report_purchases) {
        apiPost('/api/purchase/log', {
            profile_id: profileId,
            profile_name: config.profile_id || '',
            va_name: config.va_name,
            event_name: msg.data.event_name || '',
            event_url: msg.data.event_url || '',
            event_date: msg.data.event_date || '',
            venue: msg.data.venue || '',
            quantity: msg.data.quantity || 0,
            total_amount: msg.data.total_amount || 0,
            section: msg.data.section || '',
            row_info: msg.data.row_info || '',
            seat_info: msg.data.seat_info || '',
            order_id: msg.data.order_id || '',
            email: msg.data.email || '',
            source: 'extension',
        }).then(function(result) {
            if (result && result.ok) {
                console.log('[NDR] Purchase logged:', result.purchase_id);
                chrome.action.setBadgeText({ text: 'BUY', tabId: tabId });
                chrome.action.setBadgeBackgroundColor({ color: '#3fb950', tabId: tabId });
            }
        });
    }
});

chrome.alarms.create('flush_queue', { periodInMinutes: 0.1 });
chrome.alarms.onAlarm.addListener(function(alarm) {
    if (alarm.name === 'flush_queue') {
        flushQueueBuffer();
    }
});
