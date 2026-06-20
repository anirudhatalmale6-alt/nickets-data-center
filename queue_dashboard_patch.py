"""
Queue Dashboard Data Reporter Patch
Add this to the existing queue_dashboard.py to send queue data to the Nickets Data API.
Import and call DataReporter.report() from the scan loop.

Usage:
    1. Copy this file next to queue_dashboard.py
    2. In QueueDashboardApp.__init__, add: self.data_reporter = DataReporter(api_url, api_key)
    3. In the scan callback where profiles are updated, add:
       self.data_reporter.report(profile_id, queue_num, event_name, event_url, va_name)
"""

import json
import threading
import time

try:
    import urllib.request
    import urllib.error
except ImportError:
    pass


class DataReporter:
    def __init__(self, api_url='http://127.0.0.1:7890', api_key='nk$d4t4#2026!', va_name=''):
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.va_name = va_name
        self.buffer = []
        self.lock = threading.Lock()
        self.flush_interval = 5
        self._start_flush_thread()

    def _start_flush_thread(self):
        def loop():
            while True:
                time.sleep(self.flush_interval)
                self.flush()
        t = threading.Thread(target=loop, daemon=True)
        t.start()

    def report(self, profile_id, queue_position, event_name='', event_url='', va_name='', profile_name=''):
        with self.lock:
            self.buffer.append({
                'profile_id': profile_id,
                'profile_name': profile_name,
                'va_name': va_name or self.va_name,
                'queue_position': queue_position,
                'event_name': event_name,
                'event_url': event_url,
                'status': 'in_queue' if queue_position > 0 else 'waiting',
                'source': 'dashboard',
            })

    def flush(self):
        with self.lock:
            if not self.buffer:
                return
            events = self.buffer[:]
            self.buffer.clear()

        try:
            data = json.dumps({'events': events}).encode('utf-8')
            req = urllib.request.Request(
                self.api_url + '/api/queue/bulk',
                data=data,
                method='POST'
            )
            req.add_header('Content-Type', 'application/json')
            req.add_header('X-API-Key', self.api_key)
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode())
                if result.get('ok'):
                    return True
        except Exception as e:
            with self.lock:
                self.buffer = events + self.buffer
            return False

    def report_purchase(self, profile_id, event_name, quantity=0, total_amount=0, **kwargs):
        try:
            payload = {
                'profile_id': profile_id,
                'va_name': kwargs.get('va_name', self.va_name),
                'event_name': event_name,
                'quantity': quantity,
                'total_amount': total_amount,
                'source': 'dashboard',
            }
            payload.update(kwargs)
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                self.api_url + '/api/purchase/log',
                data=data,
                method='POST'
            )
            req.add_header('Content-Type', 'application/json')
            req.add_header('X-API-Key', self.api_key)
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode())
        except:
            return None
