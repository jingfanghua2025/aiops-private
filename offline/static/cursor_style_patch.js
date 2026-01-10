
// --- Agent Execution ---
let executionHistory = []; // 用于存储当前会话的执行历史

// 新增：重置会话（清空上下文）
window.handleNewChat = async function() {
    if (!(await uiConfirm('确定要开启新会话吗？这将清空当前聊天记录和执行历史。', '开启新会话确认'))) return;

    // 关键修复：不要用 `xxx = []` 替换引用，否则渲染仍可能引用旧数组
    const clearArr = (arr) => {
        try {
            if (Array.isArray(arr)) arr.length = 0;
        } catch (e) {}
    };

    // 清空三种模式的聊天历史（兼容 window 属性与全局 let 变量两种形式）
    try { clearArr(opsHistory); } catch (e) {}
    try { clearArr(qaHistory); } catch (e) {}
    try { clearArr(codeHistory); } catch (e) {}

    clearArr(window.opsHistory);
    clearArr(window.qaHistory);
    clearArr(window.codeHistory);

    // 重新对齐 window 引用（避免后续代码只读 window.* 时不同步）
    try { window.opsHistory = opsHistory; } catch (e) {}
    try { window.qaHistory = qaHistory; } catch (e) {}
    try { window.codeHistory = codeHistory; } catch (e) {}

    // 清空执行上下文（同样原地清空）
    clearArr(executionHistory);

    // 清空 Ops 模式的授权卡片状态
    if (typeof window.opsCards !== 'undefined') window.opsCards = {};

    // 重新渲染
    if (typeof window.renderChat === 'function') window.renderChat();
};

async function handleInlineExecute(btn) {
  // 1. 获取代码块内容
  const pre = btn.closest('.markdown-body').querySelector('pre code');
  if (!pre) return alert('未找到代码块');
  const cmd = pre.innerText.trim();
  
  // 2. 获取目标主机
  const checked = Array.from(document.querySelectorAll('.host-cb:checked')).map(x => Number(x.value)).filter(Boolean);
  if (!checked.length) return alert('请先在左侧选择要执行的主机');
  
  // 3. UI 状态更新 (临时)
  const originalText = btn.innerText;
  btn.disabled = true;
  btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 执行中...';
  
  // 4. 执行 (并发)
  try {
    for (const hostId of checked) {
      // 获取主机名/IP
      const label = document.querySelector(`.host-cb[value="${hostId}"]`)?.parentElement?.innerText || hostId;
      
      const res = await api('/ssh/execute', 'POST', { host_id: hostId, command: cmd });
      const out = res ? (res.output || '') : '';
      const err = res ? (res.error || '') : '';
      const code = (res && typeof res.exit_status !== 'undefined') ? res.exit_status : -1;
      
      const output = (out + (err ? `\n${err}` : '')).trim() || '(无输出)';
      const MAX_LOG_LEN = 10000; 
      const truncatedOutput = output.length > MAX_LOG_LEN 
          ? output.substring(0, MAX_LOG_LEN) + '\n...(截断)...' 
          : output;

      // 记录结果到上下文
      const record = {
        host_id: hostId,
        host_ip: label, 
        cmd: cmd,
        exit_code: code,
        output: truncatedOutput
      };
      executionHistory.push(record);
      
      // --- 关键修改：将执行结果直接写入对话历史，确保用户可见且上下文连贯 ---
      // 使用 'user' 角色模拟系统反馈，或者 'system' (如果支持)
      const resultMsg = {
          role: 'user',
          content: `**[执行结果]** 主机: ${label}\n命令: \`${cmd}\`\n退出码: ${code}\n\n\`\`\`\n${truncatedOutput}\n\`\`\``
      };
      opsHistory.push(resultMsg);
    }
    
    // 渲染聊天窗口 (这会重置按钮状态，并显示刚才的执行结果)
    renderChat();
    
    // 5. 自动触发 AI 下一步分析
    await triggerAgentContinue();

  } catch (e) {
    console.error(e);
    btn.innerText = '执行出错';
    btn.disabled = false;
    alert('执行失败: ' + e.message);
  }
}

