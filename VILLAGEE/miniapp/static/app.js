const tg = window.Telegram?.WebApp;
const BOT_USERNAME = new URLSearchParams(location.search).get('bot') || '';

tg?.ready();
tg?.expand();
try { tg?.setHeaderColor('#f5f7fb'); tg?.setBackgroundColor('#f5f7fb'); } catch(e){}

const STATE = { config:null, user:null, tab:'home' };

async function api(path, opts = {}) {
  const headers = {
    'X-Bot-Username': BOT_USERNAME,
    'X-Init-Data':    tg?.initData || '',
    'Content-Type':   'application/json',
    ...(opts.headers || {})
  };
  const res = await fetch(path, { ...opts, headers });
  if (!res.ok) {
    const e = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(e.detail || 'Error');
  }
  return res.json();
}

function toast(m, ms=2200) {
  const el = document.getElementById('toast');
  el.textContent = m; el.classList.add('show');
  clearTimeout(el._t); el._t = setTimeout(() => el.classList.remove('show'), ms);
}
function showLoader(v) { document.getElementById('loader').classList.toggle('hidden', !v); }
function fmt(n) { return '₹' + Number(n || 0).toFixed(0); }
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function setCrumbs(parts) {
  const el = document.getElementById('crumbs');
  if (!parts) { el.classList.add('hidden'); return; }
  el.innerHTML = parts.map((p,i) =>
    `<span${i===parts.length-1?' class="last"':''}>${esc(p)}</span>`
  ).join('<b>›</b>');
  el.classList.remove('hidden');
}

async function loadConfig() { STATE.config = await api('/api/config'); }
async function loadMe() {
  STATE.user = await api('/api/me');
  document.getElementById('balance').textContent = fmt(STATE.user.balance);
}

// ---------------- VIEWS ----------------
async function renderHome() {
  setCrumbs(null);
  const u = STATE.user;
  const el = document.getElementById('main');
  el.innerHTML = `
    <div class="hero">
      <div class="hello">Hi, ${esc(u.first_name || 'User')} 👋</div>
      <div class="hero-bal">${fmt(u.balance)}</div>
      <div class="hero-sub">Wallet balance</div>
    </div>
    <div class="grid">
      <div class="card" data-go="store">
        <div class="card-icon">🛒</div><div class="card-title">Store</div>
        <div class="card-sub">Buy accounts & files</div></div>
      <div class="card" data-go="deposit">
        <div class="card-icon">💳</div><div class="card-title">Recharge</div>
        <div class="card-sub">Add balance</div></div>
      <div class="card" data-go="profile">
        <div class="card-icon">👤</div><div class="card-title">Profile</div>
        <div class="card-sub">Account & history</div></div>
      <div class="card" data-go="refer">
        <div class="card-icon">🎗️</div><div class="card-title">Refer</div>
        <div class="card-sub">Invite & earn</div></div>
    </div>`;
  el.querySelectorAll('[data-go]').forEach(b => b.onclick = () => switchTab(b.dataset.go));
}

async function renderStore() {
  setCrumbs(['Store']);
  const el = document.getElementById('main');
  el.innerHTML = `
    <div class="section-title">Choose Server</div>
    <div class="grid">
      <div class="card big" data-srv="s2">
        <div class="card-icon">📱</div><div class="card-title">SERVER 2</div>
        <div class="card-sub">Telegram accounts</div></div>
      <div class="card big" data-srv="s3">
        <div class="card-icon">📁</div><div class="card-title">SERVER 3</div>
        <div class="card-sub">Files, OSINT, Panels</div></div>
    </div>
    <div class="note" style="padding:14px 4px 0">
      ℹ️ Server 1 (LZT) — open the bot chat and tap BUY SERVER (1)
    </div>`;
  el.querySelectorAll('[data-srv]').forEach(b => b.onclick = () => openServer(b.dataset.srv));
}

