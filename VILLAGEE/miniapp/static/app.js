const tg = window.Telegram?.WebApp;
const BOT_USERNAME = new URLSearchParams(location.search).get('bot') || '';
const STATE = { config:null, user:null, tab:'store', paymentTimer:null };

tg?.ready();
tg?.expand();
try { tg?.setHeaderColor('#f7f7fa'); tg?.setBackgroundColor('#f7f7fa'); } catch(e) {}

async function api(path, opts={}) {
  const headers = {
    'X-Bot-Username': BOT_USERNAME,
    'X-Init-Data': tg?.initData || '',
    'Content-Type': 'application/json',
    ...(opts.headers || {})
  };
  const res = await fetch(path, {...opts, headers});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText || 'Request failed');
  return data;
}
function esc(v){return String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function fmt(v){return '₹'+Number(v||0).toFixed(0);}
function toast(msg,ms=2400){const e=document.getElementById('toast');e.textContent=msg;e.classList.add('show');clearTimeout(e._t);e._t=setTimeout(()=>e.classList.remove('show'),ms);}
function loading(v){document.getElementById('loader').classList.toggle('hidden',!v);}
function crumbs(parts){const e=document.getElementById('crumbs');if(!parts){e.classList.add('hidden');return;}e.innerHTML=parts.map((p,i)=>`<span${i===parts.length-1?' class="last"':''}>${esc(p)}</span>`).join('<b>›</b>');e.classList.remove('hidden');}
function setBalance(){document.getElementById('balance').textContent=fmt(STATE.user?.balance);}
async function loadMe(){STATE.user=await api('/api/me');setBalance();}
async function loadConfig(){STATE.config=await api('/api/config');}
function go(tab){switchTab(tab);}
function navButtons(){document.querySelectorAll('#tabs button').forEach(b=>b.classList.toggle('active',b.dataset.tab===STATE.tab));}
function openBotServer1(){
  const url=`https://t.me/${encodeURIComponent(BOT_USERNAME)}?start=AllServer1`;
  try{tg?.openTelegramLink(url);}catch(e){window.open(url,'_blank','noopener');}
}

/* MARKET */
async function renderStore(){
  crumbs(null);
  const u=STATE.user, c=STATE.config||{};
  let counts={s2:0,s3:0};
  try{counts=await api('/api/servers');}catch(e){}
  const el=document.getElementById('main');
  el.innerHTML=`
    <section class="hero">
      <div class="hello">Hello, ${esc(u?.first_name||'User')} 👋</div>
      <div class="hero-bal">${fmt(u?.balance)}</div>
      <div class="hero-sub">Wallet balance • Ready to shop</div>
    </section>

    <div class="section-title">Quick Actions</div>
    <div class="grid">
      <button class="card" data-go="deposit" type="button"><div class="card-icon">＋</div><div class="card-title">Recharge</div><div class="card-sub">Add balance with UPI</div></button>
      <button class="card" data-go="profile" type="button"><div class="card-icon">◉</div><div class="card-title">My Orders</div><div class="card-sub">History & account</div></button>
      <button class="card" data-go="refer" type="button"><div class="card-icon">↗</div><div class="card-title">Refer</div><div class="card-sub">Share & earn</div></button>
      <button class="card" data-action="server1" type="button"><div class="card-icon">🌐</div><div class="card-title">Server 1</div><div class="card-sub">Open in Telegram</div></button>
    </div>

    <div class="section-title">Marketplace</div>
    <div class="grid">
      <button class="card big" data-srv="s2" type="button">
        <div class="card-icon">📱</div><div class="card-title">SERVER 2</div>
        <div class="card-sub">Telegram account stock • ${Number(counts.s2?.count||0)} available</div>
      </button>
      <button class="card big" data-srv="s3" type="button">
        <div class="card-icon">▤</div><div class="card-title">SERVER 3</div>
        <div class="card-sub">Digital products • ${Number(counts.s3?.count||0)} available</div>
      </button>
    </div>
    <div class="note">Purchases use your wallet balance. Recharge first if your balance is too low. Server 1 remains in the Telegram bot because its live external-market flow is bot-native.</div>`;
  el.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>go(b.dataset.go));
  el.querySelectorAll('[data-srv]').forEach(b=>b.onclick=()=>openServer(b.dataset.srv));
  el.querySelector('[data-action="server1"]').onclick=openBotServer1;
}

