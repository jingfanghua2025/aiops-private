// 私有化部署模式前端补丁（跃云 AIOps）：
// - 识别 /api/v1/system/public
// - 隐藏注册/找回/微信/支付/运营看板/仪表盘
// - 新增「用户管理」「系统设置（LLM/仓库/K8S/License）」页面（管理员）
// - 402 时区分 license 到期 vs 算力不足

async function fetchPublicInfo(){
  try{
    const r = await fetch('/api/v1/system/public');
    return await r.json();
  }catch(e){
    return { private_deployment: false };
  }
}

function hideEl(sel){
  document.querySelectorAll(sel).forEach(el=>{ el.classList.add('hidden'); });
}

function setLoginPlaceholders(){
  const u = document.getElementById('login-user');
  const p = document.getElementById('login-pass');
  if (u) u.placeholder = '用户名';
  if (p) p.placeholder = '密码';
}

function escapeHtml(str){
  return String(str)
    .replaceAll('&','&amp;')
    .replaceAll('<','&lt;')
    .replaceAll('>','&gt;')
    .replaceAll('"','&quot;')
    .replaceAll("'",'&#39;');
}

function copyText(txt){
  try{
    navigator.clipboard.writeText(txt);
    return true;
  }catch(e){
    try{
      const ta = document.createElement('textarea');
      ta.value = txt;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
      return true;
    }catch(_){
      return false;
    }
  }
}

function ensureBasePrivateUi(){
  // 登录：只保留用户名+密码
  setLoginPlaceholders();
  hideEl('#reg-box');
  hideEl('#forgot-password-modal');
  // 隐藏微信登录/忘记密码/立即注册/“其他方式”分隔
  hideEl('#login-box button[onclick="handleWechatLogin()"]');
  hideEl('#login-box a[onclick="showForgotPassword()"]');
  hideEl('#login-box a[onclick="toggleAuthMode(\'reg\')"]');
  hideEl('#login-box .fab');
  // “其他方式”那一行
  document.querySelectorAll('#login-box .flex.items-center.gap-2.py-2').forEach(el=>el.classList.add('hidden'));

  // 侧边栏：隐藏充值/用量/运营看板/仪表盘
  hideEl('a[onclick="showSection(\'billing\', this)"]');
  hideEl('a[onclick="showSection(\'usage\', this)"]');
  hideEl('#nav-ops');
  hideEl('a[onclick="showSection(\'dashboard\', this)"]');
}

function patchShowSection(){
  if (window.__PRIVATE_SHOWSECTION_PATCHED__) return;
  window.__PRIVATE_SHOWSECTION_PATCHED__ = true;
  const orig = window.showSection;
  if (typeof orig !== 'function') return;
  window.showSection = function(section, navItem){
    const disabled = new Set(['dashboard','billing','usage','ops']);
    if (disabled.has(section)){
      // 一律重定向到智能问答
      section = 'chat';
      // 尝试找到 chat 的 nav
      const navChat = Array.from(document.querySelectorAll('a.sidebar-item')).find(x=>x.getAttribute('onclick')?.includes("showSection('chat'"));
      navItem = navChat || navItem;
    }
    return orig(section, navItem);
  };
}

