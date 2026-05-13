# Hammerline Auctions

A modern full-stack real-time auction platform built for the five requested units: problem statement, frontend implementation, backend development, database integration, and deployment/output.

## Problem Statement

Traditional auction workflows often feel opaque: bidders do not immediately see price changes, sellers lack a clear activity trail, and users need a simple way to discover active lots. Hammerline Auctions solves this with a live bidding room where users can browse lots, filter by category, place validated bids, and see updates instantly.

## Frontend Implementation

- Responsive HTML, CSS, and JavaScript interface in `static/`.
- Auction cards with imagery, category filters, search, timers, bid counts, and current price.
- Bid desk with bidder name, amount validation hints, success/error states, and live bid history.
- Server-Sent Events keep the UI synchronized when bids are placed.

## Backend Development

- Python standard-library HTTP server in `app.py`.
- REST endpoints for auctions and bids.
- Real-time `/api/events` stream for bid broadcasts.
- Backend validation rejects missing bidder names, ended auctions, and bids below the minimum increment.

## Database Integration

- SQLite database stored as `auction.db` when the server starts.
- `auctions` table stores lot metadata, current price, status, and end time.
- `bids` table stores bid history with foreign-key relationships.
- Seed data is inserted automatically on first run.

## Deployment & Output

Run locally:

```bash
python app.py
```

Open:

```text
http://127.0.0.1:8000
```

For deployment, use any Python-capable host or VM. Keep `app.py`, the `static/` folder, and the generated SQLite database together. For production, place the app behind a reverse proxy such as Nginx and configure HTTPS.

## API Summary

- `GET /api/auctions?q=&category=` returns live auctions and categories.
- `GET /api/auctions/{id}/bids` returns recent bids for a lot.
- `POST /api/auctions/{id}/bids` places a bid.
- `GET /api/events` opens the real-time event stream.