async function openServer(srv){
  loading(true);
  try{
    if(srv==='s2'){
      crumbs(['Market','Server 2']);
      const cats=await api('/api/s2/categories');
      const el=document.getElementById('main');
      el.innerHTML=`<div class="section-title">Categories</div><div class="list">${cats.map(c=>`
        <button class="row" data-cat="${esc(c.name)}" type="button"><div class="row-icon">${esc(c.emoji)}</div><div class="row-main"><div class="row-title">${esc(c.name)}</div><div class="row-sub">Browse countries & live stock</div></div><div class="row-arrow">›</div></button>`).join('')||'<div class="empty">No categories available</div>'}</div>`;
      el.querySelectorAll('[data-cat]').forEach(b=>b.onclick=()=>openCategory(b.dataset.cat));
    }else{
      crumbs(['Market','Server 3']);
      const secs=await api('/api/s3/sections');
      const el=document.getElementById('main');
      el.innerHTML=`<div class="section-title">Sections</div><div class="list">${secs.map(s=>`
        <button class="row" data-sec="${esc(s)}" type="button"><div class="row-icon">▤</div><div class="row-main"><div class="row-title">${esc(s)}</div><div class="row-sub">Open products</div></div><div class="row-arrow">›</div></button>`).join('')||'<div class="empty">No products available</div>'}</div>`;
      el.querySelectorAll('[data-sec]').forEach(b=>b.onclick=()=>openSection(b.dataset.sec));
    }
  }catch(e){toast('❌ '+e.message);}finally{loading(false);}
}

async function openCategory(cat){
  loading(true);
  try{
    crumbs(['Market','Server 2',cat]);
    const items=await api(`/api/s2/category/${encodeURIComponent(cat)}`);
    const el=document.getElementById('main');
    el.innerHTML=`<div class="section-title">Countries</div><div class="list">${items.map(i=>`
      <button class="row" data-country="${esc(i.country)}" type="button"><div class="row-icon">${esc(i.icon)}</div><div class="row-main"><div class="row-title">${esc(i.country)}</div><div class="row-sub">${Number(i.count)} available</div></div><div class="row-price">from ${fmt(i.min_price)}</div><div class="row-arrow">›</div></button>`).join('')||'<div class="empty">No stock</div>'}</div>`;
    el.querySelectorAll('[data-country]').forEach(b=>b.onclick=()=>openCountry(cat,b.dataset.country));
  }catch(e){toast('❌ '+e.message);}finally{loading(false);}
}

async function openCountry(cat,country){
  loading(true);
  try{
    crumbs(['Market','Server 2',cat,country]);
    const items=await api(`/api/s2/${encodeURIComponent(cat)}/${encodeURIComponent(country)}`);
    const el=document.getElementById('main');
    el.innerHTML=`<div class="section-title">${esc(country)} • ${items.length} accounts</div><div class="list">${items.map(i=>`
      <button class="row" data-phone="${esc(i.phone)}" type="button"><div class="row-icon">${esc(i.icon)}</div><div class="row-main"><div class="row-title">+${esc(i.phone)}</div><div class="row-sub">Available now</div></div><div class="row-price">${fmt(i.price)}</div><div class="row-arrow">›</div></button>`).join('')||'<div class="empty">No accounts available</div>'}</div>`;
    el.querySelectorAll('[data-phone]').forEach(b=>b.onclick=()=>openItem(b.dataset.phone));
  }catch(e){toast('❌ '+e.message);}finally{loading(false);}
}

async function openItem(phone){
  loading(true);
  try{
    const it=await api(`/api/item/${encodeURIComponent(phone)}`);
    crumbs(['Market','Server 2','Account']);
    const el=document.getElementById('main');
    el.innerHTML=`<div class="detail">
      <div class="detail-title">${esc(it.country_icon)} ${esc(it.country_name)}</div>
      <div class="detail-price">${fmt(it.price)}</div>
      <div class="detail-rows">
        <div><span>Category</span><b>${esc(it.category)}</b></div>
        <div><span>Server</span><b>${esc(it.server)}</b></div>
        <div><span>2FA</span><b>${esc(it.twofa||'None')}</b></div>
        <div><span>Phone</span><b>+${esc(it.phone)}</b></div>
        ${it.description?`<div><span>Info</span><b>${esc(it.description)}</b></div>`:''}
      </div>
      <div class="warn">The purchase is processed by the Telegram bot worker. After a successful purchase, OTP/status updates are sent to your Telegram chat.</div>
      <button class="btn btn-success" id="buyBtn" type="button">Buy Now — ${fmt(it.price)}</button>
    </div>`;
    el.querySelector('#buyBtn').onclick=()=>buyItem(phone);
  }catch(e){toast('❌ '+e.message);}finally{loading(false);}
}

