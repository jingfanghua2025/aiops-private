// --- Ops Dashboard Users Extension ---
let currentOpsUserPage = 1;
let visitTrendChart = null;
let visitSourceChart = null;



function ensureOpsUsersTableColumns() {
    const tbody = document.getElementById('ops-users-tbody');
    if (!tbody) return;
    const table = tbody.closest('table');
    const headTr = table ? table.querySelector('thead tr') : null;
    if (!headTr) return;

    // Avoid repeated rewrites
    if (headTr.dataset && headTr.dataset.extended === '1') return;
    headTr.dataset.extended = '1';

    headTr.innerHTML = `
        <th class="py-3 px-2">ID</th>
        <th class="py-3 px-2">用户名</th>
        <th class="py-3 px-2">邮箱</th>
        <th class="py-3 px-2">注册时间</th>
        <th class="py-3 px-2">使用次数</th>
        <th class="text-right py-3 px-2">算力余额</th>
        <th class="text-right py-3 px-2">操作</th>
    `;
}

function ensureOpsUserDetailModal() {
    if (document.getElementById('ops-user-usage-modal')) return;

    const wrap = document.createElement('div');
    wrap.id = 'ops-user-usage-modal';
    wrap.className = 'hidden fixed inset-0 modal z-[250] flex items-center justify-center p-4';

    wrap.innerHTML = `
      <div class="bg-white rounded-2xl shadow-2xl w-full max-w-4xl p-6 max-h-[85vh] flex flex-col">
        <div class="flex items-center justify-between mb-4">
          <div>
            <div class="text-xs text-slate-400 font-bold">用户用量详情</div>
            <div id="ops-user-usage-title" class="text-lg font-bold text-slate-800"></div>
          </div>
          <button class="text-slate-400 hover:text-slate-600" onclick="document.getElementById('ops-user-usage-modal').classList.add('hidden')">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <div id="ops-user-usage-summary" class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4"></div>

        <div class="flex-1 overflow-y-auto border border-slate-100 rounded-xl">
          <table class="w-full text-xs text-left">
            <thead>
              <tr class="text-slate-400 border-b border-slate-100">
                <th class="py-2 px-3">日期</th>
                <th class="py-2 px-3">方案咨询</th>
                <th class="py-2 px-3">代码</th>
                <th class="py-2 px-3">排障&部署</th>
                <th class="py-2 px-3">合计</th>
                <th class="py-2 px-3 text-right">消耗算力</th>
              </tr>
            </thead>
            <tbody id="ops-user-usage-tbody" class="text-slate-600"></tbody>
          </table>
        </div>

        <div class="mt-4 flex justify-between items-center">
          <div class="text-[11px] text-slate-400">默认展示最近30天</div>
          <button class="px-4 py-2 rounded-xl bg-slate-100 text-slate-700 text-xs font-bold hover:bg-slate-200" onclick="document.getElementById('ops-user-usage-modal').classList.add('hidden')">关闭</button>
        </div>
      </div>
    `;

    document.body.appendChild(wrap);
}