function ensureLicenseModal(){
  if (document.getElementById('license-modal')) return;
  const el = document.createElement('div');
  el.id = 'license-modal';
  el.className = 'hidden fixed inset-0 modal z-[220] flex items-center justify-center p-4';
  el.innerHTML = `
    <div class="bg-white rounded-2xl shadow-2xl max-w-lg w-full p-6">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-lg font-bold text-slate-800">需要 License 激活</h3>
        <button class="text-slate-400 hover:text-slate-600" onclick="document.getElementById('license-modal').classList.add('hidden')"><i class="fas fa-times"></i></button>
      </div>
      <div class="text-sm text-slate-600 space-y-3">
        <div class="bg-amber-50 border border-amber-200 rounded-xl p-3">
          <div class="font-bold text-amber-700 mb-1">试用期已到期 / License 无效</div>
          <div id="license-modal-reason" class="text-amber-800 text-xs"></div>
        </div>

        <div>
          <div class="text-xs font-bold text-slate-500">机器码</div>
          <div class="flex gap-2 mt-1">
            <input id="license-modal-machine" class="flex-1 px-3 py-2 bg-slate-50 border rounded-xl font-mono text-xs" readonly />
            <button class="px-3 py-2 bg-slate-100 rounded-xl text-xs font-bold" onclick="copyText(document.getElementById('license-modal-machine').value);alert('已复制')">复制</button>
          </div>
        </div>

        <div>
          <div class="text-xs font-bold text-slate-500">申请码（用于在可联网环境提交到跃云官网）</div>
          <div class="flex gap-2 mt-1">
            <textarea id="license-modal-request" rows="3" class="flex-1 px-3 py-2 bg-slate-50 border rounded-xl font-mono text-xs" readonly></textarea>
            <button class="px-3 py-2 bg-slate-100 rounded-xl text-xs font-bold" onclick="copyText(document.getElementById('license-modal-request').value);alert('已复制')">复制</button>
          </div>
        </div>

        <div class="text-xs text-slate-500 leading-relaxed">
          <div class="font-bold text-slate-700 mb-1">申请/续期步骤</div>
          <ol id="license-modal-steps" class="list-decimal ml-5 space-y-1"></ol>
        </div>

        <div class="border-t pt-3">
          <div class="text-xs font-bold text-slate-500">导入 License Token（管理员）</div>
          <div class="flex gap-2 mt-1">
            <textarea id="license-modal-token" rows="3" class="flex-1 px-3 py-2 bg-white border rounded-xl font-mono text-xs" placeholder="粘贴 license token"></textarea>
            <button class="px-3 py-2 bg-blue-600 text-white rounded-xl text-xs font-bold" onclick="activateLicenseFromModal()">激活</button>
          </div>
          <div class="text-[11px] text-slate-400 mt-2">提示：私有化环境不出网，请在可联网环境提交申请码，审批后拿到 token 再回到这里导入。</div>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(el);
}

async function openLicenseModal(detail){
  ensureLicenseModal();
  document.getElementById('license-modal').classList.remove('hidden');
  const reason = document.getElementById('license-modal-reason');
  reason.textContent = detail?.message || detail?.reason || '';

  // 需要管理员 token 才能拿到申请码；如果未登录则先提示
  if (!localStorage.getItem('aio_token')){
    alert('请先用管理员账号登录后获取申请码并导入 license');
    return;
  }
  try{
    const req = await api('/system/license/request');
    if (!req) return;
    document.getElementById('license-modal-machine').value = req.machine_code || '';
    document.getElementById('license-modal-request').value = req.request_code || '';
    const steps = document.getElementById('license-modal-steps');
    steps.innerHTML = (req.steps||[]).map(s=>`<li>${escapeHtml(s)}</li>`).join('');
  }catch(e){
    // ignore
  }
}

async function activateLicenseFromModal(){
  const token = (document.getElementById('license-modal-token')?.value || '').trim();
  if (!token) return alert('请粘贴 token');
  const res = await api('/system/license/activate', 'POST', { token });
  if (res){
    alert(res.message || '激活成功');
    document.getElementById('license-modal').classList.add('hidden');
    // 刷新页面使 license 中间件放行
    setTimeout(()=>location.reload(), 400);
  }
}

function patchApi402(){
  if (window.__PRIVATE_API_PATCHED__) return;
  window.__PRIVATE_API_PATCHED__ = true;
  if (typeof window.api !== 'function') return;
  const orig = window.api;
  window.api = async function(path, method='GET', body=null){
    try{
      return await orig(path, method, body);
    }catch(e){
      if (e && e.status === 402){
        // 尝试识别 license
        // 原 api() 只抛出 detail 字符串；license_block_response 会返回 {detail:"需要license激活", license:{...}}
        // 这里再用 public 接口拿到 license_detail
        const pub = await fetchPublicInfo();
        if (pub && pub.private_deployment && pub.license_ok === false){
          await openLicenseModal(pub.license_detail);
          return null;
        }
      }
      throw e;
    }
  };
}

function addNavItem(nav, id, label, iconClass, onClick){
  if (document.getElementById(id)) return;
  const a = document.createElement('a');
  a.id = id;
  a.href = 'javascript:void(0)';
  a.className = 'sidebar-item flex items-center px-4 py-2.5 rounded-xl transition';
  a.onclick = onClick;
  a.innerHTML = `<i class="${iconClass} w-5 opacity-70"></i><span class="font-semibold ml-2">${label}</span>`;
  nav.appendChild(a);
}

function addUsersSection(){
  const nav = document.querySelector('aside nav');
  const main = document.querySelector('main');
  if (!nav || !main) return;

  addNavItem(nav, 'nav-users', '用户管理', 'fas fa-users', function(){ showSection('users', document.getElementById('nav-users')); });

  if (document.getElementById('section-users')) return;
  const sec = document.createElement('div');
  sec.id = 'section-users';
  sec.className = 'space-y-6 hidden';
  sec.innerHTML = `
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-bold text-slate-800">用户管理</h2>
        <div class="text-sm text-slate-500 mt-1">私有化部署仅支持管理员创建用户，用户通过用户名+密码登录。</div>
      </div>
      <button class="px-4 py-2 bg-blue-600 text-white rounded-xl font-bold" onclick="openCreateUserModal()">创建用户</button>
    </div>

    <div class="glass-card rounded-2xl p-4">
      <div class="flex gap-2 mb-3">
        <input id="users-search" class="flex-1 px-4 py-2 bg-slate-50 border rounded-xl outline-none" placeholder="按用户名搜索" oninput="renderUsersTable()" />
        <button class="px-4 py-2 bg-slate-100 rounded-xl font-bold" onclick="loadUsers()">刷新</button>
      </div>
      <div class="overflow-auto">
        <table class="w-full text-sm">
          <thead class="text-slate-400">
            <tr>
              <th class="text-left py-2">ID</th>
              <th class="text-left py-2">用户名</th>
              <th class="text-left py-2">管理员</th>
              <th class="text-left py-2">创建时间</th>
              <th class="text-right py-2">操作</th>
            </tr>
          </thead>
          <tbody id="users-tbody"></tbody>
        </table>
      </div>
    </div>

    <div id="create-user-modal" class="hidden fixed inset-0 modal z-[210] flex items-center justify-center p-4">
      <div class="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-bold text-slate-800">创建用户</h3>
          <button onclick="closeCreateUserModal()" class="text-slate-400 hover:text-slate-600"><i class="fas fa-times"></i></button>
        </div>
        <div class="space-y-3">
          <input id="cu-username" class="w-full px-4 py-2 bg-slate-50 border rounded-xl outline-none" placeholder="用户名" />
          <input id="cu-password" type="password" class="w-full px-4 py-2 bg-slate-50 border rounded-xl outline-none" placeholder="初始密码（至少8位）" />
          <label class="flex items-center gap-2 text-sm text-slate-600">
            <input id="cu-admin" type="checkbox" class="w-4 h-4" />
            <span>设为管理员</span>
          </label>
          <button class="w-full bg-blue-600 text-white py-2.5 rounded-xl font-bold" onclick="handleCreateUser()">确认创建</button>
        </div>
      </div>
    </div>
  `;
  main.appendChild(sec);
}

let __usersCache = [];
async function loadUsers(){
  const data = await api('/system/users');
  if (data && data.items){
    __usersCache = data.items;
    renderUsersTable();
  }
}
function renderUsersTable(){
  const tb = document.getElementById('users-tbody');
  if (!tb) return;
  const q = (document.getElementById('users-search')?.value || '').trim().toLowerCase();
  const items = __usersCache.filter(u => !q || (u.username||'').toLowerCase().includes(q));
  tb.innerHTML = items.map(u => {
    const adminTag = u.is_admin ? '<span class="px-2 py-1 text-xs font-bold bg-blue-50 text-blue-700 rounded">是</span>' : '<span class="px-2 py-1 text-xs font-bold bg-slate-100 text-slate-600 rounded">否</span>';
    return `
      <tr class="border-t border-slate-100">
        <td class="py-2 font-mono text-xs">${u.id}</td>
        <td class="py-2 font-bold">${escapeHtml(u.username||'')}</td>
        <td class="py-2">${adminTag}</td>
        <td class="py-2 text-slate-500 text-xs">${u.created_at ? u.created_at.slice(0,10) : '-'}</td>
        <td class="py-2 text-right">
          <button class="px-3 py-1.5 bg-slate-100 rounded-lg text-xs font-bold" onclick="promptResetPwd(${u.id})">重置密码</button>
          <button class="px-3 py-1.5 bg-red-50 text-red-600 rounded-lg text-xs font-bold" onclick="deleteUser(${u.id})">删除</button>
        </td>
      </tr>
    `;
  }).join('');
}
function openCreateUserModal(){ document.getElementById('create-user-modal')?.classList.remove('hidden'); }
function closeCreateUserModal(){ document.getElementById('create-user-modal')?.classList.add('hidden'); }
async function handleCreateUser(){
  const username = (document.getElementById('cu-username')?.value || '').trim();
  const password = (document.getElementById('cu-password')?.value || '').trim();
  const is_admin = !!document.getElementById('cu-admin')?.checked;
  if (!username || !password) return alert('请输入用户名和密码');
  if (password.length < 8) return alert('密码至少8位');
  const res = await api('/system/users', 'POST', { username, password, is_admin });
  alert(res.message || '创建成功');
  closeCreateUserModal();
  await loadUsers();
}
async function promptResetPwd(userId){
  const pwd = prompt('请输入新密码（至少8位）');
  if (!pwd) return;
  if (pwd.trim().length < 8) return alert('密码至少8位');
  const res = await api(`/system/users/${userId}/reset-password`, 'POST', { new_password: pwd.trim() });
  alert(res.message || '重置成功');
}
async function deleteUser(userId){
  if (!confirm('确认删除该用户？')) return;
  const res = await api(`/system/users/${userId}`, 'DELETE');
  alert(res.message || '删除成功');
  await loadUsers();
}

function addSystemSection(){
  const nav = document.querySelector('aside nav');
  const main = document.querySelector('main');
  if (!nav || !main) return;

  addNavItem(nav, 'nav-system', '系统设置', 'fas fa-gear', function(){ showSection('system', document.getElementById('nav-system')); });

  if (document.getElementById('section-system')) return;
  const sec = document.createElement('div');
  sec.id = 'section-system';
  sec.className = 'space-y-6 hidden';
  sec.innerHTML = `
    <div>
      <h2 class="text-xl font-bold text-slate-800">系统设置</h2>
      <div class="text-sm text-slate-500 mt-1">私有化离线部署：内网模型/私有仓库/K8S 配置 + License 管理</div>
    </div>

    <div class="glass-card rounded-2xl p-4 space-y-5">
      <div class="flex items-center justify-between">
        <div class="font-bold text-slate-800">License</div>
        <button class="px-3 py-2 bg-slate-100 rounded-xl text-xs font-bold" onclick="loadLicenseStatus()">刷新</button>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <div class="text-xs font-bold text-slate-500">状态</div>
          <div id="lic-status" class="mt-1 text-sm font-bold text-slate-800">-</div>
        </div>
        <div>
          <div class="text-xs font-bold text-slate-500">到期时间</div>
          <div id="lic-exp" class="mt-1 text-sm font-mono text-slate-700">-</div>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <div class="text-xs font-bold text-slate-500">机器码</div>
          <div class="flex gap-2 mt-1">
            <input id="lic-machine" class="flex-1 px-3 py-2 bg-slate-50 border rounded-xl font-mono text-xs" readonly />
            <button class="px-3 py-2 bg-slate-100 rounded-xl text-xs font-bold" onclick="copyText(document.getElementById('lic-machine').value);alert('已复制')">复制</button>
          </div>
        </div>
        <div>
          <div class="text-xs font-bold text-slate-500">申请码</div>
          <div class="flex gap-2 mt-1">
            <input id="lic-request" class="flex-1 px-3 py-2 bg-slate-50 border rounded-xl font-mono text-xs" readonly />
            <button class="px-3 py-2 bg-slate-100 rounded-xl text-xs font-bold" onclick="copyText(document.getElementById('lic-request').value);alert('已复制')">复制</button>
          </div>
        </div>
      </div>

      <div class="text-xs text-slate-500">
        <div class="font-bold text-slate-700 mb-1">申请步骤</div>
        <ol id="lic-steps" class="list-decimal ml-5 space-y-1"></ol>
      </div>

      <div class="border-t pt-4">
        <div class="text-xs font-bold text-slate-500">导入 License Token</div>
        <div class="flex gap-2 mt-1">
          <textarea id="lic-token" rows="3" class="flex-1 px-3 py-2 bg-white border rounded-xl font-mono text-xs" placeholder="粘贴 license token"></textarea>
          <button class="px-3 py-2 bg-blue-600 text-white rounded-xl text-xs font-bold" onclick="activateLicense()">激活</button>
        </div>
      </div>
    </div>

    <div class="glass-card rounded-2xl p-4 space-y-4">
      <div class="flex items-center justify-between">
        <div class="font-bold text-slate-800">内网大模型（优先生效）</div>
        <button class="px-3 py-2 bg-slate-100 rounded-xl text-xs font-bold" onclick="loadSystemSettings()">刷新</button>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <div class="text-xs font-bold text-slate-500">Provider</div>
          <select id="cfg-provider" class="w-full px-3 py-2 bg-slate-50 border rounded-xl">
            <option value="auto">auto</option>
            <option value="deepseek">deepseek（OpenAI兼容）</option>
            <option value="openai">openai（OpenAI兼容）</option>
            <option value="dashscope">dashscope</option>
          </select>
        </div>
        <div>
          <div class="text-xs font-bold text-slate-500">Model</div>
          <input id="cfg-model" class="w-full px-3 py-2 bg-slate-50 border rounded-xl" placeholder="MODEL_NAME" />
        </div>
        <div>
          <div class="text-xs font-bold text-slate-500">Base URL</div>
          <input id="cfg-base" class="w-full px-3 py-2 bg-slate-50 border rounded-xl" placeholder="OPENAI_API_BASE" />
        </div>
        <div>
          <div class="text-xs font-bold text-slate-500">API Key（留空则不覆盖已保存）</div>
          <input id="cfg-key" type="password" class="w-full px-3 py-2 bg-slate-50 border rounded-xl" placeholder="OPENAI_API_KEY" />
          <div id="cfg-key-present" class="text-[11px] text-slate-400 mt-1"></div>
        </div>
      </div>
      <div class="flex justify-end">
        <button class="px-4 py-2 bg-blue-600 text-white rounded-xl font-bold" onclick="saveSystemSettings()">保存配置</button>
      </div>
    </div>

    <div class="glass-card rounded-2xl p-4 space-y-4">
      <div class="font-bold text-slate-800">私有仓库 / 镜像仓库 / Nexus</div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <div class="text-xs font-bold text-slate-500">GitLab Base URL</div>
          <input id="cfg-gitlab" class="w-full px-3 py-2 bg-slate-50 border rounded-xl" placeholder="https://gitlab.local" />
        </div>
        <div>
          <div class="text-xs font-bold text-slate-500">GitLab Token（留空则不覆盖已保存）</div>
          <input id="cfg-gitlab-token" type="password" class="w-full px-3 py-2 bg-slate-50 border rounded-xl" />
          <div id="cfg-gitlab-token-present" class="text-[11px] text-slate-400 mt-1"></div>
        </div>
        <div>
          <div class="text-xs font-bold text-slate-500">镜像仓库地址</div>
          <input id="cfg-registry" class="w-full px-3 py-2 bg-slate-50 border rounded-xl" placeholder="harbor.local" />
        </div>
        <div>
          <div class="text-xs font-bold text-slate-500">Nexus Base URL</div>
          <input id="cfg-nexus" class="w-full px-3 py-2 bg-slate-50 border rounded-xl" placeholder="http://nexus.local:8081" />
        </div>
        <div>
          <div class="text-xs font-bold text-slate-500">Nexus User</div>
          <input id="cfg-nexus-user" class="w-full px-3 py-2 bg-slate-50 border rounded-xl" />
        </div>
        <div>
          <div class="text-xs font-bold text-slate-500">Nexus Pass（留空则不覆盖已保存）</div>
          <input id="cfg-nexus-pass" type="password" class="w-full px-3 py-2 bg-slate-50 border rounded-xl" />
          <div id="cfg-nexus-pass-present" class="text-[11px] text-slate-400 mt-1"></div>
        </div>
      </div>
      <div class="flex justify-end">
        <button class="px-4 py-2 bg-blue-600 text-white rounded-xl font-bold" onclick="saveRepoSettings()">保存仓库配置</button>
      </div>
    </div>

    <div class="glass-card rounded-2xl p-4 space-y-4">
      <div class="font-bold text-slate-800">Kubernetes kubeconfig</div>
      <textarea id="cfg-kubeconfig" rows="6" class="w-full px-3 py-2 bg-slate-50 border rounded-xl font-mono text-xs" placeholder="粘贴 kubeconfig YAML（建议为只读权限账号）"></textarea>
      <div id="cfg-kube-present" class="text-[11px] text-slate-400"></div>
      <div class="flex justify-end">
        <button class="px-4 py-2 bg-blue-600 text-white rounded-xl font-bold" onclick="saveKubeconfig()">保存 kubeconfig</button>
      </div>
    </div>
  `;
  main.appendChild(sec);
}

async function loadLicenseStatus(){
  const st = await api('/system/license/status');
  if (!st) return;
  const d = st.detail || {};
  const mode = d.mode || (st.ok ? 'ok' : 'blocked');
  document.getElementById('lic-status').textContent = mode === 'trial' ? '试用中' : (mode === 'license' ? '已激活' : '需要激活');
  document.getElementById('lic-exp').textContent = d.trial_end || d.license_expiry || '-';

  const req = await api('/system/license/request');
  if (req){
    document.getElementById('lic-machine').value = req.machine_code || '';
    document.getElementById('lic-request').value = req.request_code || '';
    const steps = document.getElementById('lic-steps');
    steps.innerHTML = (req.steps||[]).map(s=>`<li>${escapeHtml(s)}</li>`).join('');
  }
}

async function activateLicense(){
  const token = (document.getElementById('lic-token')?.value || '').trim();
  if (!token) return alert('请粘贴 token');
  const res = await api('/system/license/activate', 'POST', { token });
  if (res){
    alert(res.message || '激活成功');
    setTimeout(()=>location.reload(), 400);
  }
}

let __sysCache = null;
async function loadSystemSettings(){
  const cfg = await api('/system/settings');
  if (!cfg) return;
  __sysCache = cfg;

  document.getElementById('cfg-provider').value = cfg.AI_MODEL_PROVIDER || 'auto';
  document.getElementById('cfg-model').value = cfg.MODEL_NAME || '';
  document.getElementById('cfg-base').value = cfg.OPENAI_API_BASE || '';

  document.getElementById('cfg-key').value = '';
  document.getElementById('cfg-key-present').textContent = cfg.OPENAI_API_KEY__present ? '已保存（留空则保持不变）' : '未保存';

  document.getElementById('cfg-gitlab').value = cfg.GITLAB_BASE_URL || '';
  document.getElementById('cfg-gitlab-token').value = '';
  document.getElementById('cfg-gitlab-token-present').textContent = cfg.GITLAB_TOKEN__present ? '已保存（留空则保持不变）' : '未保存';

  document.getElementById('cfg-registry').value = cfg.IMAGE_REGISTRY || '';
  document.getElementById('cfg-nexus').value = cfg.NEXUS_BASE_URL || '';
  document.getElementById('cfg-nexus-user').value = cfg.NEXUS_USER || '';
  document.getElementById('cfg-nexus-pass').value = '';
  document.getElementById('cfg-nexus-pass-present').textContent = cfg.NEXUS_PASS__present ? '已保存（留空则保持不变）' : '未保存';

  document.getElementById('cfg-kubeconfig').value = '';
  document.getElementById('cfg-kube-present').textContent = cfg.KUBECONFIG_YAML__present ? '已保存（出于安全不回显；留空则保持不变）' : '未保存';
}

async function saveSystemSettings(){
  const items = [];
  const provider = (document.getElementById('cfg-provider')?.value || 'auto').trim();
  const model = (document.getElementById('cfg-model')?.value || '').trim();
  const base = (document.getElementById('cfg-base')?.value || '').trim();
  const key = (document.getElementById('cfg-key')?.value || '').trim();

  items.push({ key: 'AI_MODEL_PROVIDER', value: provider });
  items.push({ key: 'MODEL_NAME', value: model });
  items.push({ key: 'OPENAI_API_BASE', value: base });
  if (key) items.push({ key: 'OPENAI_API_KEY', value: key });

  const res = await api('/system/settings', 'POST', { items });
  if (res) alert(res.message || '保存成功');
  await loadSystemSettings();
}

async function saveRepoSettings(){
  const items = [];
  const gitlab = (document.getElementById('cfg-gitlab')?.value || '').trim();
  const gitlabToken = (document.getElementById('cfg-gitlab-token')?.value || '').trim();
  const registry = (document.getElementById('cfg-registry')?.value || '').trim();
  const nexus = (document.getElementById('cfg-nexus')?.value || '').trim();
  const nexusUser = (document.getElementById('cfg-nexus-user')?.value || '').trim();
  const nexusPass = (document.getElementById('cfg-nexus-pass')?.value || '').trim();

  items.push({ key: 'GITLAB_BASE_URL', value: gitlab });
  if (gitlabToken) items.push({ key: 'GITLAB_TOKEN', value: gitlabToken });
  items.push({ key: 'IMAGE_REGISTRY', value: registry });
  items.push({ key: 'NEXUS_BASE_URL', value: nexus });
  items.push({ key: 'NEXUS_USER', value: nexusUser });
  if (nexusPass) items.push({ key: 'NEXUS_PASS', value: nexusPass });

  const res = await api('/system/settings', 'POST', { items });
  if (res) alert(res.message || '保存成功');
  await loadSystemSettings();
}

async function saveKubeconfig(){
  const kube = (document.getElementById('cfg-kubeconfig')?.value || '').trim();
  if (!kube) return alert('请粘贴 kubeconfig');
  const res = await api('/system/settings', 'POST', { items: [{ key: 'KUBECONFIG_YAML', value: kube }] });
  if (res) alert(res.message || '保存成功');
  await loadSystemSettings();
}

(async function initPrivateDeploy(){
  const info = await fetchPublicInfo();
  if (!info || !info.private_deployment) return;

  ensureBasePrivateUi();
  patchShowSection();
  patchApi402();

  // 管理页面仅在登录后加载（避免反复弹登录）
  const hasToken = !!localStorage.getItem('aio_token');

  // 添加管理员页面（权限由后端控制；非管理员访问会 403）
  addUsersSection();
  addSystemSection();

  // 初始落到智能问答
  const navChat = Array.from(document.querySelectorAll('a.sidebar-item')).find(x=>x.getAttribute('onclick')?.includes("showSection('chat'"));
  if (navChat) showSection('chat', navChat);

  if (hasToken){
    // 预加载配置
    setTimeout(async ()=>{
      try{ await loadUsers(); }catch(e){}
      try{ await loadSystemSettings(); }catch(e){}
      try{ await loadLicenseStatus(); }catch(e){}
    }, 600);
  }
})();
