"use strict";

const STORAGE = {
  keywords: "newsAggregator:v1:savedKeywords",
  favorites: "newsAggregator:v1:favorites",
};
const state = {
  page: 1,
  limit: 30,
  total: 0,
  articles: [],
  search: { query: "", dateFrom: "", dateTo: "", source: "" },
};
const REFRESH_INTERVAL_MS = 60_000;
let refreshPromise = null;
let articleRequestGeneration = 0;

const byId = (id) => document.getElementById(id);
const readList = (key) => {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "[]");
    return Array.isArray(value) && value.every((item) => typeof item === "string") ? value : [];
  } catch (_error) {
    return [];
  }
};
const writeList = (key, values) => localStorage.setItem(key, JSON.stringify([...new Set(values)]));
const formatDate = (value) => value ? new Intl.DateTimeFormat("ja-JP", {
  dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Tokyo",
}).format(new Date(value)) : "日付不明";
const formatBytes = (bytes) => new Intl.NumberFormat("ja-JP", {
  style: "unit", unit: bytes >= 1048576 ? "megabyte" : "kilobyte", maximumFractionDigits: 1,
}).format(bytes / (bytes >= 1048576 ? 1048576 : 1024));
const element = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};
const safeArticleUrl = (value) => {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch (_error) {
    return null;
  }
};

async function requestJson(path, options) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function searchParameters() {
  const parameters = new URLSearchParams({ page: String(state.page), limit: String(state.limit) });
  for (const [name, value] of Object.entries({
    q: state.search.query,
    date_from: state.search.dateFrom,
    date_to: state.search.dateTo,
    source: state.search.source,
  })) {
    if (value) parameters.set(name, value);
  }
  return parameters;
}

function commitSearchParameters() {
  state.search = {
    query: byId("query").value,
    dateFrom: byId("date-from").value,
    dateTo: byId("date-to").value,
    source: byId("source").value,
  };
}

async function loadArticles() {
  const requestGeneration = ++articleRequestGeneration;
  byId("fetch-message").textContent = "記事を読み込み中";
  try {
    const payload = await requestJson(`/api/articles?${searchParameters()}`);
    if (requestGeneration !== articleRequestGeneration) return;
    state.articles = payload.articles;
    state.total = payload.total;
    byId("result-count").textContent = `${payload.total.toLocaleString("ja-JP")} 件`;
    byId("fetch-message").textContent = "表示日時は日本時間です";
    renderArticles();
    renderPagination();
  } catch (error) {
    if (requestGeneration !== articleRequestGeneration) return;
    byId("fetch-message").textContent = error.message;
  }
}

function renderArticles() {
  const container = byId("articles");
  const favorites = new Set(readList(STORAGE.favorites));
  const onlyFavorites = byId("favorites-only").checked;
  const articles = onlyFavorites ? state.articles.filter((article) => favorites.has(article.url)) : state.articles;
  container.replaceChildren();
  if (!articles.length) {
    container.append(element("p", "empty", onlyFavorites ? "このページにお気に入りはありません" : "記事がありません"));
    return;
  }
  for (const article of articles) container.append(articleCard(article, favorites));
}

function articleCard(article, favorites) {
  const card = element("article", "article-card");
  const kind = article.source_kind === "portal" ? "ポータル記事" : "配信元記事";
  const timeKind = article.timestamp_kind === "portal_provided" ? "ポータル提供日時" : "公開日時";
  card.append(element("div", "meta", `${article.source_name} · ${article.publisher} · ${kind}`));
  const heading = element("h3");
  const link = element("a", "", article.title);
  const href = safeArticleUrl(article.url);
  if (href) {
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  }
  heading.append(link);
  card.append(heading);
  card.append(element("div", "meta", `${timeKind}: ${formatDate(article.published_at)}`));
  if (article.summary) card.append(element("p", "summary", article.summary));
  const footer = element("div", "article-footer");
  const tags = element("div", "tag-list");
  for (const value of [article.category, ...article.tags].filter(Boolean)) tags.append(element("span", "tag", value));
  footer.append(tags);
  const favorite = element("button", `favorite-button${favorites.has(article.url) ? " active" : ""}`, favorites.has(article.url) ? "★ 保存済み" : "☆ お気に入り");
  favorite.type = "button";
  favorite.addEventListener("click", () => toggleFavorite(article.url));
  footer.append(favorite);
  card.append(footer);
  return card;
}