async function buyItem(phone){
  const b=document.getElementById('buyBtn'); if(b){b.disabled=true;b.textContent='Processing…';}
  try{
    const r=await api('/api/purchase',{method:'POST',body:JSON.stringify({phone})});
    await loadMe();
    document.getElementById('main').innerHTML=`<div class="detail purchase-success-card">
      <div class="success-icon">✓</div><div class="detail-title">Purchase accepted</div>
      <div class="detail-price">${fmt(r.amount)}</div>
      <div class="detail-rows"><div><span>Order</span><b>${esc(r.order_id)}</b></div><div><span>Phone</span><b>+${esc(r.phone)}</b></div><div><span>Status</span><b>OTP worker active</b></div></div>
      <div class="note">${esc(r.message||'Check your Telegram chat for the next step.')}</div>
      <button class="btn btn-primary" id="openChat" type="button">Open Telegram Chat</button>
      <button class="btn btn-success" id="backMarket" type="button">Back to Market</button>
    </div>`;
    document.getElementById('openChat').onclick=()=>{try{tg?.close();}catch(e){}};
    document.getElementById('backMarket').onclick=()=>go('store');
    toast('✅ Purchase accepted');
  }catch(e){toast('❌ '+e.message);if(b){b.disabled=false;b.textContent='Buy Now';}}
}

/* SERVER 3 */
async function openSection(sec){
  loading(true);
  try{
    crumbs(['Market','Server 3',sec]);
    const items=await api(`/api/s3/${encodeURIComponent(sec)}`);
    const el=document.getElementById('main');
    el.innerHTML=`<div class="section-title">${esc(sec)}</div><div class="list">${items.map(i=>`
      <button class="row" data-id="${i.id}" type="button"><div class="row-icon">▤</div><div class="row-main"><div class="row-title">${esc(i.name)}</div><div class="row-sub">${esc(i.description||'Digital product')}</div></div><div class="row-price">${fmt(i.price)}</div><div class="row-arrow">›</div></button>`).join('')||'<div class="empty">No products available</div>'}</div>`;
    el.querySelectorAll('[data-id]').forEach(b=>b.onclick=()=>buyFile(Number(b.dataset.id)));
  }catch(e){toast('❌ '+e.message);}finally{loading(false);}
}
async function buyFile(id){
  loading(true);
  try{
    const r=await api('/api/purchase/file',{method:'POST',body:JSON.stringify({product_id:id})});
    await loadMe();
    const link=r.link||''; const ep=r.api_endpoint||''; const key=r.api_key||''; const usage=r.usage_url||'';
    document.getElementById('main').innerHTML=`<div class="detail purchase-success-card"><div class="success-icon">✓</div><div class="detail-title">Purchase complete</div><div class="detail-price">${fmt(r.amount)}</div>
      <div class="detail-rows"><div><span>Product</span><b>${esc(r.name)}</b></div><div><span>Order</span><b>${esc(r.order_id)}</b></div>${ep?`<div><span>API</span><b>${esc(ep)}</b></div>`:''}${r.expiry?`<div><span>Expiry</span><b>${esc(r.expiry)}</b></div>`:''}</div>
      ${key?`<div class="note"><b>API Key</b><br><code>${esc(key)}</code>${usage?`<br><br><b>Example</b><br><code>${esc(usage)}</code>`:''}</div>`:''}
      ${link?`<a class="btn btn-primary" href="${esc(link)}" target="_blank" rel="noopener">Open Delivery</a>`:''}
      <button class="btn btn-success" id="backMarket2" type="button">Back to Market</button></div>`;
    document.getElementById('backMarket2').onclick=()=>go('store');
    toast('✅ Purchase complete');
  }catch(e){toast('❌ '+e.message);}finally{loading(false);}
}