async function openServer(srv) {
  if (srv === 's2') {
    setCrumbs(['Store','Server 2']);
    const cats = await api('/api/s2/categories');
    const el = document.getElementById('main');
    el.innerHTML = `<div class="section-title">Categories</div>
      <div class="list">${cats.map(c => `
        <div class="row" data-cat="${esc(c.name)}">
          <div class="row-icon">${esc(c.emoji)}</div>
          <div class="row-main"><div class="row-title">${esc(c.name)}</div></div>
          <div class="row-arrow">›</div>
        </div>`).join('') || '<div class="empty">No categories</div>'}</div>`;
    el.querySelectorAll('[data-cat]').forEach(r => r.onclick = () => openCategory(r.dataset.cat));
  } else if (srv === 's3') {
    setCrumbs(['Store','Server 3']);
    const secs = await api('/api/s3/sections');
    const el = document.getElementById('main');
    el.innerHTML = `<div class="section-title">Sections</div>
      <div class="list">${secs.map(s => `
        <div class="row" data-sec="${esc(s)}">
          <div class="row-icon">📦</div>
          <div class="row-main"><div class="row-title">${esc(s)}</div></div>
          <div class="row-arrow">›</div>
        </div>`).join('') || '<div class="empty">No sections</div>'}</div>`;
    el.querySelectorAll('[data-sec]').forEach(r => r.onclick = () => openSection(r.dataset.sec));
  }
}

async function openCategory(cat) {
  setCrumbs(['Store','Server 2',cat]);
  const items = await api(`/api/s2/category/${encodeURIComponent(cat)}`);
  const el = document.getElementById('main');
  el.innerHTML = `<div class="section-title">Countries</div>
    <div class="list">${items.map(i => `
      <div class="row" data-country="${esc(i.country)}">
        <div class="row-icon">${esc(i.icon)}</div>
        <div class="row-main"><div class="row-title">${esc(i.country)}</div>
          <div class="row-sub">${i.count} available</div></div>
        <div class="row-price">${fmt(i.min_price)}</div>
        <div class="row-arrow">›</div>
      </div>`).join('') || '<div class="empty">No stock</div>'}</div>`;
  el.querySelectorAll('[data-country]').forEach(r =>
    r.onclick = () => openCountry(cat, r.dataset.country));
}

async function openCountry(cat, country) {
  setCrumbs(['Store','Server 2',cat,country]);
  const items = await api(`/api/s2/${encodeURIComponent(cat)}/${encodeURIComponent(country)}`);
  const el = document.getElementById('main');
  el.innerHTML = `<div class="section-title">${esc(country)} — ${items.length} accounts</div>
    <div class="list">${items.map(i => `
      <div class="row" data-phone="${esc(i.phone)}">
        <div class="row-icon">${esc(i.icon)}</div>
        <div class="row-main"><div class="row-title">+${esc(i.phone)}</div></div>
        <div class="row-price">${fmt(i.price)}</div>
      </div>`).join('')}</div>`;
  el.querySelectorAll('[data-phone]').forEach(r =>
    r.onclick = () => openItem(r.dataset.phone));
}

async function openItem(phone) {
  setCrumbs(['Store','Item']);
  const it = await api(`/api/item/${phone}`);
  const el = document.getElementById('main');
  el.innerHTML = `
    <div class="detail">
      <div class="detail-title">${esc(it.country_icon)} ${esc(it.country_name)}</div>
      <div class="detail-price">${fmt(it.price)}</div>
      <div class="detail-rows">
        <div><span>Category</span><b>${esc(it.category)}</b></div>
        <div><span>Server</span><b>${esc(it.server)}</b></div>
        <div><span>2FA</span><b>${esc(it.twofa || 'None')}</b></div>
        ${it.description ? `<div><span>Description</span><b>${esc(it.description)}</b></div>` : ''}
      </div>
      <div class="warn">⚠️ Use Graph Manager / Plus Messenger. We are not responsible for freeze/ban.</div>
      <button class="btn btn-success" id="buyBtn">Buy Now — ${fmt(it.price)}</button>
    </div>`;
  document.getElementById('buyBtn').onclick = () => buyItem(phone);
}

