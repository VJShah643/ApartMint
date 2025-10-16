const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));

const messagesEl = document.getElementById('messages');
const cardsEl = document.getElementById('cards');
const summaryEl = document.getElementById('summary');

function addMessage(text, who = 'user') {
  const msg = document.createElement('div');
  msg.className = `msg ${who}`;
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;
  msg.appendChild(bubble);
  messagesEl.appendChild(msg);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function fmt(n) {
  try {
    return new Intl.NumberFormat('sv-SE').format(n);
  } catch {
    return n;
  }
}

function cardTemplate(l) {
  const img = (l.images && l.images.length) ? l.images[0] : null;
  const rent = l.rentNumeric ? `${fmt(l.rentNumeric)} kr/mo` : (l.rent || '');
  const rooms = l.roomsNumeric ? `${l.roomsNumeric} rooms` : (l.rooms || '');
  const size = l.sizeNumeric ? `${l.sizeNumeric} m²` : (l.size || '');
  const city = l.city || '';
  const title = l.title || 'Listing';
  return `
  <article class="card">
    <div class="card__media">${img ? `<img src="${img}" alt="${title}">` : ''}</div>
    <div class="card__body">
      <h3 class="card__title">${title}</h3>
      <div class="pillrow">
        ${rent ? `<span class="pill">${rent}</span>` : ''}
        ${rooms ? `<span class="pill">${rooms}</span>` : ''}
        ${size ? `<span class="pill">${size}</span>` : ''}
      </div>
      <div class="meta">${city ? city + ' · ' : ''}${l.area || ''}</div>
    </div>
    <div class="card__footer">
      <a class="link" href="${l.url}" target="_blank" rel="noopener">Open listing</a>
      <span class="source">${l.source}</span>
    </div>
  </article>`;
}

function renderCards(items) {
  cardsEl.innerHTML = items.map(cardTemplate).join('');
}

async function sendMessage(text) {
  addMessage(text, 'user');
  const btn = $('#chat-form button');
  btn.disabled = true;
  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    });
    if (!resp.ok) throw new Error('Request failed');
    const data = await resp.json();
    addMessage(data.reply || 'Here are some options.', 'bot');
    const prefs = data.preferences || {};
    const parts = [];
    if (prefs.city) parts.push(`near ${prefs.city}`);
    if (prefs.rooms) parts.push(`${prefs.rooms}+ rooms`);
    if (prefs.budget) parts.push(`≤ ${fmt(prefs.budget)} kr/mo`);
    summaryEl.textContent = parts.length ? `Showing results ${parts.join(', ')}` : 'Showing recommended results';
    renderCards(data.results || []);
  } catch (e) {
    addMessage('Sorry, something went wrong. Please try again.', 'bot');
  } finally {
    btn.disabled = false;
  }
}

$('#chat-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const input = $('#message-input');
  const val = input.value.trim();
  if (!val) return;
  sendMessage(val);
  input.value = '';
});

// Initial fetch to populate with some listings
(async function init() {
  try {
    const r = await fetch('/api/listings?limit=6');
    if (r.ok) {
      const d = await r.json();
      renderCards(d.items || []);
      summaryEl.textContent = 'Popular listings right now';
    }
  } catch {}
})();