/* WALLET */
async function renderDeposit(){
  crumbs(null); const c=STATE.config||{}; const el=document.getElementById('main');
  el.innerHTML=`<div class="section-title">Wallet</div><div class="hero wallet-hero"><div class="hello">Available balance</div><div class="hero-bal">${fmt(STATE.user?.balance)}</div><div class="hero-sub">Minimum recharge ${fmt(c.min_deposit)}</div></div>
    <div class="section-title">Recharge Amount</div><div class="deposit-box"><label for="depAmt">Amount in INR</label><input id="depAmt" type="number" min="${Number(c.min_deposit||1)}" inputmode="numeric" placeholder="Minimum ₹${Number(c.min_deposit||1)}"><div class="quick">${[50,100,200,500,1000].map(v=>`<button type="button" data-v="${v}">₹${v}</button>`).join('')}</div></div>
    <div class="section-title">Payment Method</div><div class="grid"><button class="card" data-method="auto" type="button"><div class="card-icon">⚡</div><div class="card-title">UPI Auto</div><div class="card-sub">Auto verification when bank email is matched</div></button><button class="card" data-method="manual" type="button"><div class="card-icon">▤</div><div class="card-title">UPI Manual</div><div class="card-sub">UTR + admin approval</div></button></div><div id="depResult"></div>`;
  const amt=el.querySelector('#depAmt');el.querySelectorAll('.quick button').forEach(b=>b.onclick=()=>amt.value=b.dataset.v);el.querySelectorAll('[data-method]').forEach(b=>b.onclick=()=>makeDeposit(b.dataset.method,Number(amt.value||0)));
}
async function makeDeposit(method,amount){
  const min=Number(STATE.config?.min_deposit||1); if(!Number.isFinite(amount)||amount<min){toast(`Minimum ${fmt(min)}`);return;}
  loading(true);
  try{
    const r=await api(`/api/deposit/${method}`,{method:'POST',body:JSON.stringify({amount:Math.floor(amount)})});
    const qr=`https://api.qrserver.com/v1/create-qr-code/?size=320x320&margin=8&data=${encodeURIComponent(r.upi_url)}`;
    document.getElementById('depResult').innerHTML=`<div class="rainbow-pay-card"><div class="pay-badge">SECURE UPI PAYMENT</div><div class="pay-title">Pay ${fmt(r.amount)}</div><div class="pay-subtitle">Scan QR • Pay exact amount • Submit UTR/TXN</div><div class="qr-frame"><div class="qr-frame-inner"><img class="qr" src="${qr}" alt="UPI payment QR"></div></div><div class="upi-id">UPI ID: <b>${esc(r.upi_id)}</b></div><div class="payment-meta"><div><span>Amount</span><b>${fmt(r.amount)}</b></div><div><span>Order</span><code>${esc(r.order_id)}</code></div></div><button class="btn btn-primary" id="downloadQr" type="button">Download QR</button><div class="verify-box"><div class="verify-title">Payment Verification</div><div class="verify-hint">After payment, enter the UTR or transaction ID.</div><input id="paymentRef" class="verify-input" type="text" autocomplete="off" placeholder="UTR / TXN ID"><button class="btn btn-success" id="verifyPayment" type="button">Submit & Verify</button><div id="paymentStatus"></div></div><div class="note">Auto UPI credits when a matching bank/FamPay record is found. Manual UPI sends the UTR to the Telegram owner for approval.</div></div>`;
    document.getElementById('downloadQr').onclick=()=>downloadQR(qr,r.order_id);
    document.getElementById('verifyPayment').onclick=()=>verifyPayment(r.order_id);
    renderPaymentStatus(r.order_id);
    if(method==='auto') pollPayment(r.order_id);
  }catch(e){toast('❌ '+e.message);}finally{loading(false);}
}
async function downloadQR(url,oid){try{const r=await fetch(url);if(!r.ok)throw 0;const blob=await r.blob();const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=`VILLAGEE_QR_${oid}.png`;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1000);}catch(e){window.open(url,'_blank','noopener');}}
async function verifyPayment(oid){
  const input=document.getElementById('paymentRef'), btn=document.getElementById('verifyPayment'); const ref=(input?.value||'').trim();
  if(ref.length<4){toast('Enter a valid UTR/TXN');return;} if(btn){btn.disabled=true;btn.textContent='Checking…';}
  try{const r=await api('/api/verify-payment',{method:'POST',body:JSON.stringify({order_id:oid,utr:ref})});renderPaymentStatus(oid);toast(r.message||'Submitted');if(r.status==='success'){await loadMe();}}
  catch(e){toast('❌ '+e.message);renderPaymentStatus(oid);}finally{if(btn){btn.disabled=false;btn.textContent='Submit & Verify';}}
}
async function renderPaymentStatus(oid){const el=document.getElementById('paymentStatus');if(!el)return;try{const r=await api(`/api/order/${encodeURIComponent(oid)}`);const ok=r.status==='success';el.className=`payment-status ${ok?'success':'waiting'}`;el.innerHTML=`<div><span class="status-dot"></span>${ok?'Payment credited':'Status: '+esc(r.status||'pending')}</div>`;}catch(e){}}
function pollPayment(oid){clearInterval(STATE.paymentTimer);let n=0;STATE.paymentTimer=setInterval(async()=>{n++;if(n>90){clearInterval(STATE.paymentTimer);return;}try{const r=await api(`/api/order/${encodeURIComponent(oid)}`);if(r.status==='success'){clearInterval(STATE.paymentTimer);await loadMe();renderPaymentStatus(oid);toast('✅ Balance credited');}else if(['expired','failed','mismatch','duplicate'].includes(r.status)){clearInterval(STATE.paymentTimer);renderPaymentStatus(oid);}}catch(e){}},5000);}

