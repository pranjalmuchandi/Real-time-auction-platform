from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
from pymongo import MongoClient
import json
import mimetypes
import queue
import threading
import time
import os


ROOT = Path(__file__).parent.resolve()
STATIC_DIR = ROOT / "static"

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 10000))

# Replace with your MongoDB Atlas connection string
MONGO_URI = MONGO_URI = "mongodb+srv://pranjalmuchandi028:auction123@cluster0.q1veocr.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

client = MongoClient(MONGO_URI)
db = client["auctionDB"]

auctions_collection = db["auctions"]
bids_collection = db["bids"]

events_lock = threading.Lock()
event_clients = []


# ---------------------------
# Insert sample data once
# ---------------------------
def init_db():
    if auctions_collection.count_documents({}) == 0:
        now = int(time.time())

        sample_auctions = [
            {
                "title": "Leica M6 Camera",
                "category": "Photography",
                "description": "Vintage Leica camera",
                "imageUrl": "https://images.unsplash.com/photo-1512790182412-b19e6d62bc39",
                "startingPrice": 1800,
                "currentPrice": 2450,
                "bidCount": 8,
                "endsAt": now + 50000,
                "status": "live"
            },
            {
                "title": "Omega Watch",
                "category": "Watches",
                "description": "Luxury vintage watch",
                "imageUrl": "https://images.unsplash.com/photo-1523275335684",
                "startingPrice": 1000,
                "currentPrice": 1500,
                "bidCount": 5,
                "endsAt": now + 60000,
                "status": "live"
            }
        ]

        auctions_collection.insert_many(sample_auctions)
        print("Sample auction data inserted successfully")


# ---------------------------
# Real-time event broadcast
# ---------------------------
def broadcast(event_name, payload):
    message = f"event: {event_name}\ndata: {json.dumps(payload)}\n\n".encode("utf-8")

    with events_lock:
        clients = list(event_clients)

    for client in clients:
        client.put(message)


# ---------------------------
# HTTP Handler
# ---------------------------
class AuctionHandler(SimpleHTTPRequestHandler):

    def translate_path(self, path):
        parsed = urlparse(path)
        clean_path = parsed.path.lstrip("/") or "index.html"
        return str(STATIC_DIR / clean_path)

    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
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

        if not str(path).startswith(str(STATIC_DIR)) or not path.exists():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

        body = path.read_bytes()

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -------------------
    # Get auctions
    # -------------------
    def handle_auctions(self):
        auctions = list(auctions_collection.find())

        for auction in auctions:
            auction["id"] = str(auction["_id"])
            del auction["_id"]

        categories = auctions_collection.distinct("category")

        self.send_json({
            "auctions": auctions,
            "categories": categories,
            "serverTime": int(time.time())
        })

    # -------------------
    # Get bids
    # -------------------
    def handle_bids(self, path):
        auction_id = path.split("/")[3]

        bids = list(
            bids_collection.find({"auction_id": auction_id})
        )

        for bid in bids:
            bid["id"] = str(bid["_id"])
            del bid["_id"]

        self.send_json({"bids": bids})

    # -------------------
    # Real-time events
    # -------------------
    def handle_events(self):
        client_queue = queue.Queue()

        with events_lock:
            event_clients.append(client_queue)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        try:
            while True:
                try:
                    message = client_queue.get(timeout=20)
                except queue.Empty:
                    message = b": heartbeat\n\n"

                self.wfile.write(message)
                self.wfile.flush()

        except:
            pass

    # -------------------
    # Place bid
    # -------------------
    def place_bid(self, path):
        auction_id = path.split("/")[3]

        payload = self.read_json()

        bidder_name = payload.get("bidderName")
        amount = int(payload.get("amount"))

        auction = auctions_collection.find_one({"_id": auction_id})

        if not auction:
            self.send_json({"error": "Auction not found"}, 404)
            return

        bids_collection.insert_one({
            "auction_id": auction_id,
            "bidderName": bidder_name,
            "amount": amount,
            "createdAt": int(time.time())
        })

        auctions_collection.update_one(
            {"_id": auction_id},
            {
                "$set": {"currentPrice": amount},
                "$inc": {"bidCount": 1}
            }
        )

        updated_auction = auctions_collection.find_one({"_id": auction_id})

        updated_auction["id"] = str(updated_auction["_id"])
        del updated_auction["_id"]

        response = {
            "auction": updated_auction
        }

        broadcast("bid", response)
        self.send_json(response, 201)


# ---------------------------
# Run server
# ---------------------------
if __name__ == "__main__":
    init_db()
    print(f"Running on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), AuctionHandler).serve_forever()