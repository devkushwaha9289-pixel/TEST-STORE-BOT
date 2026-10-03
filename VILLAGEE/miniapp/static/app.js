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
function inTg(url){try{tg?.openTelegramLink(url);}catch(e){window.open(url,'_blank','noopener');}}
function openBotWA(){inTg(`https://t.me/${encodeURIComponent(BOT_USERNAME)}?start=AllWhatsapp`);}
async function renderStore(){
  crumbs(null);
  const u=STATE.user, c=STATE.config||{}, f=c.features||{};
  let counts={s2:0,s3:0};
  try{counts=await api('/api/servers');}catch(e){}
  const el=document.getElementById('main');
  const off=(on)=>on?'':' • <b>OFF</b>';
  el.innerHTML=`
    <section class="hero">
      <div class="hello">Hello, ${esc(u?.first_name||'User')} 👋</div>
      <div class="hero-bal">${fmt(u?.balance)}</div>
      <div class="hero-sub">Wallet balance • Ready to shop</div>
    </section>
    <div class="section-title">Quick Actions</div>
    <div class="grid">
      <button class="card" data-go="deposit" type="button"><div class="card-icon">＋</div><div class="card-title">Recharge</div><div class="card-sub">Paytm / FamPay / Manual UPI</div></button>
      <button class="card" data-go="profile" type="button"><div class="card-icon">◉</div><div class="card-title">My Profile</div><div class="card-sub">History & account</div></button>
      <button class="card" data-go="refer" type="button"><div class="card-icon">↗</div><div class="card-title">Refer</div><div class="card-sub">Share & earn</div></button>
      <button class="card" data-action="redeem" type="button"><div class="card-icon">🎁</div><div class="card-title">Redeem</div><div class="card-sub">Coupon code</div></button>
      <button class="card" data-action="transfer" type="button"><div class="card-icon">💸</div><div class="card-title">Send Balance</div><div class="card-sub">Transfer to a user</div></button>
      <button class="card" data-action="support" type="button"><div class="card-icon">🆘</div><div class="card-title">Support</div><div class="card-sub">Contact admin</div></button>
      ${c.is_admin?`<button class="card" data-action="admin" type="button"><div class="card-icon">🔐</div><div class="card-title">Admin Panel</div><div class="card-sub">Manage store</div></button>`:''}
    </div>
    <div class="section-title">Marketplace</div>
    <div class="grid">
      <button class="card big" data-action="server1" type="button">
        <div class="card-icon">🌐</div><div class="card-title">SERVER 1</div>
        <div class="card-sub">Live external market • opens in Telegram bot${off(f.server1)}</div>
      </button>
      <button class="card big" data-srv="s2" type="button">
        <div class="card-icon">📱</div><div class="card-title">SERVER 2</div>
        <div class="card-sub">Telegram account stock • ${Number(counts.s2?.count||0)} available${off(f.server2)}</div>
      </button>
      <button class="card big" data-srv="s3" type="button">
        <div class="card-icon">▤</div><div class="card-title">SERVER 3</div>
        <div class="card-sub">Files, panels & OSINT APIs • ${Number(counts.s3?.count||0)} available${off(f.server3)}</div>
      </button>
      <button class="card big" data-action="wa" type="button">
        <div class="card-icon">🟢</div><div class="card-title">WHATSAPP (4)</div>
        <div class="card-sub">${f.whatsapp?'Active • opens in Telegram bot':'Coming soon'}</div>
      </button>
    </div>
    <div class="note">Purchases use your wallet balance. Recharge first if your balance is low. Server 1 and WhatsApp run through live external APIs, so they open inside the Telegram bot.</div>`;
  el.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>go(b.dataset.go));
  el.querySelectorAll('[data-srv]').forEach(b=>b.onclick=()=>{
    const key=b.dataset.srv==='s2'?'server2':'server3';
    if(!f[key]){toast('This server is currently disabled');return;}
    openServer(b.dataset.srv);
  });
  const act={server1:openBotServer1,wa:()=>f.whatsapp?openBotWA():toast('🔔 WhatsApp is coming soon'),
    redeem:renderRedeem,transfer:renderTransfer,admin:renderAdmin,
    support:()=>renderSupport()};
  el.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>act[b.dataset.action]());
}

function renderSupport(){
  crumbs(['Support']);
  const c=STATE.config||{};
  document.getElementById('main').innerHTML=`<div class="section-title">🆘 Support</div>
    <div class="detail"><div class="detail-rows">
      <div><span>Contact</span><b>${esc(c.contact_1||'—')}</b></div>
      <div><span>Updates</span><b>${esc(c.contact_2||'—')}</b></div></div>
      <button class="btn btn-primary" id="contactAdmin" type="button">Contact Admin</button>
      <button class="btn btn-success" id="backHome" type="button">← Back</button></div>`;
  document.getElementById('contactAdmin').onclick=()=>inTg(c.support_url||`https://t.me/${BOT_USERNAME}`);
  document.getElementById('backHome').onclick=()=>go('store');
}