/* REFERRAL */
async function renderRefer(){
  crumbs(null); loading(true);
  try{
    const [r, referrals, earnings] = await Promise.all([
      api('/api/refer'), api('/api/referrals'), api('/api/referral-history')
    ]);
    const el=document.getElementById('main');
    el.innerHTML=`
      <div class="section-title">Referral Program</div>
      <div class="refer-box">
        <div class="refer-head">Share your link — earn for every referral</div>
        <div class="refer-link">${esc(r.link)}</div>
        <button class="btn btn-primary" id="copyReferral" type="button">Copy Link</button>
        <a class="btn btn-success" href="https://t.me/share/url?url=${encodeURIComponent(r.link)}&text=${encodeURIComponent('Join VILLAGEE SMS SHOP')}" target="_blank" rel="noopener">Share on Telegram</a>
      </div>
      <div class="section-title">Referral Summary</div>
      <div class="stats">
        <div class="stat"><div class="s-val">${Number(STATE.user?.referral_count||referrals.length||0)}</div><div class="s-lbl">Total Referrals</div></div>
        <div class="stat"><div class="s-val">${fmt(STATE.user?.referral_earnings)}</div><div class="s-lbl">Referral Earnings</div></div>
      </div>
      <div class="section-title">Refer History</div>
      <div class="list">
        ${referrals.map(x=>`<div class="row"><div class="row-icon">👤</div><div class="row-main"><div class="row-title">${esc(((x.first_name||'User')+' '+(x.last_name||'')).trim())}</div><div class="row-sub">${x.username?'@'+esc(x.username)+' • ':''}ID ${esc(x.user_id)} • ${esc((x.joined_date||'').slice(0,16))}</div></div><div class="row-price">Joined</div></div>`).join('') || '<div class="empty">No referrals yet</div>'}
      </div>
      <div class="section-title">Referral Earnings History</div>
      <div class="list">
        ${earnings.map(x=>`<div class="row"><div class="row-icon">🎁</div><div class="row-main"><div class="row-title">Bonus ${fmt(x.bonus_amount)}</div><div class="row-sub">User ${esc(x.referred_user_id)} • Deposit ${fmt(x.deposit_amount)} • ${esc((x.date||'').slice(0,16))}</div></div><div class="row-price">+${fmt(x.bonus_amount)}</div></div>`).join('') || '<div class="empty">No referral earnings yet</div>'}
      </div>`;
    document.getElementById('copyReferral').onclick=async()=>{
      try{await navigator.clipboard.writeText(r.link);toast('✅ Link copied');}
      catch(e){toast('Copy blocked by browser');}
    };
  }catch(e){toast('❌ '+e.message);}
  finally{loading(false);}
}

