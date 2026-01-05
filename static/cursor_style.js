/**
 * Cursor风格的前端增强
 * 支持流式输出、Markdown渲染、代码高亮、执行过程显示
 */

// 流式问答函数（像Cursor一样逐字显示）
async function sendMessageStream(q, mode = 'qa', conversationId = null) {
  const token = authToken || localStorage.getItem('aio_token') || '';
  const hist = mode === 'qa' ? qaHistory : mode === 'code' ? codeHistory : opsHistory;
  
  // 添加用户消息
  hist.push({ role: 'user', content: q });
  renderChat();
  
  // 创建占位消息
  const placeholderId = 'msg_' + Date.now();
  const placeholder = {
    role: 'assistant',
    content: '',
    streaming: true,
    id: placeholderId
  };
  hist.push(placeholder);
  renderChat();
  
  // 构建URL
  let url = `/api/v1/ask/stream?question=${encodeURIComponent(q)}&mode=${mode}`;
  if (conversationId) {
    url += `&conversation_id=${encodeURIComponent(conversationId)}`;
  }
  
  try {
    const eventSource = new EventSource(url, {
      headers: {
        'Authorization': 'Bearer ' + token
      }
    });
    
    let fullContent = '';
    let statusMessage = '';
    
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        switch (data.type) {
          case 'status':
            // 显示状态（思考中、生成中等）
            statusMessage = data.message;
            placeholder.content = `<div class="flex items-center gap-2 text-slate-400">
              <div class="animate-spin h-4 w-4 border-2 border-blue-500 border-t-transparent rounded-full"></div>
              <span>${statusMessage}</span>
            </div>`;
            renderChat();
            break;
            
          case 'start':
            // 开始生成内容
            placeholder.content = '';
            fullContent = '';
            break;
            
          case 'token':
            // 逐字显示（打字效果）
            fullContent += data.content;
            placeholder.content = renderMarkdown(fullContent);
            renderChat();
            // 自动滚动到底部
            setTimeout(() => {
              const chatContainer = document.getElementById('chat-container');
              if (chatContainer) {
                chatContainer.scrollTop = chatContainer.scrollHeight;
              }
            }, 50);
            break;
            
          case 'done':
            // 完成
            placeholder.streaming = false;
            placeholder.content = renderMarkdown(fullContent);
            renderChat();
            eventSource.close();
            
            // 高亮代码块
            setTimeout(() => {
              document.querySelectorAll('pre code').forEach(block => {
                if (typeof hljs !== 'undefined') {
                  hljs.highlightElement(block);
                }
              });
            }, 100);
            
            // 更新统计
            updateStats();
            break;
            
          case 'error':
            placeholder.streaming = false;
            placeholder.content = `<div class="text-red-500">错误：${data.message}</div>`;
            renderChat();
            eventSource.close();
            break;
        }
      } catch (e) {
        console.error('解析SSE消息失败:', e);
      }
    };
    
    eventSource.onerror = (error) => {
      console.error('SSE连接错误:', error);
      placeholder.streaming = false;
      placeholder.content = `<div class="text-red-500">连接错误，请重试</div>`;
      renderChat();
      eventSource.close();
    };
    
  } catch (e) {
    console.error('流式请求失败:', e);
    placeholder.streaming = false;
    placeholder.content = `<div class="text-red-500">请求失败：${e.message}</div>`;
    renderChat();
  }
}

// 流式排障计划生成
async function proposeOpsStream(hostId, task, conversationId = null) {
  const token = authToken || localStorage.getItem('aio_token') || '';
  
  // 创建占位消息
  const placeholderId = 'ops_' + Date.now();
  const placeholder = {
    role: 'assistant',
    content: '',
    streaming: true,
    id: placeholderId,
    type: 'ops_plan'
  };
  opsHistory.push(placeholder);
  renderChat();
  
  // 构建URL
  let url = `/api/v1/ssh/propose/stream?host_id=${hostId}&task=${encodeURIComponent(task)}`;
  if (conversationId) {
    url += `&conversation_id=${encodeURIComponent(conversationId)}`;
  }
  
  try {
    const eventSource = new EventSource(url, {
      headers: {
        'Authorization': 'Bearer ' + token
      }
    });
    
    let statusMessage = '';
    
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        switch (data.type) {
          case 'status':
            statusMessage = data.message;
            placeholder.content = `<div class="flex items-center gap-2 text-slate-400 p-4">
              <div class="animate-spin h-4 w-4 border-2 border-blue-500 border-t-transparent rounded-full"></div>
              <span>${statusMessage}</span>
            </div>`;
            renderChat();
            break;
            
          case 'plan':
            // 计划生成完成
            placeholder.streaming = false;
            const cardId = 'ops_' + Date.now() + '_' + Math.random().toString(16).slice(2);
            window.opsCards = window.opsCards || {};
            window.opsCards[cardId] = {
              host_id: data.host_id || hostId,
              host_ip: data.host_ip,
              plan: data.plan,
              task: task,
              status: 'pending',
              conversation_id: data.conversation_id
            };
            
            // 移除占位消息，添加卡片
            const idx = opsHistory.findIndex(m => m.id === placeholderId);
            if (idx !== -1) {
              opsHistory.splice(idx, 1);
            }
            opsHistory.push({ role: 'assistant', kind: 'ops_card', cardId });
            renderChat();
            eventSource.close();
            break;
            
          case 'done':
            eventSource.close();
            break;
            
          case 'error':
            placeholder.streaming = false;
            placeholder.content = `<div class="text-red-500 p-4">错误：${data.message}</div>`;
            renderChat();
            eventSource.close();
            break;
        }
      } catch (e) {
        console.error('解析SSE消息失败:', e);
      }
    };
    
    eventSource.onerror = (error) => {
      console.error('SSE连接错误:', error);
      placeholder.streaming = false;
      placeholder.content = `<div class="text-red-500 p-4">连接错误，请重试</div>`;
      renderChat();
      eventSource.close();
    };
    
  } catch (e) {
    console.error('流式请求失败:', e);
    placeholder.streaming = false;
    placeholder.content = `<div class="text-red-500 p-4">请求失败：${e.message}</div>`;
    renderChat();
  }
}

// Markdown渲染函数（支持代码高亮）
function renderMarkdown(text) {
  if (!text) return '';
  
  try {
    if (typeof marked !== 'undefined') {
      // 使用marked渲染Markdown
      marked.setOptions({
        breaks: true,
        gfm: true,
        highlight: function(code, lang) {
          if (typeof hljs !== 'undefined' && lang) {
            try {
              return hljs.highlight(code, { language: lang }).value;
            } catch (e) {
              return hljs.highlightAuto(code).value;
            }
          }
          return code;
        }
      });
      return marked.parse(text);
    } else {
      // 降级：简单处理
      return text.replace(/\n/g, '<br>');
    }
  } catch (e) {
    console.error('Markdown渲染失败:', e);
    return text.replace(/\n/g, '<br>');
  }
}

// 改进的消息渲染（支持流式显示）
function renderMessageContent(message) {
  if (message.streaming && message.content) {
    // 流式显示中，添加光标动画
    return message.content + '<span class="inline-block w-2 h-5 bg-blue-500 animate-pulse ml-1"></span>';
  }
  
  if (message.content) {
    // 渲染Markdown
    return renderMarkdown(message.content);
  }
  
  return '';
}

// 导出函数供全局使用
if (typeof window !== 'undefined') {
  window.sendMessageStream = sendMessageStream;
  window.proposeOpsStream = proposeOpsStream;
  window.renderMarkdown = renderMarkdown;
  window.renderMessageContent = renderMessageContent;
}