async function triggerAgentContinue() {
  // 自动发送请求给 Agent
  const btn = document.getElementById('btn-send');
  if (btn) { btn.disabled = true; btn.innerText = '分析中...'; }
  
  const hist = opsHistory;
  // 添加一个占位符
  const placeholder = { role: 'assistant', content: '收到执行结果，正在分析...' };
  hist.push(placeholder);
  renderChat();
  
  try {
    const checked = Array.from(document.querySelectorAll('.host-cb:checked')).map(x => Number(x.value)).filter(Boolean);
    
    // 上下文过滤：仅发送与当前选中主机相关的历史
    let historyToSend = [];
    if (checked.length > 0) {
        historyToSend = executionHistory.filter(item => checked.includes(item.host_id));
    }
    // 只取最近 10 条
    historyToSend = historyToSend.slice(-10);

    const token = authToken || localStorage.getItem('aio_token') || '';
    const response = await fetch('/api/v1/ssh/agent/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + token
      },
      body: JSON.stringify({
        host_ids: checked,
        // 明确告知 AI 刚执行了什么，要求其基于结果分析
        message: "我已执行上述命令（见上文结果），请根据执行输出进行分析。如果报错，请给出修复建议；如果成功，请给出下一步操作。", 
        execution_history: historyToSend
      })
    });

    if (!response.ok) throw new Error('Agent API Error');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let done = false;
    let text = '';

    while (!done) {
      const { value, done: doneReading } = await reader.read();
      done = doneReading;
      const chunk = decoder.decode(value, { stream: true });
      text += chunk;
      placeholder.content = text;
      renderChat(); 
    }

  } catch (e) {
    placeholder.content = 'Agent Error: ' + e.message;
    renderChat();
  } finally {
    if (btn) { btn.disabled = false; btn.innerText = '发送'; }
  }
}


async function handleSendQuestion() {
  const input = document.getElementById('chat-input');
  const q0 = (input?.value || '').trim();
  if (!q0) return;
  if (input) input.value = '';

  const hist = chatMode==='qa' ? qaHistory : chatMode==='code' ? codeHistory : opsHistory;
  hist.push({ role: 'user', content: q0 });

  const placeholder = { role: 'assistant', content: '正在生成中...' };
  hist.push(placeholder);
  renderChat();

  const btn = document.getElementById('btn-send');
  const oldText = btn?.innerText;
  if (btn) { btn.disabled = true; btn.innerText = '生成中...'; }

  try {
    if (chatMode === 'ops') {
        const checked = Array.from(document.querySelectorAll('.host-cb:checked')).map(x => Number(x.value)).filter(Boolean);
        if (!checked.length) {
            placeholder.content = '请先选择要执行的主机（可多选）。';
            renderChat();
            return;
        }
        
        let historyToSend = [];
        if (checked.length > 0) {
            historyToSend = executionHistory.filter(item => checked.includes(item.host_id));
        }
        historyToSend = historyToSend.slice(-10);

        const token = authToken || localStorage.getItem('aio_token') || '';
        const response = await fetch('/api/v1/ssh/agent/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + token
            },
            body: JSON.stringify({
                host_ids: checked,
                message: q0,
                execution_history: historyToSend 
            })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Request failed');
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let done = false;
        let text = '';
        
        while (!done) {
            const { value, done: doneReading } = await reader.read();
            done = doneReading;
            const chunk = decoder.decode(value, { stream: true });
            text += chunk;
            placeholder.content = text;
            renderChat();
        }
        return;
    }

    const q = (chatMode === 'code')
      ? `你是资深软件工程师。请直接输出可运行代码与必要的说明（含依赖/运行方式），优先给出完整文件内容。\n\n需求：${q0}`
      : q0;

    const token = authToken || localStorage.getItem('aio_token') || '';
    const res = await fetch('/api/v1/ask?question=' + encodeURIComponent(q), {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + token }
    });

    const data = res.ok ? await res.json() : { answer: await res.text() };
    const answer = data?.answer || data?.result || JSON.stringify(data);
    placeholder.content = res.ok ? answer : ('请求失败：' + answer);
    renderChat();
    updateStats();
  } catch (e) {
    console.error(e);
    placeholder.content = '请求异常：' + (e?.message || String(e));
    renderChat();
  } finally {
    if (btn) { btn.disabled = false; btn.innerText = oldText || '发送'; }
  }
}