/* PROFILE + SEPARATE HISTORY / LEGAL PAGES */
async function renderProfile(){
  crumbs(null);
  const u=STATE.user, el=document.getElementById('main');
  el.innerHTML=`
    <div class="section-title">Profile</div>
    <div class="profile">
      <div class="p-name">${esc(((u.first_name||'User')+' '+(u.last_name||'')).trim())}</div>
      <div class="p-id">ID: ${esc(u.user_id)} ${u.username?'@'+esc(u.username):''}</div>
    </div>
    <div class="stats">
      <div class="stat"><div class="s-val">${fmt(u.balance)}</div><div class="s-lbl">Balance</div></div>
      <div class="stat"><div class="s-val">${fmt(u.total_deposited)}</div><div class="s-lbl">Deposited</div></div>
      <div class="stat"><div class="s-val">${Number(u.total_purchases||0)}</div><div class="s-lbl">Purchases</div></div>
      <div class="stat"><div class="s-val">${Number(u.referral_count||0)}</div><div class="s-lbl">Referrals</div></div>
    </div>
    <div class="section-title">History</div>
    <div class="list">
      <button class="row" data-profile-page="purchases" type="button"><div class="row-icon">📦</div><div class="row-main"><div class="row-title">Purchase History</div><div class="row-sub">All purchased accounts, files and products</div></div><div class="row-arrow">›</div></button>
      <button class="row" data-profile-page="recharges" type="button"><div class="row-icon">💳</div><div class="row-main"><div class="row-title">Recharge History</div><div class="row-sub">UPI auto/manual recharge records</div></div><div class="row-arrow">›</div></button>
      <button class="row" data-profile-page="referrals" type="button"><div class="row-icon">👥</div><div class="row-main"><div class="row-title">Referral History</div><div class="row-sub">People referred and referral earnings</div></div><div class="row-arrow">›</div></button>
    </div>
    <div class="section-title">Terms & Policies</div>
    <div class="list">
      <button class="row" data-profile-page="terms" type="button"><div class="row-icon">📄</div><div class="row-main"><div class="row-title">Terms & Conditions</div><div class="row-sub">Rules for using VILLAGEE SMS SHOP</div></div><div class="row-arrow">›</div></button>
      <button class="row" data-profile-page="refund" type="button"><div class="row-icon">🚫</div><div class="row-main"><div class="row-title">Refund Policy</div><div class="row-sub">All purchases are final — no refund</div></div><div class="row-arrow">›</div></button>
      <button class="row" data-profile-page="privacy" type="button"><div class="row-icon">🛡️</div><div class="row-main"><div class="row-title">Privacy Policy</div><div class="row-sub">How account and order information is used</div></div><div class="row-arrow">›</div></button>
    </div>
    <div class="section-title">Support</div>
    <button class="row" id="openSupport" type="button"><div class="row-icon">❓</div><div class="row-main"><div class="row-title">Help & Support</div><div class="row-sub">Open support in Telegram</div></div><div class="row-arrow">›</div></button>`;
  el.querySelectorAll('[data-profile-page]').forEach(b=>b.onclick=()=>openProfilePage(b.dataset.profilePage));
  document.getElementById('openSupport').onclick=()=>{
    const url=STATE.config?.support_url || `https://t.me/${encodeURIComponent(BOT_USERNAME)}`;
    try{tg?.openTelegramLink(url);}catch(e){window.open(url,'_blank','noopener');}
  };
}

function policyPage(title, icon, sections){
  const el=document.getElementById('main');
  el.innerHTML=`<button class="btn btn-success" id="backProfile" type="button">← Back to Profile</button><div class="section-title">${icon} ${title}</div><div class="detail policy-page">${sections.map(s=>`<div class="policy-section"><div class="detail-title">${esc(s[0])}</div><div class="policy-text">${esc(s[1])}</div></div>`).join('')}</div>`;
  document.getElementById('backProfile').onclick=renderProfile;
}

