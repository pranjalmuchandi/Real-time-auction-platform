from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import json
import mimetypes
import queue
import sqlite3
import threading
import time


ROOT = Path(__file__).parent.resolve()
STATIC_DIR = ROOT / "static"
DB_PATH = ROOT / "auction.db"
HOST = "127.0.0.1"
PORT = 8000

events_lock = threading.Lock()
event_clients = []


def get_db():
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    with get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS auctions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                image_url TEXT NOT NULL,
                starting_price INTEGER NOT NULL,
                current_price INTEGER NOT NULL,
                bid_count INTEGER NOT NULL DEFAULT 0,
                ends_at INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'live'
            );

            CREATE TABLE IF NOT EXISTS bids (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                auction_id INTEGER NOT NULL,
                bidder_name TEXT NOT NULL,
                amount INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (auction_id) REFERENCES auctions(id) ON DELETE CASCADE
            );
            """
        )

        count = db.execute("SELECT COUNT(*) AS total FROM auctions").fetchone()["total"]
        if count == 0:
            now = int(time.time())
            seed = [
                (
                    "Leica M6 Classic Film Kit",
                    "Photography",
                    "A serviced rangefinder body with 50mm Summicron lens, leather case, and fresh light seals.",
                    "https://images.unsplash.com/photo-1512790182412-b19e6d62bc39?auto=format&fit=crop&w=1200&q=80",
                    1800,
                    2450,
                    8,
                    now + 5400,
                    "live",
                ),
                (
                    "Walnut Eames Lounge Chair",
                    "Design",
                    "Mid-century lounge chair in warm walnut veneer with black leather cushions and matching ottoman.",
                    "https://images.unsplash.com/photo-1567538096630-e0c55bd6374c?auto=format&fit=crop&w=1200&q=80",
                    1200,
                    1725,
                    11,
                    now + 9200,
                    "live",
                ),
                (
                    "1960s Omega Seamaster",
                    "Watches",
                    "Automatic stainless steel watch with silver dial, original crown, and recent movement service.",
                    "https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=1200&q=80",
                    900,
                    1380,
                    6,
                    now + 12500,
                    "live",
                ),
            ]
            db.executemany(
                """
                INSERT INTO auctions
                (title, category, description, image_url, starting_price, current_price, bid_count, ends_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                seed,
            )
            db.executemany(
                """
                INSERT INTO bids (auction_id, bidder_name, amount, created_at)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (1, "Anika", 2050, now - 1900),
                    (1, "Mason", 2250, now - 800),
                    (1, "Priya", 2450, now - 300),
                    (2, "Dev", 1500, now - 2300),
                    (2, "Noah", 1675, now - 700),
                    (2, "Ira", 1725, now - 250),
                    (3, "Lena", 1120, now - 1600),
                    (3, "Kabir", 1380, now - 450),
                ],
            )


def row_to_auction(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "category": row["category"],
        "description": row["description"],
        "imageUrl": row["image_url"],
        "startingPrice": row["starting_price"],
        "currentPrice": row["current_price"],
        "bidCount": row["bid_count"],
        "endsAt": row["ends_at"],
        "status": row["status"],
    }


def row_to_bid(row):
    return {
        "id": row["id"],
        "auctionId": row["auction_id"],
        "bidderName": row["bidder_name"],
        "amount": row["amount"],
        "createdAt": row["created_at"],
    }


def broadcast(event_name, payload):
    message = f"event: {event_name}\ndata: {json.dumps(payload)}\n\n".encode("utf-8")
    with events_lock:
        clients = list(event_clients)
    for client in clients:
        client.put(message)


class AuctionHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        parsed = urlparse(path)
        clean_path = parsed.path.lstrip("/") or "index.html"
        return str(STATIC_DIR / clean_path)

    def log_message(self, format, *args):
        print("[%s] %s" % (self.log_date_time_string(), format % args))

    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/auctions":
            self.handle_auctions()
            return
        if parsed.path.startswith("/api/auctions/") and parsed.path.endswith("/bids"):
            self.handle_bids(parsed.path)
            return
        if parsed.path == "/api/events":
            self.handle_events()
            return
        if parsed.path == "/":
            self.path = "/index.html"
        self.serve_static()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/auctions/") and parsed.path.endswith("/bids"):
            self.place_bid(parsed.path)
            return
        self.send_json({"error": "Endpoint not found"}, 404)

    def serve_static(self):
        path = Path(self.translate_path(self.path)).resolve()
        if not str(path).startswith(str(STATIC_DIR)) or not path.exists() or path.is_dir():
            self.send_error(404, "File not found")
            return

        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_auctions(self):
        filters = parse_qs(urlparse(self.path).query)
        search = filters.get("q", [""])[0].strip().lower()
        category = filters.get("category", ["all"])[0]
        params = []
        clauses = ["status = 'live'"]

        if search:
            clauses.append("(LOWER(title) LIKE ? OR LOWER(description) LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        if category != "all":
            clauses.append("category = ?")
            params.append(category)

        sql = f"SELECT * FROM auctions WHERE {' AND '.join(clauses)} ORDER BY ends_at ASC"
        with get_db() as db:
            auctions = [row_to_auction(row) for row in db.execute(sql, params).fetchall()]
            categories = [
                row["category"]
                for row in db.execute("SELECT DISTINCT category FROM auctions ORDER BY category").fetchall()
            ]
        self.send_json({"auctions": auctions, "categories": categories, "serverTime": int(time.time())})

    def handle_bids(self, path):
        auction_id = int(path.split("/")[3])
        with get_db() as db:
            rows = db.execute(
                """
                SELECT * FROM bids
                WHERE auction_id = ?
                ORDER BY amount DESC, created_at DESC
                LIMIT 12
                """,
                (auction_id,),
            ).fetchall()
        self.send_json({"bids": [row_to_bid(row) for row in rows]})

    def handle_events(self):
        client_queue = queue.Queue()
        with events_lock:
            event_clients.append(client_queue)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            self.wfile.write(b"event: connected\ndata: {\"ok\": true}\n\n")
            self.wfile.flush()
            while True:
                try:
                    message = client_queue.get(timeout=20)
                except queue.Empty:
                    message = b": heartbeat\n\n"
                self.wfile.write(message)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with events_lock:
                if client_queue in event_clients:
                    event_clients.remove(client_queue)

    def place_bid(self, path):
        auction_id = int(path.split("/")[3])
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.send_json({"error": "Invalid JSON body"}, 400)
            return

        bidder_name = str(payload.get("bidderName", "")).strip()[:40]
        try:
            amount = int(payload.get("amount", 0))
        except (TypeError, ValueError):
            amount = 0

        if not bidder_name:
            self.send_json({"error": "Bidder name is required"}, 400)
            return

        with get_db() as db:
            auction = db.execute("SELECT * FROM auctions WHERE id = ?", (auction_id,)).fetchone()
            if auction is None:
                self.send_json({"error": "Auction not found"}, 404)
                return
            if auction["ends_at"] <= int(time.time()):
                self.send_json({"error": "Auction has ended"}, 409)
                return
            minimum = auction["current_price"] + 25
            if amount < minimum:
                self.send_json({"error": f"Bid must be at least ${minimum:,}"}, 400)
                return

            now = int(time.time())
            cursor = db.execute(
                """
                INSERT INTO bids (auction_id, bidder_name, amount, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (auction_id, bidder_name, amount, now),
            )
            db.execute(
                """
                UPDATE auctions
                SET current_price = ?, bid_count = bid_count + 1
                WHERE id = ?
                """,
                (amount, auction_id),
            )
            updated = db.execute("SELECT * FROM auctions WHERE id = ?", (auction_id,)).fetchone()
            bid = db.execute("SELECT * FROM bids WHERE id = ?", (cursor.lastrowid,)).fetchone()

        response = {"auction": row_to_auction(updated), "bid": row_to_bid(bid)}
        broadcast("bid", response)
        self.send_json(response, 201)


if __name__ == "__main__":
    init_db()
    print(f"Real-time auction platform running at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), AuctionHandler).serve_forever()