async function openOpsUserDailyUsage(userId, usernameEnc) {
    ensureOpsUserDetailModal();
    const modal = document.getElementById('ops-user-usage-modal');
    const title = document.getElementById('ops-user-usage-title');
    const tbody = document.getElementById('ops-user-usage-tbody');
    const summary = document.getElementById('ops-user-usage-summary');

    const username = usernameEnc ? decodeURIComponent(usernameEnc) : '';
    if (title) title.innerText = `${username || '-'} (ID: ${userId})`;
    if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="py-6 text-center text-slate-400">加载中...</td></tr>';
    if (summary) summary.innerHTML = '';

    if (modal) modal.classList.remove('hidden');

    const token = authToken || localStorage.getItem('aio_token') || '';
    try {
        const res = await fetch(`/api/v1/admin/ops/users/${userId}/daily-usage?days=30`, {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        const data = await res.json().catch(()=>({}));
        if (!res.ok) {
            if (typeof uiAlert === 'function') uiAlert(data.detail || '加载失败');
            if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="py-6 text-center text-red-500">加载失败：${(data.detail||res.statusText||'')}</td></tr>`;
            return;
        }

        const items = Array.isArray(data.items) ? data.items : [];
        const totals = data.totals || {};

        if (summary) {
            summary.innerHTML = `
              <div class="glass-card p-3 rounded-xl"><div class="text-[10px] text-slate-400 font-bold">方案咨询</div><div class="text-sm font-bold">${Number(totals.qa||0).toLocaleString()}</div></div>
              <div class="glass-card p-3 rounded-xl"><div class="text-[10px] text-slate-400 font-bold">代码</div><div class="text-sm font-bold">${Number(totals.code||0).toLocaleString()}</div></div>
              <div class="glass-card p-3 rounded-xl"><div class="text-[10px] text-slate-400 font-bold">排障&部署</div><div class="text-sm font-bold">${Number(totals.ops||0).toLocaleString()}</div></div>
              <div class="glass-card p-3 rounded-xl"><div class="text-[10px] text-slate-400 font-bold">总次数</div><div class="text-sm font-bold">${Number(totals.total||0).toLocaleString()}</div></div>
              <div class="glass-card p-3 rounded-xl"><div class="text-[10px] text-slate-400 font-bold">消耗算力</div><div class="text-sm font-bold text-blue-600">${Number(totals.compute||0).toFixed(2)}</div></div>
            `;
        }

        if (tbody) {
            if (!items.length) {
                tbody.innerHTML = '<tr><td colspan="6" class="py-6 text-center text-slate-400">暂无数据</td></tr>';
            } else {
                tbody.innerHTML = items.map(it => {
                    const c = Number(it.compute || 0);
                    return `
                      <tr class="border-b border-slate-50 hover:bg-slate-50">
                        <td class="py-2 px-3 font-mono text-xs">${it.date || '-'}</td>
                        <td class="py-2 px-3">${Number(it.qa||0).toLocaleString()}</td>
                        <td class="py-2 px-3">${Number(it.code||0).toLocaleString()}</td>
                        <td class="py-2 px-3">${Number(it.ops||0).toLocaleString()}</td>
                        <td class="py-2 px-3 font-bold">${Number(it.total||0).toLocaleString()}</td>
                        <td class="py-2 px-3 text-right font-mono ${c>0?'text-blue-600 font-bold':'text-slate-400'}">${c.toFixed(2)}</td>
                      </tr>
                    `;
                }).join('');
            }
        }

    } catch (e) {
        console.error(e);
        if (typeof uiAlert === 'function') uiAlert('加载失败: ' + (e.message || String(e)));
        if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="py-6 text-center text-red-500">加载失败：${e.message || String(e)}</td></tr>`;
    }
}
function switchOpsTab(tab) {
    // Toggle Views
    document.getElementById('ops-view-overview').classList.toggle('hidden', tab !== 'overview');
    document.getElementById('ops-view-users').classList.toggle('hidden', tab !== 'users');
    const visitView = document.getElementById('ops-view-visits');
    if (visitView) visitView.classList.toggle('hidden', tab !== 'visits');
    
    // Toggle Tabs
    const tabs = ['overview', 'users', 'visits'];
    tabs.forEach(t => {
        const btn = document.getElementById('ops-tab-' + t);
        if (btn) {
            if (t === tab) {
                btn.className = "text-sm font-bold text-blue-600 border-b-2 border-blue-600 pb-2 transition-colors";
            } else {
                btn.className = "text-sm font-bold text-slate-500 hover:text-slate-700 pb-2 transition-colors";
            }
        }
    });

    if (tab === 'users') loadOpsUsers();
    if (tab === 'visits') loadVisitStats();
}

async function loadOpsUsers(page) {
    if (page) currentOpsUserPage = page;
    const token = authToken || localStorage.getItem('aio_token') || '';
    try {
        const res = await fetch(`/api/v1/admin/ops/users?page=${currentOpsUserPage}&page_size=20`, {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        
        if (res.status === 403) {
            const tbody = document.getElementById('ops-users-tbody');
            if(tbody) tbody.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-red-500">无权访问（需要管理员权限）</td></tr>';
            return;
        }

        const data = await res.json();
        
        const tbody = document.getElementById('ops-users-tbody');
        if (!tbody) return;
        
        if (!data.items || data.items.length === 0) {
            ensureOpsUsersTableColumns();
            tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-slate-400">暂无用户</td></tr>';
            return;
        }
        
        ensureOpsUsersTableColumns();
        tbody.innerHTML = data.items.map(u => {
            const uname = encodeURIComponent(u.username || '');
            return `
            <tr class="border-b border-slate-50 hover:bg-slate-50">
                <td class="py-3 px-2">${u.id}</td>
                <td class="py-3 px-2 font-bold text-slate-800">${u.username || '-'}</td>
                <td class="py-3 px-2">${u.email || '-'}</td>
                <td class="py-3 px-2">${u.created_at || '-'}</td>
                <td class="py-3 px-2 font-mono">${Number(u.usage_count || 0).toLocaleString()}</td>
                <td class="py-3 px-2 text-right font-mono font-bold text-blue-600">￥${Number(u.balance).toFixed(2)}</td>
                <td class="py-3 px-2 text-right">
                    <button class="btn-ops-user-detail px-3 py-1.5 bg-blue-50 text-blue-600 rounded-lg text-xs font-bold hover:bg-blue-100" data-user-id="${u.id}" data-username="${uname}">
                        详情
                    </button>
                </td>
            </tr>
            `;
        }).join('');

        // bind detail buttons
        tbody.querySelectorAll('.btn-ops-user-detail').forEach(btn => {
            btn.addEventListener('click', () => openOpsUserDailyUsage(btn.dataset.userId, btn.dataset.username));
        });
        
        const total = data.total || 0;
        const totalPages = Math.ceil(total / 20) || 1;
        document.getElementById('ops-users-info').innerText = `共 ${total} 人，第 ${data.page || 1} / ${totalPages} 页`;
        
    } catch (e) {
        console.error(e);
        const tbody = document.getElementById('ops-users-tbody');
        if(tbody) ensureOpsUsersTableColumns();
        tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-red-400">加载失败: ' + e.message + '</td></tr>';
    }
}

function changeOpsUserPage(delta) {
    if (currentOpsUserPage + delta < 1) return;
    loadOpsUsers(currentOpsUserPage + delta);
}

async function loadVisitStats() {
    const token = authToken || localStorage.getItem('aio_token') || '';
    try {
        const res = await fetch('/api/v1/admin/ops/visits/stats', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        
        if (!res.ok) return; 
        
        const data = await res.json();
        
        // 1. Stats
        const statTotal = document.getElementById('visit-stat-total');
        const statToday = document.getElementById('visit-stat-today');
        if (statTotal) statTotal.innerText = (data.total || 0).toLocaleString();
        if (statToday) statToday.innerText = (data.today || 0).toLocaleString();
        
        // 2. Trend Chart
        if (document.getElementById('visit-trend-chart') && typeof echarts !== 'undefined') {
            if (!visitTrendChart) visitTrendChart = echarts.init(document.getElementById('visit-trend-chart'));
            visitTrendChart.setOption({
                tooltip: { trigger: 'axis' },
                grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
                xAxis: { type: 'category', data: data.trend.labels, boundaryGap: false },
                yAxis: { type: 'value' },
                series: [{
                    name: '访问量',
                    type: 'line',
                    smooth: true,
                    data: data.trend.data,
                    areaStyle: { opacity: 0.1 },
                    itemStyle: { color: '#3b82f6' }
                }]
            });
        }
        
        // 3. Source Chart
        if (document.getElementById('visit-source-chart') && typeof echarts !== 'undefined') {
            if (!visitSourceChart) visitSourceChart = echarts.init(document.getElementById('visit-source-chart'));
            visitSourceChart.setOption({
                tooltip: { trigger: 'item' },
                legend: { top: '5%', left: 'center' },
                series: [{
                    name: '访问来源',
                    type: 'pie',
                    radius: ['40%', '70%'],
                    avoidLabelOverlap: false,
                    itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
                    label: { show: false, position: 'center' },
                    emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
                    data: data.referrers && data.referrers.length ? data.referrers : [{value:0, name:'暂无数据'}]
                }]
            });
        }
        
        // 4. Logs
        const tbody = document.getElementById('visit-log-tbody');
        if (tbody && data.recent) {
            tbody.innerHTML = data.recent.map(r => `
                <tr class="border-b border-slate-50 text-slate-600">
                    <td class="py-2">${r.time}</td>
                    <td class="py-2 font-mono text-xs">${r.ip}</td>
                    <td class="py-2 truncate max-w-xs" title="${r.source}">${r.source}</td>
                    <td class="py-2 truncate max-w-xs text-xs text-slate-400" title="${r.ua}">${r.ua ? r.ua.substring(0, 50)+'...' : '-'}</td>
                </tr>
            `).join('');
        }
        
    } catch (e) {
        console.error("Visit stats error", e);
    }
}

// Resize observer for charts
window.addEventListener('resize', () => {
    if (visitTrendChart) visitTrendChart.resize();
    if (visitSourceChart) visitSourceChart.resize();
});
