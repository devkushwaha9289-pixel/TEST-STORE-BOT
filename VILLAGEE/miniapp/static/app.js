const tg = window.Telegram?.WebApp;
const BOT_USERNAME = new URLSearchParams(location.search).get('bot') || '';

tg?.ready();
tg?.expand();
try {
  tg?.setHeaderColor('#f6f8fc');
  tg?.setBackgroundColor('#f6f8fc');
} catch(e){}

const STATE = { config:null, user:null, tab:'home' };

async function api(path, opts = {}) {
  const headers = {
    'X-Bot-Username': BOT_USERNAME,
    'X-Init-Data': tg?.initData || '',
    'Content-Type': 'application/json',
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
  el.textContent = m;
  el.classList.add('show');
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove('show'), ms);
}
function showLoader(v) {
  document.getElementById('loader').classList.toggle('hidden', !v);
}
function fmt(n) { return '₹' + Number(n || 0).toFixed(0); }
function esc(s) {
  return String(s ?? '').replace(/[&<>\"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
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

/* ---------------- HOME ---------------- */
async function renderHome() {
  setCrumbs(null);
  const u = STATE.user;
  const el = document.getElementById('main');

  el.innerHTML = `
    <div class="hero">
      <div class="hello">Welcome back, ${esc(u.first_name || 'User')} 👋</div>
      <div class="hero-bal">${fmt(u.balance)}</div>
      <div class="hero-sub">Available wallet balance</div>
    </div>

    <div class="section-title">Quick Access</div>
    <div class="grid">
      <div class="card" data-go="store">
        <div class="card-icon">🛍</div>
        <div class="card-title">Store</div>
        <div class="card-sub">Accounts & digital items</div>
      </div>
      <div class="card" data-go="deposit">
        <div class="card-icon">＋</div>
        <div class="card-title">Recharge</div>
        <div class="card-sub">Add money to wallet</div>
      </div>
      <div class="card" data-go="profile">
        <div class="card-icon">◉</div>
        <div class="card-title">Profile</div>
        <div class="card-sub">Account & purchases</div>
      </div>
      <div class="card" data-go="refer">
        <div class="card-icon">↗</div>
        <div class="card-title">Refer</div>
        <div class="card-sub">Invite & earn</div>
      </div>
    </div>

    <div class="section-title">Shop</div>
    <div class="card big" data-go="store">
      <div class="card-icon">▣</div>
      <div class="card-title">Explore available stock</div>
      <div class="card-sub">Choose a server and browse current inventory</div>
    </div>
  `;

  el.querySelectorAll('[data-go]').forEach(b =>
    b.onclick = () => switchTab(b.dataset.go)
  );
}

/* ---------------- STORE ---------------- */
async function renderStore() {
  setCrumbs(['Store']);
  const el = document.getElementById('main');

  el.innerHTML = `
    <div class="section-title">Choose Server</div>
    <div class="grid">
      <div class="card big" data-srv="s2">
        <div class="card-icon">📱</div>
        <div class="card-title">SERVER 2</div>
        <div class="card-sub">Telegram accounts • Live stock</div>
      </div>
      <div class="card big" data-srv="s3">
        <div class="card-icon">▤</div>
        <div class="card-title">SERVER 3</div>
        <div class="card-sub">Files • OSINT • Panels</div>
      </div>
    </div>
    <div class="note">Server 1 (LZT) is available from the bot chat through BUY SERVER (1).</div>
  `;

  el.querySelectorAll('[data-srv]').forEach(b =>
    b.onclick = () => openServer(b.dataset.srv)
  );
}

async function openServer(srv) {
  showLoader(true);
  try {
    if (srv === 's2') {
      setCrumbs(['Store','Server 2']);
      const cats = await api('/api/s2/categories');
      const el = document.getElementById('main');

      el.innerHTML = `
        <div class="section-title">Categories</div>
        <div class="list">
          ${cats.map(c => `
            <div class="row" data-cat="${esc(c.name)}">
              <div class="row-icon">${esc(c.emoji)}</div>
              <div class="row-main">
                <div class="row-title">${esc(c.name)}</div>
                <div class="row-sub">Browse available countries</div>
              </div>
              <div class="row-arrow">›</div>
            </div>
          `).join('') || '<div class="empty">No categories</div>'}
        </div>`;

      el.querySelectorAll('[data-cat]').forEach(r =>
        r.onclick = () => openCategory(r.dataset.cat)
      );
    } else if (srv === 's3') {
      setCrumbs(['Store','Server 3']);
      const secs = await api('/api/s3/sections');
      const el = document.getElementById('main');

      el.innerHTML = `
        <div class="section-title">Sections</div>
        <div class="list">
          ${secs.map(s => `
            <div class="row" data-sec="${esc(s)}">
              <div class="row-icon">▤</div>
              <div class="row-main">
                <div class="row-title">${esc(s)}</div>
                <div class="row-sub">View available products</div>
              </div>
              <div class="row-arrow">›</div>
            </div>
          `).join('') || '<div class="empty">No sections</div>'}
        </div>`;

      el.querySelectorAll('[data-sec]').forEach(r =>
        r.onclick = () => openSection(r.dataset.sec)
      );
    }
  } catch(e) {
    toast('❌ ' + e.message);
  } finally {
    showLoader(false);
  }
}

async function openCategory(cat) {
  showLoader(true);
  try {
    setCrumbs(['Store','Server 2',cat]);
    const items = await api(`/api/s2/category/${encodeURIComponent(cat)}`);
    const el = document.getElementById('main');

    el.innerHTML = `
      <div class="section-title">Countries</div>
      <div class="list">
        ${items.map(i => `
          <div class="row" data-country="${esc(i.country)}">
            <div class="row-icon">${esc(i.icon)}</div>
            <div class="row-main">
              <div class="row-title">${esc(i.country)}</div>
              <div class="row-sub">${i.count} available</div>
            </div>
            <div class="row-price">from ${fmt(i.min_price)}</div>
            <div class="row-arrow">›</div>
          </div>
        `).join('') || '<div class="empty">No stock</div>'}
      </div>`;

    el.querySelectorAll('[data-country]').forEach(r =>
      r.onclick = () => openCountry(cat, r.dataset.country)
    );
  } catch(e) {
    toast('❌ ' + e.message);
  } finally {
    showLoader(false);
  }
}

async function openCountry(cat, country) {
  showLoader(true);
  try {
    setCrumbs(['Store','Server 2',cat,country]);
    const items = await api(`/api/s2/${encodeURIComponent(cat)}/${encodeURIComponent(country)}`);
    const el = document.getElementById('main');

    el.innerHTML = `
      <div class="section-title">${esc(country)} • ${items.length} accounts</div>
      <div class="list">
        ${items.map(i => `
          <div class="row" data-phone="${esc(i.phone)}">
            <div class="row-icon">${esc(i.icon)}</div>
            <div class="row-main">
              <div class="row-title">+${esc(i.phone)}</div>
              <div class="row-sub">Available account</div>
            </div>
            <div class="row-price">${fmt(i.price)}</div>
            <div class="row-arrow">›</div>
          </div>
        `).join('') || '<div class="empty">No accounts available</div>'}
      </div>`;

    el.querySelectorAll('[data-phone]').forEach(r =>
      r.onclick = () => openItem(r.dataset.phone)
    );
  } catch(e) {
    toast('❌ ' + e.message);
  } finally {
    showLoader(false);
  }
}

async function openItem(phone) {
  showLoader(true);
  try {
    setCrumbs(['Store','Item']);
    const it = await api(`/api/item/${encodeURIComponent(phone)}`);
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

        <div class="warn">
          ⚠️ Use the supported client mentioned by the seller. Account availability and platform restrictions may change.
        </div>

        <button class="btn btn-success" id="buyBtn">Buy Now — ${fmt(it.price)}</button>
      </div>`;

    document.getElementById('buyBtn').onclick = () => buyItem(phone);
  } catch(e) {
    toast('❌ ' + e.message);
  } finally {
    showLoader(false);
  }
}

async function openSection(sec) {
  showLoader(true);
  try {
    setCrumbs(['Store','Server 3',sec]);
    const items = await api(`/api/s3/${encodeURIComponent(sec)}`);
    const el = document.getElementById('main');

    el.innerHTML = `
      <div class="section-title">${esc(sec)}</div>
      <div class="list">
        ${items.map(i => `
          <div class="row" data-id="${i.id}">
            <div class="row-icon">▤</div>
            <div class="row-main">
              <div class="row-title">${esc(i.name)}</div>
              ${i.description ? `<div class="row-sub">${esc(i.description.slice(0,60))}</div>` : ''}
            </div>
            <div class="row-price">${fmt(i.price)}</div>
            <div class="row-arrow">›</div>
          </div>
        `).join('') || '<div class="empty">No products available</div>'}
      </div>`;

    el.querySelectorAll('[data-id]').forEach(r =>
      r.onclick = () => buyFileProduct(Number(r.dataset.id))
    );
  } catch(e) {
    toast('❌ ' + e.message);
  } finally {
    showLoader(false);
  }
}

/* ---------------- PURCHASE ---------------- */
async function buyItem(phone) {
  showLoader(true);
  try {
    const r = await api('/api/purchase', {
      method:'POST',
      body:JSON.stringify({phone})
    });

    toast(`✅ Order ${r.order_id} placed!`);
    if (tg?.showAlert) {
      tg.showAlert('Order placed!\n\nThe bot will send the OTP here automatically.');
    }

    await loadMe();
    switchTab('home');
  } catch(e) {
    toast('❌ ' + e.message);
  } finally {
    showLoader(false);
  }
}

async function buyFileProduct(productId) {
  showLoader(true);
  try {
    const r = await api('/api/purchase/file', {
      method:'POST', body:JSON.stringify({product_id: productId})
    });
    toast(`✅ ${r.name} purchased`);
    const result = document.getElementById('main');
    result.innerHTML = `
      <div class="detail purchase-success-card">
        <div class="success-icon">✓</div>
        <div class="detail-title">Purchase Successful</div>
        <div class="detail-price">${fmt(r.amount)}</div>
        <div class="detail-rows">
          <div><span>Product</span><b>${esc(r.name)}</b></div>
          <div><span>Order ID</span><b><code>${esc(r.order_id)}</code></b></div>
        </div>
        ${r.link ? `<a class="btn btn-success" href="${esc(r.link)}" target="_blank" rel="noopener">Open / Download</a>` : `<div class="note">Delivery link is not configured. Contact support.</div>`}
        <button class="btn btn-primary" id="backStore">Back to Store</button>
      </div>`;
    document.getElementById('backStore').onclick = () => switchTab('store');
    await loadMe();
  } catch(e) {
    toast('❌ ' + e.message);
  } finally {
    showLoader(false);
  }
}

function renderPaymentStatus(oid) {
  const box = document.getElementById('paymentStatus');
  if (!box) return;
  box.innerHTML = `<div class="payment-status waiting"><span class="status-dot"></span><span>Waiting for payment verification…</span></div>`;
}

async function verifyPaymentRef(oid) {
  const utr = (document.getElementById('utrInput')?.value || '').trim();
  const txn = (document.getElementById('txnInput')?.value || '').trim();
  if (!utr && !txn) { toast('Enter UTR or Transaction ID'); return; }
  const btn = document.getElementById('verifyPaymentBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Verifying…'; }
  try {
    const r = await api('/api/verify-payment', {
      method:'POST', body:JSON.stringify({order_id:oid, utr:utr || null, txn:txn || null})
    });
    if (r.verified && r.status === 'success') {
      toast(`✅ ₹${r.amount || ''} credited successfully!`, 3500);
      await loadMe();
      const box = document.getElementById('paymentStatus');
      if (box) box.innerHTML = `<div class="payment-status success"><span>✓</span><span>${esc(r.message)}</span></div>`;
      setTimeout(() => switchTab('home'), 1200);
    } else {
      toast('⚠️ ' + (r.message || r.status || 'Verification pending'));
    }
  } catch(e) {
    toast('❌ ' + e.message);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Verify UTR / TXN'; }
  }
}

/* ---------------- DEPOSIT ---------------- */
async function renderDeposit() {
  setCrumbs(null);
  const c = STATE.config;
  const el = document.getElementById('main');

  el.innerHTML = `
    <div class="section-title">Add Balance</div>
    <div class="deposit-box">
      <label>Amount in INR</label>
      <input type="number" id="depAmt" min="${c.min_deposit}" placeholder="Minimum ₹${c.min_deposit}">
      <div class="quick">
        ${[50,100,200,500,1000].map(v =>
          `<button data-v="${v}">₹${v}</button>`).join('')}
      </div>
    </div>

    <div class="section-title">Payment Method</div>
    <div class="grid">
      <div class="card" data-m="auto">
        <div class="card-icon">⚡</div>
        <div class="card-title">UPI Auto</div>
        <div class="card-sub">Automatic verification</div>
      </div>
      <div class="card" data-m="manual">
        <div class="card-icon">▤</div>
        <div class="card-title">UPI Manual</div>
        <div class="card-sub">Admin verification</div>
      </div>
    </div>
    <div id="depResult"></div>`;

  const amt = el.querySelector('#depAmt');
  el.querySelectorAll('.quick button').forEach(b =>
    b.onclick = () => amt.value = b.dataset.v
  );
  el.querySelectorAll('[data-m]').forEach(b =>
    b.onclick = () => makeDeposit(b.dataset.m, +amt.value)
  );
}

async function makeDeposit(method, amount) {
  if (!amount || amount < STATE.config.min_deposit) {
    toast(`Minimum ₹${STATE.config.min_deposit}`);
    return;
  }
  showLoader(true);
  try {
    const r = await api(`/api/deposit/${method}`, {
      method:'POST', body:JSON.stringify({amount})
    });
    const qr = `https://api.qrserver.com/v1/create-qr-code/?size=320x320&margin=8&data=${encodeURIComponent(r.upi_url)}`;
    document.getElementById('depResult').innerHTML = `
      <div class="pay-card rainbow-pay-card">
        <div class="pay-badge">SECURE UPI PAYMENT</div>
        <div class="pay-title">Pay ${fmt(r.amount)}</div>
        <div class="pay-subtitle">Scan QR • Pay exact amount • Verify with UTR/TXN</div>
        <div class="qr-frame">
          <div class="qr-frame-inner">
            <img src="${qr}" alt="Payment QR" class="qr">
          </div>
        </div>
        <div class="upi-id">UPI ID: <b>${esc(r.upi_id)}</b></div>
        <a class="btn btn-primary" href="${esc(r.upi_url)}">Open UPI App</a>
        <div class="payment-meta">
          <div><span>Amount</span><b>${fmt(r.amount)}</b></div>
          <div><span>Order</span><code>${esc(r.order_id)}</code></div>
        </div>
        <div class="verify-box">
          <div class="verify-title">Payment Verification</div>
          <div class="verify-hint">After payment, enter either your UTR or Transaction ID.</div>
          <input id="utrInput" class="verify-input" type="text" inputmode="numeric" autocomplete="off" placeholder="UTR / UTR Number">
          <input id="txnInput" class="verify-input" type="text" autocomplete="off" placeholder="Transaction ID (optional)">
          <button class="btn btn-success" id="verifyPaymentBtn">Verify UTR / TXN</button>
          <div id="paymentStatus"></div>
        </div>
        <div class="note">Do not submit the same UTR/TXN for another order. Verification only credits the exact order amount.</div>
      </div>`;
    renderPaymentStatus(r.order_id);
    document.getElementById('verifyPaymentBtn').onclick = () => verifyPaymentRef(r.order_id);
    if (method === 'auto') pollOrder(r.order_id);
  } catch(e) {
    toast('❌ ' + e.message);
  } finally {
    showLoader(false);
  }
}


function pollOrder(oid) {
  let n = 0;
  const t = setInterval(async () => {
    n++;
    if (n > 60) { clearInterval(t); return; }

    try {
      const r = await api(`/api/order/${oid}`);

      if (r.status === 'success') {
        clearInterval(t);
        toast('✅ Payment credited!');
        await loadMe();
        switchTab('home');
      } else if (['expired','failed','mismatch','duplicate'].includes(r.status)) {
        clearInterval(t);
        toast('❌ ' + r.status);
      }
    } catch(e){}
  },5000);
}

/* ---------------- PROFILE ---------------- */
async function renderProfile() {
  setCrumbs(null);
  const u = STATE.user;
  const el = document.getElementById('main');

  el.innerHTML = `
    <div class="section-title">Profile</div>
    <div class="profile">
      <div class="p-name">${esc(u.first_name || 'User')} ${esc(u.last_name || '')}</div>
      <div class="p-id">ID: ${esc(u.user_id)} ${u.username ? '@'+esc(u.username) : ''}</div>
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
    document.getElementById('hist').innerHTML =
      rows.map(r => `
        <div class="row">
          <div class="row-icon">📱</div>
          <div class="row-main">
            <div class="row-title">${esc(r.phone || '—')}</div>
            <div class="row-sub">${esc(r.country || '')} • ${esc((r.date||'').slice(0,16))}</div>
          </div>
          <div class="row-price">${fmt(r.price)}</div>
        </div>
      `).join('') || '<div class="empty">No purchases yet</div>';
  } catch(e) {
    document.getElementById('hist').innerHTML =
      '<div class="empty">Could not load history</div>';
  }
}

/* ---------------- REFER ---------------- */
async function renderRefer() {
  setCrumbs(null);
  try {
    const r = await api('/api/refer');
    const el = document.getElementById('main');

    el.innerHTML = `
      <div class="section-title">Refer & Earn</div>
      <div class="refer-box">
        <div class="refer-link">${esc(r.link)}</div>
        <button class="btn btn-primary" id="copyLink">Copy Referral Link</button>
        <a class="btn btn-success"
           href="https://t.me/share/url?url=${encodeURIComponent(r.link)}&text=Join+VILLAGEE+SMS+SHOP"
           target="_blank">Share on Telegram</a>
      </div>`;

    document.getElementById('copyLink').onclick = async () => {
      try {
        await navigator.clipboard.writeText(r.link);
        toast('Referral link copied!');
      } catch(e) {
        toast('Copy failed');
      }
    };
  } catch(e) {
    toast('❌ ' + e.message);
  }
}

/* ---------------- TABS ---------------- */
function switchTab(tab) {
  STATE.tab = tab;
  document.querySelectorAll('#tabs button').forEach(b =>
    b.classList.toggle('active', b.dataset.tab === tab)
  );

  const routes = {
    home:renderHome,
    store:renderStore,
    deposit:renderDeposit,
    profile:renderProfile,
    refer:renderRefer
  };

  (routes[tab] || renderHome)();
}

document.querySelectorAll('#tabs button').forEach(b =>
  b.onclick = () => switchTab(b.dataset.tab)
);

/* ---------------- INIT ---------------- */
(async function init() {
  if (!BOT_USERNAME) {
    document.getElementById('main').innerHTML =
      '<div class="empty">Missing bot parameter. Open this Mini App from Telegram.</div>';
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
    switchTab('home');
  } catch(e) {
    document.getElementById('main').innerHTML =
      `<div class="empty">Error: ${esc(e.message)}</div>`;
  } finally {
    showLoader(false);
  }
})();
