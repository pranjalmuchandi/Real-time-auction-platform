const state = {
  auctions: [],
  categories: [],
  selectedId: null,
  category: "all",
  search: "",
};

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const grid = document.querySelector("#auction-grid");
const filters = document.querySelector("#filters");
const search = document.querySelector("#search");
const liveCount = document.querySelector("#live-count");
const connection = document.querySelector("#connection");
const selectedTitle = document.querySelector("#selected-title");
const bidForm = document.querySelector("#bid-form");
const bidderName = document.querySelector("#bidder-name");
const bidAmount = document.querySelector("#bid-amount");
const formMessage = document.querySelector("#form-message");
const bidHistory = document.querySelector("#bid-history");
const minimumBid = document.querySelector("#minimum-bid");
const cardTemplate = document.querySelector("#auction-card-template");

function timeLeft(endsAt) {
  const seconds = Math.max(0, endsAt - Math.floor(Date.now() / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m left`;
}

function currentAuction() {
  return state.auctions.find((auction) => auction.id === state.selectedId);
}

function setMessage(text, success = false) {
  formMessage.textContent = text;
  formMessage.classList.toggle("success", success);
}

function renderFilters() {
  filters.innerHTML = "";
  ["all", ...state.categories].forEach((category) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `filter-button${category === state.category ? " active" : ""}`;
    button.textContent = category === "all" ? "All" : category;
    button.addEventListener("click", () => {
      state.category = category;
      loadAuctions();
    });
    filters.append(button);
  });
}

function renderAuctions() {
  grid.innerHTML = "";
  liveCount.textContent = `${state.auctions.length} live lots`;

  state.auctions.forEach((auction) => {
    const fragment = cardTemplate.content.cloneNode(true);
    const button = fragment.querySelector(".card-button");
    const image = fragment.querySelector("img");

    button.classList.toggle("selected", auction.id === state.selectedId);
    button.addEventListener("click", () => selectAuction(auction.id));
    image.src = auction.imageUrl;
    image.alt = auction.title;
    fragment.querySelector(".category").textContent = auction.category;
    fragment.querySelector(".timer").textContent = timeLeft(auction.endsAt);
    fragment.querySelector("h3").textContent = auction.title;
    fragment.querySelector("p").textContent = auction.description;
    fragment.querySelector(".price").textContent = currency.format(auction.currentPrice);
    fragment.querySelector(".bid-count").textContent = `${auction.bidCount} bids`;
    grid.append(fragment);
  });
}

async function loadAuctions() {
  const params = new URLSearchParams({ category: state.category, q: state.search });
  const response = await fetch(`/api/auctions?${params}`);
  const data = await response.json();
  state.auctions = data.auctions;
  state.categories = data.categories;

  if (!state.selectedId && state.auctions.length > 0) {
    state.selectedId = state.auctions[0].id;
  }
  if (state.selectedId && !state.auctions.some((auction) => auction.id === state.selectedId)) {
    state.selectedId = state.auctions[0]?.id ?? null;
  }

  renderFilters();
  renderAuctions();
  await renderBidDesk();
}

async function selectAuction(id) {
  state.selectedId = id;
  setMessage("");
  renderAuctions();
  await renderBidDesk();
}

async function renderBidDesk() {
  const auction = currentAuction();
  bidForm.querySelector("button").disabled = !auction;
  bidHistory.innerHTML = "";

  if (!auction) {
    selectedTitle.textContent = "Select a lot";
    bidAmount.value = "";
    minimumBid.textContent = "";
    return;
  }

  selectedTitle.textContent = auction.title;
  bidAmount.min = auction.currentPrice + 25;
  bidAmount.placeholder = `${auction.currentPrice + 25}`;
  bidAmount.value = auction.currentPrice + 25;
  minimumBid.textContent = `Min ${currency.format(auction.currentPrice + 25)}`;

  const response = await fetch(`/api/auctions/${auction.id}/bids`);
  const data = await response.json();
  data.bids.forEach((bid) => {
    const item = document.createElement("li");
    const when = new Date(bid.createdAt * 1000).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
    item.innerHTML = `
      <span><strong>${escapeHtml(bid.bidderName)}</strong><small>${when}</small></span>
      <strong>${currency.format(bid.amount)}</strong>
    `;
    bidHistory.append(item);
  });
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (match) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[match]));
}

bidForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const auction = currentAuction();
  if (!auction) return;

  setMessage("");
  const response = await fetch(`/api/auctions/${auction.id}/bids`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      bidderName: bidderName.value,
      amount: bidAmount.value,
    }),
  });
  const data = await response.json();

  if (!response.ok) {
    setMessage(data.error || "Could not place bid");
    return;
  }

  applyBidUpdate(data);
  setMessage("Bid placed successfully.", true);
});

search.addEventListener("input", () => {
  state.search = search.value.trim();
  clearTimeout(search.timer);
  search.timer = setTimeout(loadAuctions, 180);
});

function applyBidUpdate(data) {
  const index = state.auctions.findIndex((auction) => auction.id === data.auction.id);
  if (index >= 0) {
    state.auctions[index] = data.auction;
  } else if (state.category === "all" || state.category === data.auction.category) {
    state.auctions.push(data.auction);
  }
  renderAuctions();
  if (state.selectedId === data.auction.id) {
    renderBidDesk();
  }
}

function connectEvents() {
  const source = new EventSource("/api/events");

  source.addEventListener("connected", () => {
    connection.textContent = "Live";
    connection.classList.remove("offline");
  });

  source.addEventListener("bid", (event) => {
    applyBidUpdate(JSON.parse(event.data));
  });

  source.onerror = () => {
    connection.textContent = "Reconnecting";
    connection.classList.add("offline");
  };
}

setInterval(renderAuctions, 30000);
connectEvents();
loadAuctions();
