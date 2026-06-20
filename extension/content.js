// Nickets Data Reporter - Content Script
// Monitors Ticketmaster pages for queue positions and purchase confirmations
// Reports data back to the background service worker

(function() {
    'use strict';

    let lastQueuePos = null;
    let lastReportTime = 0;
    const REPORT_INTERVAL = 4000;
    let purchaseReported = false;

    function parseQueueNumber(str) {
        var n = parseInt(String(str || '').replace(/,/g, ''), 10);
        return (n > 0 && n < 100000000) ? n : null;
    }

    function detectQueuePosition() {
        var selectors = [
            '#MainPart_lbQueueNumber', '#lbQueueNumber', '[id*="lbQueueNumber"]',
            '#MainPart_h2HeaderSubText', '#h2-main', '.queue-position',
            '[class*="queue-position"]', '[class*="queuePosition"]',
            '[id*="queue-position"]', '[id*="queuePosition"]',
            '[class*="queueNumber"]', '[id*="queueNumber"]',
            '[class*="waiting-number"]', '[id*="waiting-number"]',
            '[class*="place-in-line"]', '[class*="placeInLine"]',
            '[class*="spot-number"]', '[data-queue-number]',
            '.number-display', '#queue-number'
        ];

        var patterns = [
            /you\s+are\s+(?:now\s+)?in\s+the\s+queue\s*#?\s*([\d,]{1,8})/i,
            /\bin\s+the\s+queue\s*#\s*([\d,]{1,8})/i,
            /([\d,]{1,8})\s+people\s+ahead\s+of\s+you/i,
            /([\d,]{1,8})\s+people?\s+ahead/i,
            /([\d,]{1,8})\s+waiting\s+ahead/i,
            /you\s+are\s+(?:now\s+)?(?:number\s+|#\s*)?([\d,]{1,8})\s+in/i,
            /(?:your\s+)?(?:queue\s+)?position\s+(?:is\s+)?(?:number\s+|#\s*)?([\d,]{1,8})/i,
            /you(?:'re| are)(?: currently)?\s+(?:number|#|position)\s*([\d,]{1,8})/i,
            /\bplace\s+#?([\d,]{1,8})/i,
            /#([\d,]{1,8})\s+in\s+(?:line|queue)/i,
            /there\s+are\s+([\d,]{1,8})\s+people/i
        ];

        for (var s = 0; s < selectors.length; s++) {
            try {
                var el = document.querySelector(selectors[s]);
                if (!el) continue;
                var cleaned = String(el.textContent || '').replace(/,/g, '').match(/\d+/);
                if (cleaned) {
                    var n = parseQueueNumber(cleaned[0]);
                    if (n !== null) return n;
                }
            } catch(e) {}
        }

        var text = document.body ? document.body.innerText : '';
        for (var i = 0; i < patterns.length; i++) {
            var m = text.match(patterns[i]);
            if (m) {
                var n2 = parseQueueNumber(m[1]);
                if (n2 !== null) return n2;
            }
        }

        return null;
    }

    function getEventInfo() {
        var title = document.title || '';
        title = title.replace(/\s*[|\-–—]\s*ticketmaster.*$/i, '')
                     .replace(/\s*[|\-–—]\s*livenation.*$/i, '')
                     .replace(/\s*[|\-–—]\s*queue.*$/i, '')
                     .trim();
        if (!title || /^\d[\d,\s]*$/.test(title)) {
            var parts = location.pathname.split('/').filter(Boolean);
            var skip = ['event','queue','events','signup','tickets','checkout','waitingroom','thewaitingroom'];
            for (var i = parts.length - 1; i >= 0; i--) {
                if (skip.indexOf(parts[i].toLowerCase()) === -1 && !/^[0-9a-f]{8,}$/i.test(parts[i]) && !/^\d+$/.test(parts[i])) {
                    title = parts[i].replace(/-/g, ' ').replace(/_/g, ' ');
                    break;
                }
            }
        }
        return { name: title.substring(0, 100), url: location.href };
    }

    function detectPurchaseConfirmation() {
        var url = location.href.toLowerCase();
        var isConfirmPage = /confirm|receipt|order-confirm|success|thank/i.test(url);
        var bodyText = (document.body ? document.body.innerText : '').substring(0, 5000);
        var hasConfirmText = /order\s*confirm|purchase\s*confirm|thank\s*you\s*for\s*your\s*order|your\s*tickets?\s*(?:are|have\s*been)/i.test(bodyText);

        if (!isConfirmPage && !hasConfirmText) return null;

        var orderMatch = bodyText.match(/order\s*(?:#|number|id)[:\s]*([A-Z0-9\-]{5,20})/i);
        var qtyMatch = bodyText.match(/(\d+)\s*(?:ticket|seat)/i);
        var totalMatch = bodyText.match(/(?:total|amount|charged)[:\s]*\$?([\d,]+\.?\d*)/i);
        var venueMatch = bodyText.match(/(?:venue|at|location)[:\s]+([^\n]{3,60})/i);
        var dateMatch = bodyText.match(/(?:date|when|on)[:\s]+([^\n]{5,40})/i);
        var sectionMatch = bodyText.match(/(?:section|sec)[:\s]+([^\n]{1,30})/i);
        var rowMatch = bodyText.match(/(?:row)[:\s]+([^\n]{1,20})/i);
        var seatMatch = bodyText.match(/(?:seat|seats?)[:\s]+([^\n]{1,40})/i);

        return {
            order_id: orderMatch ? orderMatch[1].trim() : '',
            quantity: qtyMatch ? parseInt(qtyMatch[1]) : 0,
            total_amount: totalMatch ? parseFloat(totalMatch[1].replace(/,/g, '')) : 0,
            venue: venueMatch ? venueMatch[1].trim() : '',
            event_date: dateMatch ? dateMatch[1].trim() : '',
            section: sectionMatch ? sectionMatch[1].trim() : '',
            row_info: rowMatch ? rowMatch[1].trim() : '',
            seat_info: seatMatch ? seatMatch[1].trim() : '',
        };
    }

    function reportQueue(position) {
        var now = Date.now();
        if (now - lastReportTime < REPORT_INTERVAL) return;
        lastReportTime = now;

        var info = getEventInfo();
        chrome.runtime.sendMessage({
            type: 'queue_update',
            data: {
                queue_position: position,
                event_name: info.name,
                event_url: info.url,
                status: position === 0 ? 'waiting' : 'in_queue'
            }
        });
    }

    function reportPurchase(purchaseData) {
        if (purchaseReported) return;
        purchaseReported = true;

        var info = getEventInfo();
        chrome.runtime.sendMessage({
            type: 'purchase',
            data: Object.assign({}, purchaseData, {
                event_name: info.name || purchaseData.event_name || '',
                event_url: info.url,
            })
        });
    }

    function scan() {
        var pos = detectQueuePosition();
        if (pos !== null) {
            if (pos !== lastQueuePos || Date.now() - lastReportTime > 10000) {
                lastQueuePos = pos;
                reportQueue(pos);
            }
        }

        if (!purchaseReported) {
            var purchase = detectPurchaseConfirmation();
            if (purchase) {
                reportPurchase(purchase);
            }
        }
    }

    if (/ticketmaster|livenation|queue-it/i.test(location.hostname)) {
        scan();
        setInterval(scan, REPORT_INTERVAL);

        var observer = new MutationObserver(function() {
            clearTimeout(window._ndrDebounce);
            window._ndrDebounce = setTimeout(scan, 500);
        });
        observer.observe(document.body || document.documentElement, {
            childList: true, subtree: true, characterData: true
        });
    }
})();