async function openSection(sec) {
  setCrumbs(['Store','Server 3',sec]);
  const items = await api(`/api/s3/${encodeURIComponent(sec)}`);
  const el = document.getElementById('main');
  el.innerHTML = `<div class="section-title">${esc(sec)}</div>
    <div class="list">${items.map(i => `
      <div class="row" data-id="${i.id}">
        <div class="row-icon">📦</div>
        <div class="row-main">
          <div class="row-title">${esc(i.name)}</div>
          ${i.description ? `<div class="row-sub">${esc(i.description.slice(0,60))}</div>` : ''}
        </div>
        <div class="row-price">${fmt(i.price)}</div>
      </div>`).join('')}</div>`;
  el.querySelectorAll('[data-id]').forEach(r => r.onclick = () => {
    toast('Open the bot chat to buy this item');
  });
}

async function buyItem(phone) {
  showLoader(true);
  try {
    const r = await api('/api/purchase', {
      method: 'POST', body: JSON.stringify({ phone })
    });
    showLoader(false);
    toast(`✅ Order ${r.order_id} placed!`);
    if (tg?.showAlert) tg.showAlert(`Order placed!\n\nOpen bot chat to receive the OTP.`);
    await loadMe();
    switchTab('home');
  } catch (e) {
    showLoader(false); toast('❌ ' + e.message);
  }
}

async function renderDeposit() {
  setCrumbs(null);
  const c = STATE.config;
  const el = document.getElementById('main');
  el.innerHTML = `
    <div class="section-title">Add Balance</div>
    <div class="deposit-box">
      <label>Amount (₹)</label>
      <input type="number" id="depAmt" min="${c.min_deposit}" placeholder="Min ${c.min_deposit}">
      <div class="quick">
        ${[50,100,200,500,1000].map(v => `<button data-v="${v}">₹${v}</button>`).join('')}
      </div>
    </div>
    <div class="section-title">Method</div>
    <div class="grid">
      <div class="card" data-m="auto">
        <div class="card-icon">⚡</div><div class="card-title">UPI Auto</div>
        <div class="card-sub">Instant credit</div></div>
      <div class="card" data-m="manual">
        <div class="card-icon">📄</div><div class="card-title">UPI Manual</div>
        <div class="card-sub">Admin approve</div></div>
    </div>
    <div id="depResult"></div>`;
  const amt = el.querySelector('#depAmt');
  el.querySelectorAll('.quick button').forEach(b => b.onclick = () => amt.value = b.dataset.v);
  el.querySelectorAll('[data-m]').forEach(b =>
    b.onclick = () => makeDeposit(b.dataset.m, +amt.value));
}

async function makeDeposit(method, amount) {
  if (!amount || amount < STATE.config.min_deposit) {
    toast(`Min ₹${STATE.config.min_deposit}`); return;
  }
  showLoader(true);
  try {
    const r = await api(`/api/deposit/${method}`, {
      method:'POST', body: JSON.stringify({ amount })
    });
    showLoader(false);
    const qr = `https://api.qrserver.com/v1/create-qr-code/?size=260x260&data=${encodeURIComponent(r.upi_url)}`;
    document.getElementById('depResult').innerHTML = `
      <div class="pay-card">
        <div class="pay-title">Pay ${fmt(r.amount)}</div>
        <img src="${qr}" alt="QR" class="qr"/>
        <div class="upi-id">UPI: <b>${esc(r.upi_id)}</b></div>
        <a class="btn" href="${esc(r.upi_url)}">Open UPI App</a>
        <div class="note">${method==='auto' ? 'Waiting for payment…' : esc(r.instructions)}</div>
        <div class="note">Order: <code>${esc(r.order_id)}</code></div>
      </div>`;
    if (method === 'auto') pollOrder(r.order_id);
  } catch (e) { showLoader(false); toast('❌ ' + e.message); }
}