function renderChat() {
  const box = document.getElementById('chat-box');
  if (!box) return;
  box.innerHTML = '';
  const hist = chatMode==='qa' ? qaHistory : chatMode==='code' ? codeHistory : opsHistory;
  
  // Ops 模式顶部增加“重置会话”按钮 (更明显)
  if (chatMode === 'ops') {
      const toolBar = document.createElement('div');
      toolBar.className = 'flex justify-between items-center mb-4 px-2 pb-2 border-b border-slate-100';
      toolBar.innerHTML = `
        <span class="text-xs text-slate-400">当前会话上下文</span>
        <button onclick="handleNewChat()" class="px-3 py-1.5 text-xs font-bold text-white bg-red-500 hover:bg-red-600 rounded-lg flex items-center gap-1 shadow-sm transition">
            <i class="fas fa-trash-alt"></i> 清空会话 / 新的开始
        </button>
      `;
      box.appendChild(toolBar);
  }

  if (!hist.length) {
    const tip = document.createElement('div');
    tip.className = 'text-xs text-slate-400 px-4';
    tip.innerText = chatMode==='code'
      ? '请输入需求，我将输出可运行的代码。'
      : chatMode==='ops'
        ? '请在左侧选择主机，然后输入运维需求。\nAI 将一步步引导你执行命令。'
        : '请输入问题/方案需求。';
    box.appendChild(tip);
    return;
  }

  const lastAssistantIndex = (() => {
    for (let i = hist.length - 1; i >= 0; i--) {
      if (hist[i].role === 'assistant') return i;
    }
    return -1;
  })();

  hist.forEach((m, i) => {
    const row = document.createElement('div');
    row.className = m.role==='user' ? 'flex flex-col items-end gap-2' : 'flex flex-col items-start gap-2';

    const bubble = document.createElement('div');
    // 增加一种 'result' 样式，如果 content 包含 [执行结果]
    const isResult = m.content && m.content.includes('**[执行结果]**');
    
    if (isResult) {
        bubble.className = 'max-w-[95%] bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-xs font-mono text-slate-700 shadow-inner markdown-body';
    } else {
        bubble.className = (m.role==='user'
          ? 'max-w-[80%] bg-blue-600 text-white rounded-2xl px-4 py-3 text-sm'
          : 'max-w-[95%] bg-white border border-slate-200 rounded-2xl px-4 py-4 text-sm shadow-sm markdown-body');
    }

    if (m.role === 'assistant' || isResult) {
        try {
            bubble.innerHTML = marked.parse(m.content || '');
            bubble.querySelectorAll('pre code').forEach((el) => {
                hljs.highlightElement(el);
                
                // 优化：为代码块增加滚动条限制，避免长输出刷屏
                if (el.parentElement && el.parentElement.tagName === 'PRE') {
                    el.parentElement.classList.add('max-h-[500px]', 'overflow-y-auto');
                }

                // Ops 模式下，为 bash 代码块添加运行按钮 (仅 Assistant 消息)
                if (m.role === 'assistant' && chatMode === 'ops' && (el.classList.contains('language-bash') || el.classList.contains('language-shell'))) {
                    const btnDiv = document.createElement('div');
                    btnDiv.className = 'mt-2 flex justify-end';
                    btnDiv.innerHTML = `<button class="px-3 py-1.5 bg-blue-600 text-white text-xs font-bold rounded-lg hover:bg-blue-700 transition flex items-center gap-1" onclick="handleInlineExecute(this)"><i class="fas fa-play"></i> 运行</button>`;
                    el.parentElement.parentElement.insertBefore(btnDiv, el.parentElement.nextSibling);
                }
            });
        } catch(e) {
            console.error(e);
            bubble.innerText = m.content || '';
        }
    } else {
        bubble.innerText = m.content || '';
    }

    row.appendChild(bubble);
    box.appendChild(row);
  });

  box.scrollTop = box.scrollHeight;
}
