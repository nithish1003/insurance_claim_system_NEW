/**
 * 💎 ClaimIQ AI - Universal Intelligence Engine
 * Production Search Bar v2.0
 */

document.addEventListener('DOMContentLoaded', function() {
    const trigger = document.getElementById('assistantTrigger');
    const windowEl = document.getElementById('assistantWindow');
    const hideBtn = document.getElementById('hideAssistant');
    const input = document.getElementById('assistantInput');
    const sendBtn = document.getElementById('assistantSendBtn');
    const chatBody = document.getElementById('assistantChatBody');
    const quickActions = document.getElementById('quickActions');
    const autocompleteBox = document.getElementById('smartAutocomplete');
    const clearInputBtn = document.getElementById('clearInputBtn');

    let isLoading = false;
    let selectedIndex = -1;
    let suggestions = [];
    let debounceTimer;

    // 🏗️ Window Interaction
    trigger.onclick = () => {
        windowEl.classList.toggle('active');
        if (windowEl.classList.contains('active')) {
            input.focus();
            scrollToBottom();
            if(!input.value.trim()) showRecentSearches();
        }
    };

    hideBtn.onclick = () => windowEl.classList.remove('active');

    // Close on Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (autocompleteBox.style.display === 'flex') {
                hideAutocomplete();
            } else if (windowEl.classList.contains('active')) {
                windowEl.classList.remove('active');
            }
        }
    });

    // 📝 Input Handling
    input.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
        
        const val = this.value.trim();
        clearInputBtn.style.display = val.length > 0 ? 'block' : 'none';
        
        if (val.length >= 2) {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => fetchSuggestions(val), 200);
        } else if (val.length === 0) {
            showRecentSearches();
        } else {
            hideAutocomplete();
        }
    });

    input.addEventListener('focus', () => {
        if (!input.value.trim()) showRecentSearches();
    });

    clearInputBtn.onclick = () => {
        input.value = '';
        input.style.height = 'auto';
        clearInputBtn.style.display = 'none';
        showRecentSearches();
        input.focus();
    };

    // 🥥 Universal Search Intelligence
    async function fetchSuggestions(query) {
        try {
            const response = await fetch(`/assistant/api/autocomplete/?q=${encodeURIComponent(query)}`, {
                headers: { 'Accept': 'application/json' }
            });
            const contentType = response.headers.get('content-type');
            if (response.status === 401 || (contentType && contentType.includes('text/html') && response.url.includes('login'))) {
                // If session expired during autocomplete, just hide it silently or redirect if it was a critical action
                hideAutocomplete();
                return;
            }
            if (!contentType || !contentType.includes('application/json')) {
                hideAutocomplete();
                return;
            }
            const data = await response.json();
            suggestions = data.results || [];
            renderSuggestions(query);
        } catch (e) {
            hideAutocomplete();
        }
    }

    function renderSuggestions(query) {
        if (suggestions.length === 0) {
            autocompleteBox.innerHTML = '<div class="cl-suggestion" style="cursor:default; color:var(--cl-text-dim);">No matching records found.</div>';
            autocompleteBox.style.display = 'flex';
            return;
        }

        // --- CATEGORY GROUPING ---
        const groups = suggestions.reduce((acc, curr) => {
            if (!acc[curr.category]) acc[curr.category] = [];
            acc[curr.category].push(curr);
            return acc;
        }, {});

        let html = '';
        let globalIdx = 0;
        
        // Re-flattened suggestions for keyboard nav
        const flatSuggestions = [];

        Object.keys(groups).forEach(cat => {
            html += `<div class="cl-sug-group-header">${cat}</div>`;
            groups[cat].forEach(s => {
                const currentIdx = globalIdx++;
                flatSuggestions.push(s);
                html += `
                    <div class="cl-suggestion" data-index="${currentIdx}" id="sug_${currentIdx}" onclick="selectSuggestion(${currentIdx})">
                        <div class="cl-sug-info">
                            <div class="cl-sug-title">${highlightMatch(s.title, query)}</div>
                            <div class="cl-sug-sub">${s.subtitle}</div>
                        </div>
                        <span class="cl-sug-badge cl-sug-${s.category.replace(' ', '')}">${s.category}</span>
                    </div>
                `;
            });
        });

        suggestions = flatSuggestions; // Update with flattened order
        autocompleteBox.innerHTML = html;
        autocompleteBox.style.display = 'flex';
        selectedIndex = -1;
    }

    function showRecentSearches() {
        const recent = JSON.parse(localStorage.getItem('cl_recent_searches') || '[]');
        if (recent.length === 0) {
            hideAutocomplete();
            return;
        }

        let html = '<div class="cl-sug-group-header">Recent Searches</div>';
        recent.forEach((s, i) => {
            html += `
                <div class="cl-suggestion" onclick="fillInput('${s}')">
                    <i class="bi bi-clock-history" style="color:var(--cl-text-dim); margin-right:10px;"></i>
                    <div class="cl-sug-title">${s}</div>
                </div>
            `;
        });
        autocompleteBox.innerHTML = html;
        autocompleteBox.style.display = 'flex';
    }

    function saveRecentSearch(query) {
        let recent = JSON.parse(localStorage.getItem('cl_recent_searches') || '[]');
        recent = [query, ...recent.filter(s => s !== query)].slice(0, 5);
        localStorage.setItem('cl_recent_searches', JSON.stringify(recent));
    }

    window.fillInput = (val) => {
        input.value = val;
        fetchSuggestions(val);
        input.focus();
    };

    function highlightMatch(text, query) {
        if (!query) return text;
        const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
        return text.replace(regex, '<span class="cl-highlight">$1</span>');
    }

    function hideAutocomplete() {
        autocompleteBox.style.display = 'none';
        selectedIndex = -1;
    }

    window.selectSuggestion = (idx) => {
        const s = suggestions[idx];
        if (s) {
            saveRecentSearch(s.value);
            input.value = s.value;
            hideAutocomplete();
            sendMessage();
        }
    };

    // ⌨️ Keyboard Mastery
    input.addEventListener('keydown', (e) => {
        if (autocompleteBox.style.display !== 'flex') {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
            return;
        }

        const items = autocompleteBox.querySelectorAll('.cl-suggestion');
        
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            selectedIndex = (selectedIndex + 1) % items.length;
            updateActiveItem(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            selectedIndex = (selectedIndex - 1 + items.length) % items.length;
            updateActiveItem(items);
        } else if (e.key === 'Enter' || e.key === 'Tab') {
            if (selectedIndex >= 0) {
                e.preventDefault();
                selectSuggestion(selectedIndex);
            } else if (e.key === 'Enter') {
                e.preventDefault();
                sendMessage();
            }
        }
    });

    function updateActiveItem(items) {
        items.forEach((item, i) => {
            item.classList.toggle('active', i === selectedIndex);
            if (i === selectedIndex) item.scrollIntoView({ block: 'nearest' });
        });
    }

    // 📤 Message Dispatcher
    async function sendMessage(msgText) {
        const text = msgText || input.value.trim();
        if (!text || isLoading) return;

        isLoading = true;
        sendBtn.disabled = true;
        input.value = '';
        input.style.height = 'auto';
        clearInputBtn.style.display = 'none';
        hideAutocomplete();
        if (quickActions) quickActions.style.display = 'none';

        appendMessage('user', text);
        const thinkingId = 'thinking_' + Date.now();
        appendThinking(thinkingId);
        scrollToBottom();

        try {
            const response = await fetch('/assistant/api/chat/', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json', 
                    'Accept': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken') 
                },
                body: JSON.stringify({ message: text })
            });

            const contentType = response.headers.get('content-type');
            if (response.status === 401 || (contentType && contentType.includes('text/html') && response.url.includes('login'))) {
                removeElement(thinkingId);
                appendMessage('ai', 'Your session has expired. Please <a href="/accounts/login/?next=' + encodeURIComponent(window.location.pathname) + '" class="cl-link">login again</a> to continue.');
                return;
            }

            if (!contentType || !contentType.includes('application/json')) {
                const rawText = await response.text();
                console.error("Non-JSON Chat Response:", rawText);
                throw new Error("NON_JSON_RESPONSE");
            }

            const data = await response.json();
            removeElement(thinkingId);
            appendAIResponse(data);
        } catch (error) {
            removeElement(thinkingId);
            const msg = error.message === "NON_JSON_RESPONSE" 
                ? "Neural service temporarily unavailable. Please try again later." 
                : "Lost connection to neural network. Please retry.";
            appendMessage('ai', msg);
        } finally {
            isLoading = false;
            sendBtn.disabled = false;
            scrollToBottom();
        }
    }

    // ... formatText, scrollToBottom, getCookie mapping ...
    function appendMessage(s, c) {
        const d = document.createElement('div'); d.className = `cl-msg ${s}`;
        d.innerHTML = `<div class="cl-bubble">${formatText(c)}</div>`; 
        chatBody.appendChild(d);
        
        // 🛠️ Keep buttons at the very bottom
        chatBody.appendChild(quickActions);
        
        d.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
    function appendThinking(id) {
        const d = document.createElement('div'); d.className = 'cl-msg ai'; d.id = id;
        d.innerHTML = `<div class="cl-bubble"><div class="cl-thinking"><div class="cl-dot"></div><div class="cl-dot"></div><div class="cl-dot"></div></div></div>`;
        chatBody.appendChild(d);
        
        // 🛠️ Keep buttons at the very bottom
        chatBody.appendChild(quickActions);
        
        d.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
    function appendAIResponse(data) {
        const d = document.createElement('div'); d.className = 'cl-msg ai';
        const b = document.createElement('div'); b.className = 'cl-bubble'; d.appendChild(b);
        const t = data.response || "No data received."; chatBody.appendChild(d);
        
        // 🛠️ Keep buttons at the very bottom
        chatBody.appendChild(quickActions);

        let i = 0; function type() {
            if (i < t.length) { 
                b.innerHTML = formatText(t.substring(0, ++i)); 
                d.scrollIntoView({ behavior: 'auto', block: 'end' });
                setTimeout(type, 10); 
            } 
            else { 
                appendActions(d, data.message_id, data.intent); 
                d.scrollIntoView({ behavior: 'smooth', block: 'end' });
            }
        }
        type();
    }
    function appendActions(d, id, intent) {
        const a = document.createElement('div');
        a.style.cssText = "display:flex; gap:8px; margin-top:8px; opacity:0; transition:0.4s; transform:translateY(10px);";
        a.innerHTML = `<button onclick="submitFeedback('${id}', 1, this)" class="cl-feedback-btn">👍</button><button onclick="submitFeedback('${id}', -1, this)" class="cl-feedback-btn">👎</button>`;
        if(intent === 'fallback') a.innerHTML += `<button onclick="location.href='/support/'" class="cl-escalate-btn">Support</button>`;
        d.appendChild(a); setTimeout(() => { a.style.opacity = '1'; a.style.transform = 'translateY(0)'; scrollToBottom(); }, 100);
    }
    window.submitFeedback = async (id, v, btn) => {
        btn.parentElement.querySelectorAll('button').forEach(b => b.disabled = true);
        try { await fetch('/assistant/api/feedback/', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') }, body: JSON.stringify({ message_id: id, value: v }) }); } catch(e){}
    };
    function formatText(t) { return t.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="cl-link">$1</a>').replace(/\n/g, '<br>'); }
    function scrollToBottom() { chatBody.scrollTop = chatBody.scrollHeight; }
    function removeElement(id) { const e = document.getElementById(id); if(e) e.remove(); }
    function getCookie(n) { 
        let v = null; if (document.cookie && document.cookie !== '') {
            const cs = document.cookie.split(';');
            for (let i = 0; i < cs.length; i++) { const c = cs[i].trim(); if (c.substring(0, n.length + 1) === (n + '=')) { v = decodeURIComponent(c.substring(n.length + 1)); break; } }
        } return v;
    }

    sendBtn.onclick = () => sendMessage();
    window.sendQuickMsg = (m) => sendMessage(m);
});