function toggleFavorite(url) {
  const favorites = new Set(readList(STORAGE.favorites));
  favorites.has(url) ? favorites.delete(url) : favorites.add(url);
  writeList(STORAGE.favorites, [...favorites]);
  renderArticles();
}

function renderPagination() {
  const pages = Math.max(1, Math.ceil(state.total / state.limit));
  const container = byId("pagination");
  container.replaceChildren();
  const previous = element("button", "", "前へ");
  previous.disabled = state.page <= 1;
  previous.addEventListener("click", () => { state.page -= 1; loadArticles(); });
  const next = element("button", "", "次へ");
  next.disabled = state.page >= pages;
  next.addEventListener("click", () => { state.page += 1; loadArticles(); });
  container.append(previous, element("span", "meta", `${state.page} / ${pages}`), next);
}

function renderSavedKeywords() {
  const container = byId("saved-keywords");
  container.replaceChildren();
  for (const keyword of readList(STORAGE.keywords)) {
    const button = element("button", "chip", keyword);
    button.type = "button";
    button.title = "クリックで検索。Shift+クリックで削除";
    button.addEventListener("click", (event) => {
      if (event.shiftKey) {
        writeList(STORAGE.keywords, readList(STORAGE.keywords).filter((item) => item !== keyword));
        renderSavedKeywords();
      } else {
        byId("query").value = keyword;
        commitSearchParameters();
        state.page = 1;
        loadArticles();
      }
    });
    container.append(button);
  }
}

async function loadSources() {
  const payload = await requestJson("/api/sources");
  const select = byId("source");
  const selectedSource = select.value;
  const allSources = element("option", "", "すべて");
  allSources.value = "";
  select.replaceChildren(allSources);
  for (const source of payload.sources) {
    const option = element("option", "", source.name);
    option.value = source.id;
    select.append(option);
  }
  select.value = selectedSource;
  const container = byId("source-states");
  container.replaceChildren();
  for (const source of payload.sources) {
    const card = element("article", "source-card");
    card.append(element("h3", "", source.name));
    card.append(element("span", `status ${source.status}`, statusLabel(source.status)));
    const latest = source.last_success_at ? `最終成功: ${formatDate(source.last_success_at)}` : "最終成功: なし";
    card.append(element("p", "", latest));
    if (source.last_attempt_at) card.append(element("p", "", `最終試行: ${formatDate(source.last_attempt_at)}`));
    if (source.error) card.append(element("p", "", source.error));
    card.append(element("p", "", source.terms_note));
    for (const feed of source.feeds.filter((item) => item.error || item.skipped_reason)) {
      card.append(element("p", "feed-details", `${feed.category || feed.id}: ${feed.error || feed.skipped_reason}`));
    }
    container.append(card);
  }
}

function statusLabel(status) {
  return ({ success: "正常", error: "エラー", skipped: "間隔調整", disabled: "無効", never: "未取得" })[status] || status;
}

async function loadStorage() {
  const usage = await requestJson("/api/storage");
  byId("storage-size").textContent = formatBytes(usage.total_bytes);
}

function refreshView() {
  if (refreshPromise) return refreshPromise;
  refreshPromise = Promise.all([loadArticles(), loadSources(), loadStorage()])
    .catch((error) => {
      byId("fetch-message").textContent = error.message;
    })
    .finally(() => {
      refreshPromise = null;
    });
  return refreshPromise;
}

byId("search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  commitSearchParameters();
  state.page = 1;
  loadArticles();
});
byId("save-keyword").addEventListener("click", () => {
  const keyword = byId("query").value.trim();
  if (!keyword) return;
  writeList(STORAGE.keywords, [...readList(STORAGE.keywords), keyword]);
  renderSavedKeywords();
});
byId("favorites-only").addEventListener("change", renderArticles);
byId("fetch-button").addEventListener("click", async () => {
  const button = byId("fetch-button");
  button.disabled = true;
  byId("fetch-message").textContent = "取得中（他ソースは個別に継続します）";
  try {
    const report = await requestJson("/api/fetch", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
    });
    byId("fetch-message").textContent = report.has_errors ? "一部ソースで取得エラー" : "取得が完了しました";
    await refreshView();
  } catch (error) {
    byId("fetch-message").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

renderSavedKeywords();
refreshView();
setInterval(refreshView, REFRESH_INTERVAL_MS);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") refreshView();
});
