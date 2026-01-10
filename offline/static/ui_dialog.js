/*
  AIOps+ UI Dialog & Theme Utilities
  - Replace browser alert with app modal dialog (non-blocking)
  - Provide uiConfirm/uiPrompt (async) to replace confirm/prompt
  - Add theme toggle (light/dark) with localStorage persistence
  - Add Enter-to-send for chat input
*/
(function(){
  if (window.__aio_ui_dialog_inited) return;
  window.__aio_ui_dialog_inited = true;

  function ensureDialogDom() {
    if (document.getElementById('aio-ui-dialog-overlay')) return;

    const overlay = document.createElement('div');
    overlay.id = 'aio-ui-dialog-overlay';
    overlay.className = 'hidden fixed inset-0 z-[9999] flex items-center justify-center p-4';
    overlay.style.background = 'rgba(0,0,0,0.55)';
    overlay.style.backdropFilter = 'blur(4px)';

    overlay.innerHTML = `
      <div class="w-full max-w-md bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden">
        <div class="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <div class="font-bold text-slate-800 text-sm" id="aio-ui-dialog-title">提示</div>
          <button id="aio-ui-dialog-x" class="text-slate-400 hover:text-slate-600" aria-label="close">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="px-5 py-4">
          <div id="aio-ui-dialog-message" class="text-sm text-slate-600 whitespace-pre-wrap break-words"></div>
          <div id="aio-ui-dialog-input-wrap" class="hidden mt-3">
            <input id="aio-ui-dialog-input" class="w-full px-3 py-2 border border-slate-200 rounded-xl outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
        </div>
        <div class="px-5 py-4 border-t border-slate-100 flex gap-2 justify-end">
          <button id="aio-ui-dialog-cancel" class="hidden px-4 py-2 rounded-xl bg-slate-100 text-slate-700 text-xs font-bold hover:bg-slate-200">取消</button>
          <button id="aio-ui-dialog-ok" class="px-4 py-2 rounded-xl bg-blue-600 text-white text-xs font-bold hover:bg-blue-700">确定</button>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);

    // Close on overlay click
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        const x = document.getElementById('aio-ui-dialog-x');
        if (x) x.click();
      }
    });
  }

  function showDialog(opts) {
    ensureDialogDom();

    const overlay = document.getElementById('aio-ui-dialog-overlay');
    const titleEl = document.getElementById('aio-ui-dialog-title');
    const msgEl = document.getElementById('aio-ui-dialog-message');
    const okBtn = document.getElementById('aio-ui-dialog-ok');
    const cancelBtn = document.getElementById('aio-ui-dialog-cancel');
    const closeBtn = document.getElementById('aio-ui-dialog-x');
    const inputWrap = document.getElementById('aio-ui-dialog-input-wrap');
    const inputEl = document.getElementById('aio-ui-dialog-input');

    if (!overlay || !titleEl || !msgEl || !okBtn || !cancelBtn || !closeBtn || !inputWrap || !inputEl) {
      // Fallback (should not happen)
      return Promise.resolve({ confirmed: true, value: null });
    }

    const {
      title = '提示',
      message = '',
      okText = '确定',
      cancelText = '取消',
      showCancel = false,
      input = false,
      inputPlaceholder = '',
      defaultValue = ''
    } = (opts || {});

    titleEl.innerText = title;
    msgEl.innerText = (message === undefined || message === null) ? '' : String(message);

    okBtn.innerText = okText;
    cancelBtn.innerText = cancelText;
    cancelBtn.classList.toggle('hidden', !showCancel);

    inputWrap.classList.toggle('hidden', !input);
    inputEl.placeholder = inputPlaceholder || '';
    inputEl.value = defaultValue || '';

    overlay.classList.remove('hidden');

    return new Promise((resolve) => {
      let resolved = false;
      const finish = (confirmed) => {
        if (resolved) return;
        resolved = true;
        overlay.classList.add('hidden');
        cleanup();
        resolve({ confirmed, value: input ? inputEl.value : null });
      };

      const onOk = () => finish(true);
      const onCancel = () => finish(false);
      const onKey = (e) => {
        if (e.key === 'Escape') return onCancel();
        if (e.key === 'Enter' && input) return onOk();
      };

      function cleanup() {
        okBtn.removeEventListener('click', onOk);
        cancelBtn.removeEventListener('click', onCancel);
        closeBtn.removeEventListener('click', onCancel);
        document.removeEventListener('keydown', onKey, true);
      }

      okBtn.addEventListener('click', onOk);
      cancelBtn.addEventListener('click', onCancel);
      closeBtn.addEventListener('click', onCancel);
      document.addEventListener('keydown', onKey, true);

      // focus
      setTimeout(() => {
        try {
          if (input) inputEl.focus();
          else okBtn.focus();
        } catch(e) {}
      }, 0);
    });
  }

  // Public API
  window.uiDialog = {
    show: showDialog,
    alert: function(message, title) {
      return showDialog({ title: title || '提示', message: message || '' });
    },
    confirm: async function(message, title) {
      const res = await showDialog({ title: title || '确认', message: message || '', showCancel: true, okText: '确认', cancelText: '取消' });
      return !!res.confirmed;
    },
    prompt: async function(message, title, defaultValue) {
      const res = await showDialog({
        title: title || '输入',
        message: message || '',
        showCancel: true,
        input: true,
        okText: '确定',
        cancelText: '取消',
        defaultValue: defaultValue || ''
      });
      return res.confirmed ? (res.value || '') : null;
    }
  };

  // Convenience globals
  window.uiAlert = function(msg, title){ return window.uiDialog.alert(msg, title); };
  window.uiConfirm = function(msg, title){ return window.uiDialog.confirm(msg, title); };
  window.uiPrompt = function(msg, title, defaultValue){ return window.uiDialog.prompt(msg, title, defaultValue); };

  // Replace native alert (non-blocking)
  try {
    const nativeAlert = window.alert;
    window.__nativeAlert = nativeAlert;
    window.alert = function(msg){
      // Do not recurse
      return window.uiDialog.alert(msg, '提示');
    };
  } catch(e) {}

  // Theme
  function injectThemeCssOnce(){
    if (document.getElementById('aio-theme-style')) return;
    const style = document.createElement('style');
    style.id = 'aio-theme-style';
    style.innerHTML = `
      body.theme-dark { background: #0b1220 !important; color: #e5e7eb !important; }
      body.theme-dark .glass-card { background: rgba(17, 24, 39, 0.9) !important; border-color: rgba(148,163,184,0.15) !important; box-shadow: none !important; }
      body.theme-dark .border-slate-200 { border-color: rgba(148,163,184,0.18) !important; }
      body.theme-dark .border-slate-100 { border-color: rgba(148,163,184,0.12) !important; }
      body.theme-dark .text-slate-800 { color: #f1f5f9 !important; }
      body.theme-dark .text-slate-700 { color: #e5e7eb !important; }
      body.theme-dark .text-slate-600 { color: #cbd5e1 !important; }
      body.theme-dark .text-slate-500 { color: #94a3b8 !important; }
      body.theme-dark .text-slate-400 { color: #94a3b8 !important; }
      body.theme-dark .bg-white { background-color: rgba(15, 23, 42, 0.92) !important; }
      body.theme-dark .bg-slate-50 { background-color: rgba(15, 23, 42, 0.92) !important; }
      body.theme-dark .bg-\[\#f8fafc\] { background-color: #0b1220 !important; }
      body.theme-dark input, body.theme-dark select, body.theme-dark textarea {
        background-color: rgba(15, 23, 42, 0.92) !important;
        color: #e5e7eb !important;
        border-color: rgba(148,163,184,0.25) !important;
      }
      body.theme-dark .sidebar-item:hover { background-color: rgba(59,130,246,0.10) !important; }
      body.theme-dark .sidebar-item.active { background-color: rgba(59,130,246,0.14) !important; }
    `;
    document.head.appendChild(style);
  }

  function applyTheme(theme){
    injectThemeCssOnce();
    const t = (theme === 'dark') ? 'dark' : 'light';
    document.body.classList.toggle('theme-dark', t === 'dark');
    localStorage.setItem('aio_theme', t);
    // update icon
    const btn = document.getElementById('aio-theme-toggle-btn');
    if (btn) {
      btn.innerHTML = t === 'dark'
        ? '<i class="fas fa-sun"></i><span class="ml-2 hidden md:inline">白天</span>'
        : '<i class="fas fa-moon"></i><span class="ml-2 hidden md:inline">黑夜</span>';
    }
  }

  window.applyTheme = applyTheme;
  window.toggleTheme = function(){
    const cur = localStorage.getItem('aio_theme') || 'light';
    applyTheme(cur === 'dark' ? 'light' : 'dark');
  };

  function injectThemeToggleBtn(){
    if (document.getElementById('aio-theme-toggle-btn')) return;
    const header = document.querySelector('header');
    if (!header) return;
    // try find the right-side container
    const right = header.querySelector('.flex.items-center.gap-3') || header;

    const btn = document.createElement('button');
    btn.id = 'aio-theme-toggle-btn';
    btn.className = 'px-3 py-2 rounded-xl border border-slate-200 bg-white text-slate-600 text-xs font-bold hover:bg-slate-50 flex items-center';
    btn.onclick = window.toggleTheme;
    btn.type = 'button';
    right.insertBefore(btn, right.firstChild);

    const cur = localStorage.getItem('aio_theme') || 'light';
    applyTheme(cur);
  }

  // Enter-to-send on chat input
  function bindEnterToSend(){
    const input = document.getElementById('chat-input');
    if (!input || input.__aio_enter_bound) return;
    input.__aio_enter_bound = true;
    input.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      // if user is in dialog input, ignore
      if (document.getElementById('aio-ui-dialog-overlay') && !document.getElementById('aio-ui-dialog-overlay').classList.contains('hidden')) return;
      e.preventDefault();
      if (typeof window.handleSendQuestion === 'function') window.handleSendQuestion();
    });
  }

  function boot(){
    try { injectThemeToggleBtn(); } catch(e) {}
    try { bindEnterToSend(); } catch(e) {}
  }

  document.addEventListener('DOMContentLoaded', boot);
  // In case scripts load after DOMContentLoaded
  setTimeout(boot, 300);
  setInterval(bindEnterToSend, 1500);
})();
