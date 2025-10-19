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
  return bubble;
}

function addTypingIndicator() {
  const msg = document.createElement('div');
  msg.className = 'msg bot typing-indicator';
  msg.id = 'typing-indicator';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
  msg.appendChild(bubble);
  messagesEl.appendChild(msg);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return msg;
}

function removeTypingIndicator() {
  const indicator = document.getElementById('typing-indicator');
  if (indicator) indicator.remove();
}

async function typeText(bubble, text, speed = 15) {
  bubble.textContent = '';
  for (let i = 0; i < text.length; i++) {
    bubble.textContent += text[i];
    messagesEl.scrollTop = messagesEl.scrollHeight;
    if (speed > 0) await new Promise(r => setTimeout(r, speed));
  }
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
  const description = l.description || l.description_en || '';
  const descriptionSnippet = description.length > 120 ? description.slice(0, 120) + '...' : description;
  
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
      ${descriptionSnippet ? `<p class="card__description">${descriptionSnippet}</p>` : ''}
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

// Session handling: keep a stable sessionId in localStorage
const SESSION_KEY = 'apartmint_session_id';
function getSessionId() {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

async function sendMessage(text, { reset = false } = {}) {
  addMessage(text, 'user');
  const btn = $('#chat-form button');
  btn.disabled = true;
  
  // Show typing indicator
  const typingIndicator = addTypingIndicator();
  
  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, sessionId: getSessionId(), reset })
    });
    if (!resp.ok) throw new Error('Request failed');
    const data = await resp.json();
    
    // Remove typing indicator and add bot message with typing effect
    removeTypingIndicator();
    const botBubble = addMessage('', 'bot');
    await typeText(botBubble, data.reply || 'Here are some options.', 15);
    
    const prefs = data.preferences || {};
    const results = data.results || [];
    
    // Only show filter summary and cards if we have results
    if (results.length > 0) {
      const parts = [];
      if (prefs.city) parts.push(`near ${prefs.city}`);
      if (prefs.rooms && prefs.maxRooms && prefs.rooms === prefs.maxRooms) {
        parts.push(`exactly ${prefs.rooms} room${prefs.rooms > 1 ? 's' : ''}`);
      } else if (prefs.rooms && prefs.maxRooms) {
        parts.push(`${prefs.rooms}–${prefs.maxRooms} rooms`);
      } else if (prefs.rooms) {
        parts.push(`${prefs.rooms}+ rooms`);
      } else if (prefs.maxRooms) {
        parts.push(`≤ ${prefs.maxRooms} rooms`);
      }
      if (prefs.budget) parts.push(`≤ ${fmt(prefs.budget)} kr/mo`);
      summaryEl.textContent = parts.length ? `Showing results ${parts.join(', ')}` : 'Showing recommended results';
      renderCards(results);
    } else {
      // No results (greeting/help/detail with no match) — clear cards but keep summary friendly
      summaryEl.textContent = 'Ask me anything about apartments!';
      cardsEl.innerHTML = '';
    }
  } catch (e) {
    removeTypingIndicator();
    const errBubble = addMessage('', 'bot');
    await typeText(errBubble, 'Sorry, something went wrong. Please try again.', 15);
  } finally {
    btn.disabled = false;
  }
}$('#chat-form').addEventListener('submit', (e) => {
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

// Optional: add a New Search button dynamically beside the send button
window.addEventListener('DOMContentLoaded', () => {
  const form = $('#chat-form');
  const resetBtn = document.createElement('button');
  resetBtn.type = 'button';
  resetBtn.className = 'btn';
  resetBtn.style.marginLeft = '8px';
  resetBtn.textContent = 'New search';
  resetBtn.addEventListener('click', () => {
    sendMessage('reset', { reset: true });
    addMessage('Starting a new search. Tell me your preferences.', 'bot');
  });
  form.appendChild(resetBtn);
});