function pollOrder(oid) {
  let n = 0;
  const t = setInterval(async () => {
    n++;
    if (n > 60) { clearInterval(t); return; }
    try {
      const r = await api(`/api/order/${oid}`);
      if (r.status === 'success') {
        clearInterval(t); toast('✅ Payment credited!');
        await loadMe(); switchTab('home');
      } else if (['expired','failed','mismatch','duplicate'].includes(r.status)) {
        clearInterval(t); toast('❌ ' + r.status);
      }
    } catch(e){}
  }, 5000);
}

async function renderProfile() {
  setCrumbs(null);
  const u = STATE.user;
  const el = document.getElementById('main');
  el.innerHTML = `
    <div class="section-title">Profile</div>
    <div class="profile">
      <div class="p-name">${esc(u.first_name || 'User')} ${esc(u.last_name || '')}</div>
      <div class="p-id">ID: ${esc(u.user_id)} ${u.username ? '@' + esc(u.username) : ''}</div>
    </div>
    <div class="stats">
      <div class="stat"><div class="s-val">${fmt(u.balance)}</div><div class="s-lbl">Balance</div></div>
      <div class="stat"><div class="s-val">${fmt(u.total_deposited)}</div><div class="s-lbl">Deposited</div></div>
      <div class="stat"><div class="s-val">${u.total_purchases || 0}</div><div class="s-lbl">Purchases</div></div>
      <div class="stat"><div class="s-val">${u.referral_count || 0}</div><div class="s-lbl">Referrals</div></div>
    </div>
    <div class="section-title">Recent Purchases</div>
    <div id="hist" class="list"><div class="empty">Loading…</div></div>`;
  try {
    const rows = await api('/api/history');
    document.getElementById('hist').innerHTML = rows.map(r => `
      <div class="row">
        <div class="row-icon">📱</div>
        <div class="row-main">
          <div class="row-title">${esc(r.phone || '—')}</div>
          <div class="row-sub">${esc(r.country || '')} • ${esc((r.date||'').slice(0,16))}</div>
        </div>
        <div class="row-price">${fmt(r.price)}</div>
      </div>`).join('') || '<div class="empty">No purchases yet</div>';
  } catch(e){}
}

async function renderRefer() {
  setCrumbs(null);
  const r = await api('/api/refer');
  const el = document.getElementById('main');
  el.innerHTML = `
    <div class="section-title">Refer & Earn</div>
    <div class="refer-box">
      <div class="refer-link">${esc(r.link)}</div>
      <button class="btn btn-primary" id="copyLink">Copy Link</button>
      <a class="btn btn-success"
         href="https://t.me/share/url?url=${encodeURIComponent(r.link)}&text=Join+VILLAGEE+SMS+SHOP"
         target="_blank">Share</a>
    </div>`;
  document.getElementById('copyLink').onclick = () => {
    navigator.clipboard.writeText(r.link); toast('Copied!');
  };
}

// ---------------- TABS ----------------
function switchTab(tab) {
  STATE.tab = tab;
  document.querySelectorAll('#tabs button').forEach(b =>
    b.classList.toggle('active', b.dataset.tab === tab));
  const routes = { home: renderHome, store: renderStore,
                   deposit: renderDeposit, profile: renderProfile, refer: renderRefer };
  (routes[tab] || renderHome)();
}
document.querySelectorAll('#tabs button').forEach(b =>
  b.onclick = () => switchTab(b.dataset.tab));

// ---------------- INIT ----------------
(async function init() {
  if (!BOT_USERNAME) {
    document.getElementById('main').innerHTML =
      '<div class="empty">Missing bot param. Open from Telegram.</div>';
    return;
  }
  if (!tg?.initData) {
    document.getElementById('main').innerHTML =
      '<div class="empty">Please open this Mini App from Telegram.</div>';
    return;
  }
  showLoader(true);
  try {
    await loadConfig();
    await loadMe();
    showLoader(false);
    switchTab('home');
  } catch (e) {
    showLoader(false);
    document.getElementById('main').innerHTML = `<div class="empty">Error: ${esc(e.message)}</div>`;
  }
})();