/* REDEEM */
function renderRedeem(){
  crumbs(['Redeem']);
  document.getElementById('main').innerHTML=`<div class="section-title">🎁 Redeem Coupon</div>
    <div class="deposit-box"><label for="coupon">Coupon code</label>
    <input id="coupon" type="text" autocomplete="off" autocapitalize="characters" placeholder="Enter code">
    <button class="btn btn-primary" id="redeemBtn" type="button">Redeem</button></div>`;
  document.getElementById('redeemBtn').onclick=async()=>{
    const code=document.getElementById('coupon').value.trim();
    if(!code){toast('Enter a coupon code');return;}
    loading(true);
    try{const r=await api('/api/redeem',{method:'POST',body:JSON.stringify({code})});
      await loadMe();toast('🎉 '+r.message);go('store');}
    catch(e){toast('❌ '+e.message);}finally{loading(false);}
  };
}

/* TRANSFER */
function renderTransfer(){
  crumbs(['Send Balance']);
  const fee=Number(STATE.config?.transfer_fee||0);
  document.getElementById('main').innerHTML=`<div class="section-title">💸 Send Balance</div>
    <div class="deposit-box"><label for="trUid">Receiver Telegram ID</label>
    <input id="trUid" type="number" inputmode="numeric" placeholder="e.g. 123456789">
    <button class="btn btn-success" id="trLookup" type="button">Find user</button>
    <div id="trStep"></div></div>
    <div class="note">Transfer fee: ${fee}% • Minimum ₹10 • Your balance: ${fmt(STATE.user?.balance)}</div>`;
  document.getElementById('trLookup').onclick=async()=>{
    const to=Number(document.getElementById('trUid').value);
    if(!to){toast('Enter receiver ID');return;}
    loading(true);
    try{
      const r=await api('/api/transfer/lookup',{method:'POST',body:JSON.stringify({to_uid:to})});
      document.getElementById('trStep').innerHTML=`<div class="verify-box"><div class="verify-title">${esc(r.name)} ${r.username?'(@'+esc(r.username)+')':''}</div>
        <div class="verify-hint">ID ${esc(r.user_id)} • fee ${r.fee_percent}%</div>
        <label class="verify-label" for="trAmt">Amount (₹)</label>
        <input id="trAmt" class="verify-input" type="number" inputmode="numeric" min="10" placeholder="Min ₹10">
        <button class="btn btn-primary" id="trSend" type="button">Send</button></div>`;
      document.getElementById('trSend').onclick=async()=>{
        const amount=Math.floor(Number(document.getElementById('trAmt').value));
        if(!amount||amount<10){toast('Minimum ₹10');return;}
        if(!confirm(`Send ₹${amount} to ${r.name}?`))return;
        loading(true);
        try{const x=await api('/api/transfer',{method:'POST',body:JSON.stringify({to_uid:to,amount})});
          await loadMe();toast('✅ '+x.message);go('store');}
        catch(e){toast('❌ '+e.message);}finally{loading(false);}
      };
    }catch(e){toast('❌ '+e.message);}finally{loading(false);}
  };
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
  clearInterval(STATE.paymentTimer);
  crumbs(null); const c=STATE.config||{}, f=c.features||{}; const el=document.getElementById('main');
  const methods=[
    f.paytm&&['paytm','💳','Paytm Auto','Auto-verified via Paytm API'],
    f.fampay&&['auto','⚡','FamPay Auto','Auto / UTR verification'],
    f.manual&&['manual','▤','UPI Manual','UTR + admin approval'],
  ].filter(Boolean);
  el.innerHTML=`<div class="section-title">Wallet</div><div class="hero wallet-hero"><div class="hello">Available balance</div><div class="hero-bal">${fmt(STATE.user?.balance)}</div><div class="hero-sub">Minimum recharge ${fmt(c.min_deposit)}</div></div>
    <div class="section-title">Recharge Amount</div><div class="deposit-box"><label for="depAmt">Amount in INR</label><input id="depAmt" type="number" min="${Number(c.min_deposit||1)}" inputmode="numeric" placeholder="Minimum ₹${Number(c.min_deposit||1)}"><div class="quick">${[50,100,200,500,1000].map(v=>`<button type="button" data-v="${v}">₹${v}</button>`).join('')}</div></div>
    <div class="section-title">Payment Method</div>
    <div class="grid">${methods.map(m=>`<button class="card" data-method="${m[0]}" type="button"><div class="card-icon">${m[1]}</div><div class="card-title">${m[2]}</div><div class="card-sub">${m[3]}</div></button>`).join('')||'<div class="empty" style="grid-column:1/-1">Recharge is currently disabled</div>'}</div>
    <div id="depResult"></div>`;
  const amt=el.querySelector('#depAmt');el.querySelectorAll('.quick button').forEach(b=>b.onclick=()=>amt.value=b.dataset.v);
  el.querySelectorAll('[data-method]').forEach(b=>b.onclick=()=>makeDeposit(b.dataset.method,Number(amt.value||0)));
}
async function makeDeposit(method,amount){
  const min=Number(STATE.config?.min_deposit||1); if(!Number.isFinite(amount)||amount<min){toast(`Minimum ${fmt(min)}`);return;}
  loading(true);
  try{
    const r=await api(`/api/deposit/${method}`,{method:'POST',body:JSON.stringify({amount:Math.floor(amount)})});
    const qr=`https://api.qrserver.com/v1/create-qr-code/?size=320x320&margin=8&data=${encodeURIComponent(r.upi_url)}`;
    const isPaytm=r.provider==='paytm', isManual=r.provider==='manual';
    const badge=isPaytm?'PAYTM AUTOMATIC':isManual?'MANUAL UPI PAYMENT':'FAMPAY AUTOMATIC';
    const sub=isPaytm?'Scan QR • Pay exact amount • Auto credit':isManual?'Scan QR • Pay exact amount • Submit UTR':'Scan QR • Pay exact amount • Submit UTR/TXN';
    let verify='';
    if(isPaytm){
      verify=`<div class="verify-box"><div class="verify-title">Automatic verification</div><div class="verify-hint">No UTR needed. Your balance is credited automatically within seconds of payment. Order stays valid for 15 minutes.</div><button class="btn btn-success" id="paytmCheck" type="button">Check payment now</button><div id="paymentStatus"></div></div>`;
    }else if(isManual){
      verify=`<div class="verify-box"><div class="verify-title">Submit UTR</div><div class="verify-hint">After paying, enter the UTR / reference number. Admin will approve your payment.</div><label class="verify-label" for="paymentReference">UTR / Reference No.</label><input id="paymentReference" class="verify-input" type="text" autocomplete="off" spellcheck="false" placeholder="12-digit UTR"><button class="btn btn-success" id="manualSubmit" type="button">Submit for approval</button><div id="paymentStatus"></div></div>`;
    }else{
      verify=`<div class="verify-box"><div class="verify-title">Payment Verification</div><div class="verify-hint">Enter 12-digit numeric UTR, or Transaction ID (TXN). Amount is taken from this order automatically. Payments are also auto-detected.</div><label class="verify-label" for="paymentReference">UTR / Transaction ID (TXN)</label><input id="paymentReference" class="verify-input" type="text" autocomplete="off" spellcheck="false" placeholder="12-digit UTR or FMPIB..."><button class="btn btn-success" id="verifyPayment" type="button">Submit & Verify</button><div id="paymentStatus"></div></div>`;
    }
    document.getElementById('depResult').innerHTML=`<div class="rainbow-pay-card"><div class="pay-badge">${badge}</div><div class="pay-title">Pay ${fmt(r.amount)}</div><div class="pay-subtitle">${sub}</div><div class="qr-frame"><div class="qr-frame-inner"><img class="qr" src="${qr}" alt="UPI payment QR"></div></div><div class="upi-id">UPI ID: <b>${esc(r.upi_id)}</b></div><div class="payment-meta"><div><span>Amount</span><b>${fmt(r.amount)}</b></div><div><span>Order</span><code>${esc(r.order_id)}</code></div></div><a class="btn btn-primary" href="${esc(r.upi_url)}">Open UPI app</a><button class="btn btn-success" id="copyUpi" type="button">Copy UPI ID</button><button class="btn btn-success" id="downloadQr" type="button">Download QR</button>${verify}</div>`;
    document.getElementById('downloadQr').onclick=()=>downloadQR(qr,r.order_id);
    document.getElementById('copyUpi').onclick=async()=>{try{await navigator.clipboard.writeText(r.upi_id);toast('✅ UPI ID copied');}catch(e){toast(r.upi_id);}};
    if(isPaytm){document.getElementById('paytmCheck').onclick=()=>checkPaytm(r.order_id);}
    else if(isManual){document.getElementById('manualSubmit').onclick=()=>submitManual(r.order_id);}
    else{document.getElementById('verifyPayment').onclick=()=>verifyPayment(r.order_id);}
    renderPaymentStatus(r.order_id);
    if(r.poll) pollPayment(r.order_id);
    document.getElementById('depResult').scrollIntoView({behavior:'smooth',block:'start'});
  }catch(e){toast('❌ '+e.message);}finally{loading(false);}
}
async function downloadQR(url,oid){try{const r=await fetch(url);if(!r.ok)throw 0;const blob=await r.blob();const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=`VILLAGEE_QR_${oid}.png`;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1000);}catch(e){window.open(url,'_blank','noopener');}}
async function checkPaytm(oid){
  const btn=document.getElementById('paytmCheck'); if(btn){btn.disabled=true;btn.textContent='Checking…';}
  try{
    const r=await api('/api/paytm/check',{method:'POST',body:JSON.stringify({order_id:oid})});
    if(r.status==='success'){await loadMe();setBalance();toast('✅ Balance credited');}
    else if(r.status==='mismatch'){toast('⚠️ Amount mismatch. Not credited. Contact support.');}
    else{toast('⏳ Paytm has not confirmed this payment yet');}
    renderPaymentStatus(oid);
  }catch(e){toast('❌ '+e.message);}
  finally{if(btn){btn.disabled=false;btn.textContent='Check payment now';}}
}
async function submitManual(oid){
  const raw=(document.getElementById('paymentReference')?.value||'').trim();
  const clean=raw.replace(/[^A-Za-z0-9]/g,'').toUpperCase();
  if(clean.length<4){toast('Enter a valid UTR');return;}
  const btn=document.getElementById('manualSubmit'); if(btn){btn.disabled=true;btn.textContent='Submitting…';}
  try{
    const r=await api('/api/deposit/manual/submit',{method:'POST',body:JSON.stringify({order_id:oid,utr:clean})});
    toast('✅ '+(r.message||'Submitted'));
    const st=document.getElementById('paymentStatus');
    if(st){st.className='payment-status waiting';st.innerHTML='<div><span class="status-dot"></span>Submitted. Waiting for admin approval…</div>';}
    pollPayment(oid);
  }catch(e){toast('❌ '+e.message);}
  finally{if(btn){btn.disabled=false;btn.textContent='Submit for approval';}}
}
async function verifyPayment(oid){
  const reference=(document.getElementById('paymentReference')?.value||'').trim();
  const btn=document.getElementById('verifyPayment');
  if(!reference){toast('Enter UTR or Transaction ID');return;}
  const clean=reference.replace(/[^A-Za-z0-9]/g,'').toUpperCase();
  if(/^\d+$/.test(clean) && clean.length!==12){toast('UTR must be exactly 12 digits');return;}
  if(!/^\d{12}$/.test(clean) && clean.length<6){toast('Enter a valid Transaction ID');return;}
  if(btn){btn.disabled=true;btn.textContent='Checking…';}
  try{
    const r=await api('/api/verify-payment',{method:'POST',body:JSON.stringify({order_id:oid,reference:clean})});
    renderPaymentStatus(oid); toast(r.message||'Submitted');
    if(r.status==='success'){await loadMe();}
  }catch(e){toast('❌ '+e.message);renderPaymentStatus(oid);}
  finally{if(btn){btn.disabled=false;btn.textContent='Submit & Verify';}}
}
const PAY_LABELS={pending:'Waiting for payment',manual_pending:'Waiting for UTR / admin approval',success:'Payment credited',expired:'Order expired',failed:'Payment failed',mismatch:'Amount mismatch — contact support',duplicate:'Duplicate payment reference',manual_rejected:'Rejected by admin',superseded:'Replaced by a newer order'};
async function renderPaymentStatus(oid){const el=document.getElementById('paymentStatus');if(!el)return;try{const r=await api(`/api/order/${encodeURIComponent(oid)}`);const ok=r.status==='success';el.className=`payment-status ${ok?'success':'waiting'}`;el.innerHTML=`<div><span class="status-dot"></span>${esc(PAY_LABELS[r.status]||('Status: '+r.status))}</div>`;}catch(e){}}
function pollPayment(oid){
  clearInterval(STATE.paymentTimer);let n=0;
  STATE.paymentTimer=setInterval(async()=>{
    n++;if(n>180){clearInterval(STATE.paymentTimer);return;}
    try{
      const r=await api(`/api/order/${encodeURIComponent(oid)}`);
      if(r.status==='success'){clearInterval(STATE.paymentTimer);await loadMe();renderPaymentStatus(oid);toast('✅ Balance credited');}
      else if(['expired','failed','mismatch','duplicate','manual_rejected','superseded'].includes(r.status)){clearInterval(STATE.paymentTimer);renderPaymentStatus(oid);}
      else{renderPaymentStatus(oid);}
    }catch(e){}
  },5000);
}

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
      <button class="row" data-profile-page="balance" type="button"><div class="row-icon">💼</div><div class="row-main"><div class="row-title">Balance History</div><div class="row-sub">Every credit and debit on your wallet</div></div><div class="row-arrow">›</div></button>
      <button class="row" data-profile-page="recharges" type="button"><div class="row-icon">💳</div><div class="row-main"><div class="row-title">Recharge History</div><div class="row-sub">UPI auto/manual recharge records</div></div><div class="row-arrow">›</div></button>
      <button class="row" data-profile-page="referrals" type="button"><div class="row-icon">👥</div><div class="row-main"><div class="row-title">Referral History</div><div class="row-sub">People referred and referral earnings</div></div><div class="row-arrow">›</div></button>
    </div>
    <div class="section-title">Terms & Policies</div>
    <div class="list">
      <button class="row" data-profile-page="terms" type="button"><div class="row-icon">📄</div><div class="row-main"><div class="row-title">Terms & Conditions</div><div class="row-sub">Rules for using VILLAGEE SMS SHOP</div></div><div class="row-arrow">›</div></button>
      <button class="row" data-profile-page="refund" type="button"><div class="row-icon">🚫</div><div class="row-main"><div class="row-title">Refund Policy</div><div class="row-sub">All purchases are final — no refund</div></div><div class="row-arrow">›</div></button>
      <button class="row" data-profile-page="privacy" type="button"><div class="row-icon">🛡️</div><div class="row-main"><div class="row-title">Privacy Policy</div><div class="row-sub">How account and order information is used</div></div><div class="row-arrow">›</div></button>
    </div>
    <div class="section-title">Wallet Tools</div>
    <div class="list">
      <button class="row" id="toRedeem" type="button"><div class="row-icon">🎁</div><div class="row-main"><div class="row-title">Redeem Coupon</div><div class="row-sub">Add balance with a code</div></div><div class="row-arrow">›</div></button>
      <button class="row" id="toTransfer" type="button"><div class="row-icon">💸</div><div class="row-main"><div class="row-title">Send Balance</div><div class="row-sub">Transfer to another user</div></div><div class="row-arrow">›</div></button>
      ${STATE.config?.is_admin?`<button class="row" id="toAdmin" type="button"><div class="row-icon">🔐</div><div class="row-main"><div class="row-title">Admin Panel</div><div class="row-sub">Manage payments, users & products</div></div><div class="row-arrow">›</div></button>`:''}
    </div>
    <div class="section-title">Support</div>
    <button class="row" id="openSupport" type="button"><div class="row-icon">❓</div><div class="row-main"><div class="row-title">Help & Support</div><div class="row-sub">Open support in Telegram</div></div><div class="row-arrow">›</div></button>`;
  el.querySelectorAll('[data-profile-page]').forEach(b=>b.onclick=()=>openProfilePage(b.dataset.profilePage));
  document.getElementById('toRedeem').onclick=renderRedeem;
  document.getElementById('toTransfer').onclick=renderTransfer;
  const _ta=document.getElementById('toAdmin'); if(_ta) _ta.onclick=renderAdmin;
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
    if(page==='balance'){
      const rows=await api('/api/balance-history');
      const el=document.getElementById('main');
      el.innerHTML=`<button class="btn btn-success" id="backProfile" type="button">← Back to Profile</button><div class="section-title">💼 Balance History</div><div class="list">${rows.map(r=>{const amt=Number(r.amount||0);return `<div class="row"><div class="row-icon">${amt>=0?'➕':'➖'}</div><div class="row-main"><div class="row-title">${esc(r.action||r.type||'wallet')} ${r.note?'• '+esc(r.note):''}</div><div class="row-sub">${esc((r.date||r.created_at||'').slice(0,16))}${r.new_balance!=null?' • bal '+fmt(r.new_balance):''}</div></div><div class="row-price">${amt>=0?'+':''}${fmt(amt)}</div></div>`}).join('')||'<div class="empty">No balance history yet</div>'}</div>`;
      document.getElementById('backProfile').onclick=renderProfile; return;
    }
    if(page==='referrals'){
      renderRefer(); return;
    }
  }catch(e){toast('❌ '+e.message);}
  finally{loading(false);}
}

/* ADMIN PANEL */
const PAY_LABEL={fampay_upi_id:'FamPay UPI',paytm_upi_id:'Paytm UPI',paytm_mid:'Paytm MID',manual_upi_id:'Manual UPI'};
const SET_LABEL={min_deposit:'Min deposit (₹)',usdt_rate:'USDT rate (₹)',transfer_fee:'Transfer fee (%)',support_url:'Support URL',contact_1:'Contact 1',contact_2:'Contact 2'};
function adminBack(fn){const b=document.getElementById('admBack');if(b)b.onclick=fn||renderAdmin;}
function admHead(title,back){return `<button class="btn btn-success" id="admBack" type="button">← ${back||'Admin Panel'}</button><div class="section-title">${title}</div>`;}
async function admCall(path,body){return api(path,{method:'POST',body:JSON.stringify(body||{})});}

async function renderAdmin(){
  if(!STATE.config?.is_admin){toast('Admin only');return;}
  crumbs(['Admin']); loading(true);
  try{
    const o=await api('/api/admin/overview'); const st=o.stats||{};
    const el=document.getElementById('main');
    el.innerHTML=`<div class="section-title">🔐 Admin Panel</div>
      <div class="stats">
        <div class="stat"><div class="s-val">${st.users}</div><div class="s-lbl">Users</div></div>
        <div class="stat"><div class="s-val">${fmt(st.balance_total)}</div><div class="s-lbl">Wallet total</div></div>
        <div class="stat"><div class="s-val">${st.orders}</div><div class="s-lbl">Orders</div></div>
        <div class="stat"><div class="s-val">${fmt(st.revenue)}</div><div class="s-lbl">Revenue</div></div>
        <div class="stat"><div class="s-val">${st.stock_s2}</div><div class="s-lbl">S2 stock</div></div>
        <div class="stat"><div class="s-val">${st.manual_pending}</div><div class="s-lbl">Pending manual</div></div>
      </div>
      <div class="section-title">Switches</div>
      <div class="list">${o.toggles.map(t=>`<div class="row"><div class="row-icon">${t.on?'🟢':'🔴'}</div><div class="row-main"><div class="row-title">${esc(t.label)}</div><div class="row-sub">${t.on?'ON':'OFF'}</div></div><button class="mini-btn ${t.on?'on':'off'}" data-toggle="${esc(t.key)}" type="button">${t.on?'Turn OFF':'Turn ON'}</button></div>`).join('')}</div>
      <div class="section-title">Manage</div>
      <div class="list">
        <button class="row" data-adm="payments" type="button"><div class="row-icon">💳</div><div class="row-main"><div class="row-title">Payment IDs</div><div class="row-sub">Paytm UPI / MID, FamPay UPI, Manual UPI</div></div><div class="row-arrow">›</div></button>
        <button class="row" data-adm="manual" type="button"><div class="row-icon">📄</div><div class="row-main"><div class="row-title">Manual Payments</div><div class="row-sub">${st.manual_pending} waiting for approval</div></div><div class="row-arrow">›</div></button>
        <button class="row" data-adm="users" type="button"><div class="row-icon">👤</div><div class="row-main"><div class="row-title">Users</div><div class="row-sub">Find, balance, ban / unban</div></div><div class="row-arrow">›</div></button>
        <button class="row" data-adm="settings" type="button"><div class="row-icon">⚙️</div><div class="row-main"><div class="row-title">Store Settings</div><div class="row-sub">Min deposit, rate, fee, support</div></div><div class="row-arrow">›</div></button>
        <button class="row" data-adm="coupons" type="button"><div class="row-icon">🎁</div><div class="row-main"><div class="row-title">Coupons</div><div class="row-sub">Create and delete codes</div></div><div class="row-arrow">›</div></button>
        <button class="row" data-adm="products" type="button"><div class="row-icon">▤</div><div class="row-main"><div class="row-title">Server 3 Products</div><div class="row-sub">Price, active, delete</div></div><div class="row-arrow">›</div></button>
        <button class="row" data-adm="stock" type="button"><div class="row-icon">📱</div><div class="row-main"><div class="row-title">Server 2 Stock</div><div class="row-sub">View stock and set prices</div></div><div class="row-arrow">›</div></button>
        <button class="row" data-adm="broadcast" type="button"><div class="row-icon">📣</div><div class="row-main"><div class="row-title">Broadcast</div><div class="row-sub">Message all users</div></div><div class="row-arrow">›</div></button>
      </div>
      <div class="note">Bulk stock upload, ZIP import, bot management and backups stay in the Telegram admin panel because they need file uploads.</div>`;
    el.querySelectorAll('[data-toggle]').forEach(b=>b.onclick=async()=>{
      loading(true);try{const r=await admCall('/api/admin/toggle',{key:b.dataset.toggle});toast(r.on?'✅ Turned ON':'⛔ Turned OFF');await loadConfig();renderAdmin();}
      catch(e){toast('❌ '+e.message);}finally{loading(false);}
    });
    const pages={payments:admPayments,manual:admManual,users:admUsers,settings:admSettings,coupons:admCoupons,products:admProducts,stock:admStock,broadcast:admBroadcast};
    el.querySelectorAll('[data-adm]').forEach(b=>b.onclick=()=>pages[b.dataset.adm](o));
  }catch(e){toast('❌ '+e.message);}finally{loading(false);}
}

function admEditor(title,fields,values,labels,path,after){
  const el=document.getElementById('main');
  el.innerHTML=admHead(title)+`<div class="deposit-box">${fields.map(k=>`<label for="f_${k}">${esc(labels[k]||k)}</label><input id="f_${k}" data-k="${k}" type="text" autocomplete="off" spellcheck="false" value="${esc(values[k]||'')}" style="margin-bottom:10px"><button class="btn btn-primary" data-save="${k}" type="button" style="margin-top:0;margin-bottom:14px">Save ${esc(labels[k]||k)}</button>`).join('')}</div>`;
  adminBack();
  el.querySelectorAll('[data-save]').forEach(b=>b.onclick=async()=>{
    const k=b.dataset.save; const v=document.getElementById('f_'+k).value.trim();
    loading(true);try{await admCall(path,{key:k,value:v});toast('✅ Saved');if(after)await after();}
    catch(e){toast('❌ '+e.message);}finally{loading(false);}
  });
}
function admPayments(o){admEditor('💳 Payment IDs',['paytm_upi_id','paytm_mid','fampay_upi_id','manual_upi_id'],o.payment,PAY_LABEL,'/api/admin/payment',loadConfig);}
function admSettings(o){admEditor('⚙️ Store Settings',['min_deposit','usdt_rate','transfer_fee','support_url','contact_1','contact_2'],o.settings,SET_LABEL,'/api/admin/setting',loadConfig);}

async function admManual(){
  loading(true);
  try{
    const rows=await api('/api/admin/manual'); const el=document.getElementById('main');
    el.innerHTML=admHead('📄 Manual Payments')+`<div class="list">${rows.map(r=>`<div class="detail" style="margin-bottom:10px"><div class="detail-rows">
      <div><span>User</span><b>${esc(r.first_name||'User')} ${r.username?'@'+esc(r.username):''} (${esc(r.user_id)})</b></div>
      <div><span>Amount</span><b>${fmt(r.amount)}</b></div><div><span>UTR</span><b>${esc(r.utr||'—')}</b></div>
      <div><span>Order</span><b>${esc(r.order_id)}</b></div></div>
      <button class="btn btn-primary" data-ap="${esc(r.order_id)}" type="button">✅ Approve</button>
      <button class="btn btn-success" data-rj="${esc(r.order_id)}" type="button">❌ Reject</button></div>`).join('')||'<div class="empty">No payments waiting</div>'}</div>`;
    adminBack();
    const decide=async(oid,action)=>{
      let reason='';
      if(action==='reject'){reason=prompt('Reject reason (optional)')||'';}
      else if(!confirm('Approve and credit this payment?'))return;
      loading(true);try{await admCall('/api/admin/manual/decide',{order_id:oid,action,reason});toast('✅ Done');admManual();}
      catch(e){toast('❌ '+e.message);}finally{loading(false);}
    };
    el.querySelectorAll('[data-ap]').forEach(b=>b.onclick=()=>decide(b.dataset.ap,'approve'));
    el.querySelectorAll('[data-rj]').forEach(b=>b.onclick=()=>decide(b.dataset.rj,'reject'));
  }catch(e){toast('❌ '+e.message);}finally{loading(false);}
}

function admUsers(){
  const el=document.getElementById('main');
  el.innerHTML=admHead('👤 Users')+`<div class="deposit-box"><label for="uSearch">User ID or @username</label><input id="uSearch" type="text" autocomplete="off" placeholder="123456789 or @name"><button class="btn btn-primary" id="uFind" type="button">Find user</button></div><div id="uBox"></div>`;
  adminBack();
  const find=async()=>{
    const t=document.getElementById('uSearch').value.trim(); if(!t){toast('Enter ID or username');return;}
    loading(true);
    try{
      const u=await admCall('/api/admin/user',{target:t});
      document.getElementById('uBox').innerHTML=`<div class="detail" style="margin-top:12px"><div class="detail-title">${esc(((u.first_name||'')+' '+(u.last_name||'')).trim()||'User')}</div>
        <div class="detail-rows" style="margin-top:12px">
        <div><span>ID</span><b>${esc(u.user_id)}</b></div><div><span>Username</span><b>${u.username?'@'+esc(u.username):'—'}</b></div>
        <div><span>Balance</span><b>${fmt(u.balance)}</b></div><div><span>Deposited</span><b>${fmt(u.total_deposited)}</b></div>
        <div><span>Purchases</span><b>${Number(u.total_purchases||0)}</b></div><div><span>Status</span><b>${u.banned?'🚫 Banned':'✅ Active'}</b></div></div>
        <label class="verify-label" for="uAmt" style="display:block;margin-top:12px;font-size:11px;color:#888b95;font-weight:800">Amount (₹)</label>
        <input id="uAmt" class="verify-input" type="number" inputmode="numeric" placeholder="Amount">
        <button class="btn btn-primary" id="uAdd" type="button">➕ Add balance</button>
        <button class="btn btn-success" id="uDed" type="button">➖ Deduct balance</button>
        <button class="btn btn-success" id="uBan" type="button">${u.banned?'✅ Unban user':'🚫 Ban user'}</button></div>`;
      const bal=async(mode)=>{
        const amount=Math.floor(Number(document.getElementById('uAmt').value)); if(!amount||amount<=0){toast('Enter amount');return;}
        if(!confirm(`${mode==='add'?'Add':'Deduct'} ₹${amount}?`))return;
        loading(true);try{const r=await admCall('/api/admin/balance',{user_id:Number(u.user_id),amount,mode});toast(`✅ ${fmt(r.old)} → ${fmt(r.new)}`);find();}
        catch(e){toast('❌ '+e.message);}finally{loading(false);}
      };
      document.getElementById('uAdd').onclick=()=>bal('add');
      document.getElementById('uDed').onclick=()=>bal('deduct');
      document.getElementById('uBan').onclick=async()=>{
        loading(true);try{await admCall('/api/admin/ban',{user_id:Number(u.user_id),banned:!u.banned});toast('✅ Updated');find();}
        catch(e){toast('❌ '+e.message);}finally{loading(false);}
      };
    }catch(e){toast('❌ '+e.message);document.getElementById('uBox').innerHTML='';}finally{loading(false);}
  };
  document.getElementById('uFind').onclick=find;
}

async function admCoupons(){
  loading(true);
  try{
    const rows=await api('/api/admin/coupons'); const el=document.getElementById('main');
    el.innerHTML=admHead('🎁 Coupons')+`<div class="deposit-box"><label for="cCode">New coupon</label><input id="cCode" type="text" autocapitalize="characters" placeholder="CODE" style="margin-bottom:8px"><input id="cAmt" type="number" inputmode="numeric" placeholder="Amount ₹" style="margin-bottom:8px"><input id="cMax" type="number" inputmode="numeric" placeholder="Max uses"><button class="btn btn-primary" id="cAdd" type="button">Create coupon</button></div>
      <div class="section-title">All coupons</div><div class="list">${rows.map(c=>`<div class="row"><div class="row-icon">🎁</div><div class="row-main"><div class="row-title">${esc(c.code)} • ${fmt(c.amount)}</div><div class="row-sub">Used ${c.used}/${c.max_uses} • ${c.active?'active':'inactive'}</div></div><button class="mini-btn off" data-del="${esc(c.code)}" type="button">Delete</button></div>`).join('')||'<div class="empty">No coupons</div>'}</div>`;
    adminBack();
    document.getElementById('cAdd').onclick=async()=>{
      const code=document.getElementById('cCode').value.trim(),amount=Number(document.getElementById('cAmt').value),max_uses=Number(document.getElementById('cMax').value);
      if(!code||!amount||!max_uses){toast('Fill code, amount and max uses');return;}
      loading(true);try{await admCall('/api/admin/coupons/add',{code,amount,max_uses});toast('✅ Created');admCoupons();}
      catch(e){toast('❌ '+e.message);}finally{loading(false);}
    };
    el.querySelectorAll('[data-del]').forEach(b=>b.onclick=async()=>{
      if(!confirm('Delete coupon '+b.dataset.del+'?'))return;
      loading(true);try{await admCall('/api/admin/coupons/delete',{code:b.dataset.del});toast('🗑️ Deleted');admCoupons();}
      catch(e){toast('❌ '+e.message);}finally{loading(false);}
    });
  }catch(e){toast('❌ '+e.message);}finally{loading(false);}
}

async function admProducts(){
  loading(true);
  try{
    const rows=await api('/api/admin/products'); const el=document.getElementById('main');
    el.innerHTML=admHead('▤ Server 3 Products')+`<div class="list">${rows.map(p=>`<div class="detail" style="margin-bottom:10px;padding:13px"><div class="row-title" style="white-space:normal">${esc(p.name)}</div><div class="row-sub" style="white-space:normal">${esc(p.section)} • ID ${p.id} • ${fmt(p.price)} • ${p.active?'🟢 active':'🔴 inactive'}</div>
      <div class="admin-actions"><button class="mini-btn on" data-pr="${p.id}" data-a="price" type="button">Price</button><button class="mini-btn on" data-pr="${p.id}" data-a="toggle" type="button">${p.active?'Deactivate':'Activate'}</button><button class="mini-btn off" data-pr="${p.id}" data-a="delete" type="button">Delete</button></div></div>`).join('')||'<div class="empty">No products</div>'}</div>`;
    adminBack();
    el.querySelectorAll('[data-pr]').forEach(b=>b.onclick=async()=>{
      const a=b.dataset.a; let value=null;
      if(a==='price'){value=prompt('New price (₹)');if(value===null)return;}
      if(a==='delete'&&!confirm('Delete this product permanently?'))return;
      loading(true);try{await admCall('/api/admin/products/update',{id:Number(b.dataset.pr),action:a,value});toast('✅ Done');admProducts();}
      catch(e){toast('❌ '+e.message);}finally{loading(false);}
    });
  }catch(e){toast('❌ '+e.message);}finally{loading(false);}
}

async function admStock(){
  loading(true);
  try{
    const rows=await api('/api/admin/stock'); const el=document.getElementById('main');
    el.innerHTML=admHead('📱 Server 2 Stock')+`<div class="list">${rows.map((r,i)=>`<div class="row"><div class="row-icon">${esc(r.country_icon||'🌍')}</div><div class="row-main"><div class="row-title">${esc(r.country_name)}</div><div class="row-sub">${esc(r.category)} • ${r.n} available • from ${fmt(r.min_price)}</div></div><button class="mini-btn on" data-i="${i}" type="button">Set price</button></div>`).join('')||'<div class="empty">No stock</div>'}</div>`;
    adminBack();
    el.querySelectorAll('[data-i]').forEach(b=>b.onclick=async()=>{
      const r=rows[Number(b.dataset.i)]; const v=prompt(`New price for ALL ${r.country_name} (${r.category}) accounts (₹)`,r.min_price); if(v===null)return;
      loading(true);try{const x=await admCall('/api/admin/stock/price',{category:r.category,country:r.country_name,price:Number(v)});toast(`✅ ${x.updated} updated`);admStock();}
      catch(e){toast('❌ '+e.message);}finally{loading(false);}
    });
  }catch(e){toast('❌ '+e.message);}finally{loading(false);}
}

function admBroadcast(){
  const el=document.getElementById('main');
  el.innerHTML=admHead('📣 Broadcast')+`<div class="deposit-box"><label for="bcText">Message (HTML allowed: &lt;b&gt;, &lt;i&gt;, &lt;code&gt;)</label><textarea id="bcText" rows="6" placeholder="Write your message…"></textarea><button class="btn btn-primary" id="bcSend" type="button">Send to all users</button></div><div class="note">Sent in the background. You will get a summary in Telegram when it finishes.</div>`;
  adminBack();
  document.getElementById('bcSend').onclick=async()=>{
    const text=document.getElementById('bcText').value.trim(); if(!text){toast('Message is empty');return;}
    if(!confirm('Send this message to ALL users?'))return;
    loading(true);try{const r=await admCall('/api/admin/broadcast',{text});toast(`📣 Queued for ${r.queued} users`);}
    catch(e){toast('❌ '+e.message);}finally{loading(false);}
  };
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
