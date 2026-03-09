/**
 * Terracota Chat Widget — AI-powered product assistant.
 * Vanilla JS, SSE streaming, localStorage session persistence.
 */
(function () {
    'use strict';

    const STORAGE_KEY = 'tc_chat_session';
    const WELCOME_MSG = 'Olá! Sou o assistente virtual do Terracota. Posso ajudar com dúvidas sobre planos, uso da calculadora e conformidade ANVISA. Como posso ajudar?';

    const CHIPS = [
        'Como funciona?',
        'Planos e preços',
        'Conformidade ANVISA',
        'Falar com humano',
    ];

    class TerracotaChatWidget {
        constructor() {
            this.sessionId = null;
            this.isOpen = false;
            this.isStreaming = false;
            this.chipsVisible = true;
            this._build();
            this._bind();
        }

        /* ---- DOM construction ---- */
        _build() {
            // Bubble
            this.bubble = document.createElement('button');
            this.bubble.className = 'tc-chat-bubble';
            this.bubble.setAttribute('aria-label', 'Abrir assistente virtual');
            this.bubble.innerHTML = '<i class="ph ph-robot"></i><i class="ph ph-x"></i>';

            // Panel
            this.panel = document.createElement('div');
            this.panel.className = 'tc-chat-panel';
            this.panel.setAttribute('role', 'dialog');
            this.panel.setAttribute('aria-label', 'Assistente virtual Terracota');
            this.panel.innerHTML = `
                <div class="tc-chat-header">
                    <div class="tc-chat-header-icon"><i class="ph-duotone ph-robot"></i></div>
                    <div class="tc-chat-header-text">
                        <div class="tc-chat-header-title">Assistente Terracota</div>
                        <div class="tc-chat-header-sub">IA especialista em rotulagem</div>
                    </div>
                    <button class="tc-chat-close" aria-label="Fechar chat"><i class="ph ph-x"></i></button>
                </div>
                <div class="tc-chat-messages" role="log" aria-live="polite"></div>
                <div class="tc-chips"></div>
                <div class="tc-chat-input-wrap">
                    <textarea class="tc-chat-input" placeholder="Digite sua dúvida…" rows="1"></textarea>
                    <button class="tc-chat-send" aria-label="Enviar" disabled><i class="ph ph-paper-plane-tilt"></i></button>
                </div>
            `;

            document.body.appendChild(this.bubble);
            document.body.appendChild(this.panel);

            // Cache refs
            this.messagesEl = this.panel.querySelector('.tc-chat-messages');
            this.chipsEl = this.panel.querySelector('.tc-chips');
            this.input = this.panel.querySelector('.tc-chat-input');
            this.sendBtn = this.panel.querySelector('.tc-chat-send');
            this.closeBtn = this.panel.querySelector('.tc-chat-close');

            // Build chips
            CHIPS.forEach(text => {
                const chip = document.createElement('button');
                chip.className = 'tc-chip';
                chip.textContent = text;
                this.chipsEl.appendChild(chip);
            });

            // Typing indicator
            this.typingEl = document.createElement('div');
            this.typingEl.className = 'tc-typing';
            this.typingEl.innerHTML = '<span class="tc-typing-dot"></span><span class="tc-typing-dot"></span><span class="tc-typing-dot"></span>';
            this.messagesEl.appendChild(this.typingEl);
        }

        /* ---- Event bindings ---- */
        _bind() {
            this.bubble.addEventListener('click', () => this.toggle());
            this.closeBtn.addEventListener('click', () => this.close());
            this.sendBtn.addEventListener('click', () => this._onSend());

            this.input.addEventListener('input', () => {
                this.sendBtn.disabled = !this.input.value.trim() || this.isStreaming;
                this._autoResize();
            });

            this.input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this._onSend();
                }
            });

            this.chipsEl.addEventListener('click', (e) => {
                const chip = e.target.closest('.tc-chip');
                if (!chip) return;
                const text = chip.textContent;
                if (text === 'Falar com humano') {
                    this._openHumanContact();
                    return;
                }
                this._sendMessage(text);
            });

            // ESC to close
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && this.isOpen) this.close();
            });

            // Open from external trigger (e.g. landing button)
            document.addEventListener('click', (e) => {
                if (e.target.closest('[data-open-chat]')) {
                    e.preventDefault();
                    this.open();
                }
            });
        }

        /* ---- Open / Close ---- */
        toggle() {
            this.isOpen ? this.close() : this.open();
        }

        open() {
            this.isOpen = true;
            this.bubble.classList.add('tc-open');
            this.panel.classList.add('tc-visible');

            // Show welcome on first open
            if (this.messagesEl.querySelectorAll('.tc-msg').length === 0) {
                this._appendMsg('assistant', WELCOME_MSG);
            }

            setTimeout(() => this.input.focus(), 200);
        }

        close() {
            this.isOpen = false;
            this.bubble.classList.remove('tc-open');
            this.panel.classList.remove('tc-visible');
        }

        /* ---- Session management ---- */
        async _ensureSession() {
            if (this.sessionId) return;

            // Try to resume from localStorage
            const stored = localStorage.getItem(STORAGE_KEY);
            if (stored) {
                this.sessionId = stored;
                return;
            }

            try {
                const res = await fetch('/api/chat/session', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({}),
                });
                if (res.ok) {
                    const data = await res.json();
                    this.sessionId = data.session_id;
                    localStorage.setItem(STORAGE_KEY, this.sessionId);
                }
            } catch (err) {
                console.error('[TerracotaChat] Session init failed:', err);
            }
        }

        /* ---- Messaging ---- */
        _onSend() {
            const text = this.input.value.trim();
            if (!text || this.isStreaming) return;
            this._sendMessage(text);
        }

        async _sendMessage(text) {
            await this._ensureSession();
            if (!this.sessionId) {
                this._appendMsg('assistant', 'Não foi possível conectar ao assistente. Tente novamente.');
                return;
            }

            // Hide chips after first user message
            if (this.chipsVisible) {
                this.chipsEl.style.display = 'none';
                this.chipsVisible = false;
            }

            this._appendMsg('user', text);
            this.input.value = '';
            this.sendBtn.disabled = true;
            this._autoResize();
            this._showTyping();
            this.isStreaming = true;

            try {
                const res = await fetch('/api/chat/message', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: this.sessionId, message: text }),
                });

                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.error || `HTTP ${res.status}`);
                }

                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                const botEl = this._appendMsg('assistant', '');
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop(); // keep incomplete line

                    for (const line of lines) {
                        if (!line.startsWith('data: ')) continue;
                        try {
                            const payload = JSON.parse(line.slice(6));
                            if (payload.content) {
                                botEl.textContent += payload.content;
                                this._scrollToBottom();
                            }
                            if (payload.done) {
                                this._hideTyping();
                            }
                            if (payload.error) {
                                botEl.textContent = payload.error;
                                this._hideTyping();
                            }
                        } catch { /* skip malformed */ }
                    }
                }

                this._hideTyping();
            } catch (err) {
                console.error('[TerracotaChat] Error:', err);
                this._hideTyping();

                // If session expired, clear and retry
                if (err.message && err.message.includes('session')) {
                    localStorage.removeItem(STORAGE_KEY);
                    this.sessionId = null;
                }

                this._appendMsg('assistant', 'Ocorreu um erro. Tente novamente em instantes.');
            } finally {
                this.isStreaming = false;
                this.sendBtn.disabled = !this.input.value.trim();
            }
        }

        /* ---- DOM helpers ---- */
        _appendMsg(role, content) {
            const el = document.createElement('div');
            el.className = `tc-msg tc-msg-${role}`;
            el.textContent = content;
            this.messagesEl.insertBefore(el, this.typingEl);
            this._scrollToBottom();
            return el;
        }

        _showTyping() {
            this.typingEl.classList.add('tc-active');
            this._scrollToBottom();
        }

        _hideTyping() {
            this.typingEl.classList.remove('tc-active');
        }

        _scrollToBottom() {
            this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
        }

        _autoResize() {
            this.input.style.height = 'auto';
            this.input.style.height = Math.min(this.input.scrollHeight, 80) + 'px';
        }

        _openHumanContact() {
            // Trigger the existing FAQ contact modal or navigate
            const trigger = document.querySelector('[data-faq-contact-trigger]');
            if (trigger) {
                trigger.click();
                this.close();
            } else {
                window.location.href = '/contact';
            }
        }
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => new TerracotaChatWidget());
    } else {
        new TerracotaChatWidget();
    }
})();
