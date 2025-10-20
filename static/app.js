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

function formatMarkdown(text) {
  // Convert markdown to HTML for rendering
  return text
    // Bold: **text** -> <strong>text</strong>
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // Bullet points: - item -> <li>item</li>
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    // Wrap consecutive list items in <ul>
    .replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>')
    // Line breaks
    .replace(/\n\n/g, '<br><br>');
}

async function typeText(bubble, text, speed = 15) {
  // Check if text contains markdown formatting
  const hasMarkdown = /\*\*/.test(text) || /^- /m.test(text);
  
  if (hasMarkdown) {
    // For markdown text, convert to HTML first
    const htmlContent = formatMarkdown(text);
    
    // Create a temporary div to parse the HTML
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = htmlContent;
    
    // Clear bubble and type out the HTML content with formatting
    bubble.innerHTML = '';
    
    // Type character by character, preserving HTML structure
    await typeHTMLContent(bubble, tempDiv.childNodes, speed);
  } else {
    // Plain text - use typing animation
    bubble.textContent = '';
    for (let i = 0; i < text.length; i++) {
      bubble.textContent += text[i];
      messagesEl.scrollTop = messagesEl.scrollHeight;
      if (speed > 0) await new Promise(r => setTimeout(r, speed));
    }
  }
}

async function typeHTMLContent(targetElement, nodes, speed) {
  // Recursively type HTML nodes while preserving structure
  for (const node of nodes) {
    if (node.nodeType === Node.TEXT_NODE) {
      // Type text content character by character
      const text = node.textContent;
      const textNode = document.createTextNode('');
      targetElement.appendChild(textNode);
      
      for (let i = 0; i < text.length; i++) {
        textNode.textContent += text[i];
        messagesEl.scrollTop = messagesEl.scrollHeight;
        if (speed > 0) await new Promise(r => setTimeout(r, speed));
      }
    } else if (node.nodeType === Node.ELEMENT_NODE) {
      // Create the element and recursively type its children
      const element = document.createElement(node.tagName);
      
      // Copy attributes
      for (const attr of node.attributes || []) {
        element.setAttribute(attr.name, attr.value);
      }
      
      targetElement.appendChild(element);
      
      // Recursively type children
      await typeHTMLContent(element, node.childNodes, speed);
    }
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
const MODE_KEY = 'apartmint_current_mode';

function getSessionId() {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

function getCurrentMode() {
  return localStorage.getItem(MODE_KEY) || 'broker';
}

function setCurrentMode(mode) {
  localStorage.setItem(MODE_KEY, mode);
  updateModeUI(mode);
}

function updateModeUI(mode) {
  const brokerBtn = document.getElementById('broker-mode-btn');
  const advisorBtn = document.getElementById('advisor-mode-btn');
  const modeToggle = document.querySelector('.mode-toggle');
  
  // Update button active states
  if (mode === 'broker') {
    brokerBtn.classList.add('mode-btn--active');
    advisorBtn.classList.remove('mode-btn--active');
  } else {
    advisorBtn.classList.add('mode-btn--active');
    brokerBtn.classList.remove('mode-btn--active');
  }
  
  // Update data attribute for sliding animation
  if (modeToggle) {
    modeToggle.setAttribute('data-active-mode', mode);
  }
}

async function switchMode(mode) {
  const btn = $('#chat-form button');
  btn.disabled = true;
  
  try {
    const resp = await fetch('/api/switch_mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionId: getSessionId(), mode })
    });
    
    if (!resp.ok) throw new Error('Mode switch failed');
    const data = await resp.json();
    
    // Update local mode silently (no chat message)
    setCurrentMode(mode);
    
    // Update summary text based on mode (but keep listings visible)
    if (mode === 'advisor') {
      // Don't clear cards - keep listings visible for advisor to reference
      summaryEl.textContent = '🎓 Ask me anything about housing in Sweden!';
    } else {
      summaryEl.textContent = '🔍 Tell me what you\'re looking for to see listings.';
    }
  } catch (e) {
    // Only show error if switch actually failed
    const errBubble = addMessage('', 'bot');
    await typeText(errBubble, 'Sorry, mode switch failed. Please try again.', 15);
  } finally {
    btn.disabled = false;
  }
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
    const currentMode = data.mode || getCurrentMode();
    
    // Only update cards if in broker mode or if we have new results
    if (currentMode === 'broker' && results.length > 0) {
      // Broker mode with results - update cards
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
    } else if (currentMode === 'broker' && results.length === 0) {
      // Broker mode with no results - might be greeting/help
      summaryEl.textContent = 'Tell me what you\'re looking for to see listings.';
      // Don't clear cards - keep previous search visible
    }
    // In advisor mode, don't touch cards at all - they stay from last broker search
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
  // Initialize mode UI
  updateModeUI(getCurrentMode());
  
  // Add mode toggle event listeners
  document.getElementById('broker-mode-btn').addEventListener('click', () => {
    if (getCurrentMode() !== 'broker') {
      switchMode('broker');
    }
  });
  
  document.getElementById('advisor-mode-btn').addEventListener('click', () => {
    if (getCurrentMode() !== 'advisor') {
      switchMode('advisor');
    }
  });
  
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
