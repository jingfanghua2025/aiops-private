// --- Ops Dashboard Users Extension ---
let currentOpsUserPage = 1;
let visitTrendChart = null;
let visitSourceChart = null;

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
            tbody.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-slate-400">暂无用户</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.items.map(u => `
            <tr class="border-b border-slate-50 hover:bg-slate-50">
                <td class="py-3 px-2">${u.id}</td>
                <td class="py-3 px-2 font-bold text-slate-800">${u.username || '-'}</td>
                <td class="py-3 px-2">${u.email || '-'}</td>
                <td class="py-3 px-2">${u.created_at || '-'}</td>
                <td class="py-3 px-2 text-right font-mono font-bold text-blue-600">￥${Number(u.balance).toFixed(2)}</td>
            </tr>
        `).join('');
        
        const total = data.total || 0;
        const totalPages = Math.ceil(total / 20) || 1;
        document.getElementById('ops-users-info').innerText = `共 ${total} 人，第 ${data.page || 1} / ${totalPages} 页`;
        
    } catch (e) {
        console.error(e);
        const tbody = document.getElementById('ops-users-tbody');
        if(tbody) tbody.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-red-400">加载失败: ' + e.message + '</td></tr>';
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