async function openProfilePage(page){
  crumbs(['Profile', page]);
  loading(true);
  try{
    if(page==='terms'){
      policyPage('Terms & Conditions','📄',[
        ['1. Acceptance','By using VILLAGEE SMS SHOP, you agree to these Terms & Conditions. If you do not agree, do not use the marketplace.'],
        ['2. Account','You must provide accurate Telegram account information and keep your account secure. You are responsible for activity performed through your account.'],
        ['3. Purchases','Orders are processed using the wallet balance shown in the Mini App. Product details, availability and delivery can vary by server.'],
        ['4. Account Products','Only use products/accounts in accordance with applicable laws and the product instructions. Do not submit or use accounts that you do not own or have permission to use.'],
        ['5. Prohibited Use','Fraud, abuse, chargeback abuse, stolen accounts, payment manipulation and attempts to bypass marketplace security may result in account suspension.'],
        ['6. Changes','The marketplace may update products, prices, features or these terms. Continued use after an update means you accept the updated terms.']
      ]);
      return;
    }
    if(page==='refund'){
      policyPage('Refund Policy','🚫',[
        ['No Refund Policy','ALL PURCHASES ARE FINAL AND NON-REFUNDABLE. Once a product/order has been delivered, purchased or processed, the amount will not be refunded.'],
        ['Before Purchase','Check the product, country, category, price and other displayed details before confirming payment. Ask support if you need clarification before buying.'],
        ['Failed Technical Order','If the system records a genuine failed transaction before delivery, the marketplace may automatically restore the wallet amount where applicable. This is a transaction correction, not a general refund policy.'],
        ['Payment Disputes','Do not submit false UTRs, duplicate payment claims or chargeback claims for completed purchases. Such activity may result in account restrictions.']
      ]);
      return;
    }
    if(page==='privacy'){
      policyPage('Privacy Policy','🛡️',[
        ['Information Used','The service may process your Telegram user ID, name, username, wallet activity, orders, recharge records and referral records to operate the marketplace.'],
        ['Payments','UPI order information such as order ID, amount and submitted transaction reference may be stored for verification and fraud prevention.'],
        ['Orders & Delivery','Purchase and delivery information may be retained so the bot can complete orders, provide support and maintain transaction records.'],
        ['Security','Access to Mini App data is authenticated using Telegram WebApp initData. Do not share your Telegram account or payment credentials with others.'],
        ['Data Requests','For account or data-related questions, contact the support channel provided by the bot.']
      ]);
      return;
    }
    if(page==='purchases'){
      const rows=await api('/api/history');
      const el=document.getElementById('main');
      el.innerHTML=`<button class="btn btn-success" id="backProfile" type="button">← Back to Profile</button><div class="section-title">📦 Purchase History</div><div class="list">${rows.map(r=>`<div class="row"><div class="row-icon">📦</div><div class="row-main"><div class="row-title">${esc(r.phone||'Digital product')}</div><div class="row-sub">${esc(r.section||'ORDER')} • ${esc(r.country||'')} • ${esc((r.date||'').slice(0,16))}${r.status?' • '+esc(r.status):''}</div></div><div class="row-price">${fmt(r.price)}</div></div>`).join('')||'<div class="empty">No purchases yet</div>'}</div>`;
      document.getElementById('backProfile').onclick=renderProfile; return;
    }
    if(page==='recharges'){
      const rows=await api('/api/deposit-history');
      const el=document.getElementById('main');
      el.innerHTML=`<button class="btn btn-success" id="backProfile" type="button">← Back to Profile</button><div class="section-title">💳 Recharge History</div><div class="list">${rows.map(r=>`<div class="row"><div class="row-icon">💳</div><div class="row-main"><div class="row-title">${fmt(r.amount)} • ${esc(r.method_name||'UPI')}</div><div class="row-sub">${esc(r.status||'pending')} • ${esc((r.date||'').slice(0,16))}</div></div><div class="row-price">${esc(String(r.status||'pending'))}</div></div>`).join('')||'<div class="empty">No recharge history yet</div>'}</div>`;
      document.getElementById('backProfile').onclick=renderProfile; return;
    }
    if(page==='referrals'){
      renderRefer(); return;
    }
  }catch(e){toast('❌ '+e.message);}
  finally{loading(false);}
}

/* NAV */
function switchTab(tab){STATE.tab=tab;navButtons();({store:renderStore,deposit:renderDeposit,refer:renderRefer,profile:renderProfile}[tab]||renderStore)();}
document.querySelectorAll('#tabs button').forEach(b=>b.onclick=()=>switchTab(b.dataset.tab));
document.getElementById('brandButton').onclick=()=>switchTab('store');
document.getElementById('balance').onclick=()=>switchTab('deposit');

(async function init(){
  if(!BOT_USERNAME||!tg?.initData){document.getElementById('main').innerHTML='<div class="empty">Open this Mini App from the Telegram bot.</div>';return;}
  loading(true);
  try{await loadConfig();await loadMe();switchTab('store');}
  catch(e){document.getElementById('main').innerHTML=`<div class="empty">Could not start Mini App.<br><br>${esc(e.message)}</div>`;}
  finally{loading(false);}
})();
