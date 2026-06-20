# Nickets Data Center

Centralized queue position tracking, purchase recording, and analytics dashboard.

## Components

### 1. Data API Server (`app.py`)
Flask server with SQLite database. Receives queue and purchase data, serves web dashboard.

**Run:**
```bash
pip install flask
python app.py
```
Server runs on port 7890 by default.

### 2. Data Reporter Extension (`extension/`)
Chrome extension that monitors Ticketmaster pages and reports queue positions + purchases to the API.

**Install:**
1. Open Chrome → `chrome://extensions`
2. Enable Developer Mode
3. Click "Load unpacked" → select the `extension` folder
4. Click the extension icon to configure API URL, Profile ID, and VA Name

### 3. Queue Dashboard Patch (`queue_dashboard_patch.py`)
Drop-in module for the existing Queue Dashboard to also report data to the API.

## API Endpoints

### Queue
- `POST /api/queue/log` - Log single queue position
- `POST /api/queue/bulk` - Log multiple queue positions
- `POST /api/queue/session/start` - Start a queue session
- `POST /api/queue/session/end` - End a queue session
- `GET /api/queue/history` - Query queue history
- `GET /api/queue/live` - Get live queue positions
- `GET /api/queue/sessions` - List queue sessions

### Purchases
- `POST /api/purchase/log` - Log a purchase
- `GET /api/purchases` - Query purchase history
- `GET /api/purchases/stats` - Purchase analytics

### Distribution
- `POST /api/distribution` - Create distribution entry
- `GET /api/distribution` - List distributions
- `PUT /api/distribution/<id>` - Update distribution

### Analytics
- `GET /api/analytics/overview` - Dashboard overview stats

## Dashboard
Visit `http://localhost:7890` for the web dashboard with:
- Live queue positions
- Queue history with filters
- Purchase records and stats
- Session tracking
