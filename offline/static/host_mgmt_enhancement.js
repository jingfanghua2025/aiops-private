
(function() {
    // --- 1. Cloud Sync UI ---
    const modalHtml = `
    <div id="cloud-sync-modal" class="fixed inset-0 bg-black/50 hidden items-center justify-center z-50">
        <div class="bg-white rounded-2xl w-full max-w-lg p-6 shadow-2xl transform transition-all scale-95 opacity-0" id="cloud-sync-panel">
            <div class="flex justify-between items-center mb-6">
                <h3 class="text-xl font-bold text-slate-800">导入云主机 / 堡垒机</h3>
                <button onclick="closeCloudSyncModal()" class="text-slate-400 hover:text-slate-600"><i class="fas fa-times"></i></button>
            </div>
            
            <div class="space-y-4">
                <div>
                    <label class="block text-sm font-bold text-slate-700 mb-1">来源</label>
                    <div class="grid grid-cols-3 gap-2">
                        <button onclick="selectSource('tencent')" class="source-btn py-2 border rounded-lg hover:bg-slate-50 active" data-source="tencent">腾讯云</button>
                        <button onclick="selectSource('huawei')" class="source-btn py-2 border rounded-lg hover:bg-slate-50" data-source="huawei">华为云</button>
                        <button onclick="selectSource('aliyun')" class="source-btn py-2 border rounded-lg hover:bg-slate-50" data-source="aliyun">阿里云</button>
                        <button onclick="selectSource('jdcloud')" class="source-btn py-2 border rounded-lg hover:bg-slate-50" data-source="jdcloud">京东云</button>
                        <button onclick="selectSource('ctyun')" class="source-btn py-2 border rounded-lg hover:bg-slate-50" data-source="ctyun">天翼云</button>
                        <button onclick="selectSource('jumpserver')" class="source-btn py-2 border rounded-lg hover:bg-slate-50" data-source="jumpserver">Jumpserver</button>
                        <button onclick="selectSource('spug')" class="source-btn py-2 border rounded-lg hover:bg-slate-50" data-source="spug">Spug</button>
                    </div>
                </div>

                <div id="field-ak">
                    <label class="block text-sm font-bold text-slate-700 mb-1">Access Key (AK)</label>
                    <input type="text" id="sync-ak" class="w-full px-4 py-2 border rounded-xl focus:ring-2 focus:ring-blue-500 outline-none" placeholder="AK ID / Token">
                </div>
                
                <div id="field-sk">
                    <label class="block text-sm font-bold text-slate-700 mb-1">Secret Key (SK)</label>
                    <input type="password" id="sync-sk" class="w-full px-4 py-2 border rounded-xl focus:ring-2 focus:ring-blue-500 outline-none" placeholder="SK Secret">
                </div>

                <div id="field-region">
                    <label class="block text-sm font-bold text-slate-700 mb-1">区域 (Region)</label>
                    <input type="text" id="sync-region" class="w-full px-4 py-2 border rounded-xl focus:ring-2 focus:ring-blue-500 outline-none" placeholder="e.g. ap-guangzhou / cn-hangzhou">
                </div>

                <div id="field-url" class="hidden">
                    <label class="block text-sm font-bold text-slate-700 mb-1">平台 URL</label>
                    <input type="text" id="sync-url" class="w-full px-4 py-2 border rounded-xl focus:ring-2 focus:ring-blue-500 outline-none" placeholder="http://example.com">
                </div>

                <div class="bg-blue-50 text-blue-700 p-3 rounded-lg text-sm">
                    <i class="fas fa-info-circle"></i> <span id="sync-tip">请输入腾讯云 API 密钥进行同步。</span>
                </div>

                <button onclick="handleSyncSubmit()" id="btn-sync-submit" class="w-full py-3 bg-blue-600 text-white rounded-xl font-bold hover:bg-blue-700 transition shadow-lg shadow-blue-200">
                    开始同步
                </button>
            </div>
        </div>
    </div>
    `;
    
    if(!document.getElementById('cloud-sync-modal')) {
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    }

    window.openCloudSyncModal = function() {
        const modal = document.getElementById('cloud-sync-modal');
        const panel = document.getElementById('cloud-sync-panel');
        modal.classList.remove('hidden');
        modal.classList.add('flex');
        setTimeout(() => {
            panel.classList.remove('scale-95', 'opacity-0');
            panel.classList.add('scale-100', 'opacity-100');
        }, 10);
    };

    window.closeCloudSyncModal = function() {
        const modal = document.getElementById('cloud-sync-modal');
        const panel = document.getElementById('cloud-sync-panel');
        panel.classList.remove('scale-100', 'opacity-100');
        panel.classList.add('scale-95', 'opacity-0');
        setTimeout(() => {
            modal.classList.remove('flex');
            modal.classList.add('hidden');
        }, 300);
    };

    let currentSource = 'tencent';

    window.selectSource = function(source) {
        currentSource = source;
        document.querySelectorAll('.source-btn').forEach(b => {
            const isSel = b.dataset.source === source;
            b.classList.toggle('active', isSel);
            b.classList.toggle('bg-blue-50', isSel);
            b.classList.toggle('text-blue-600', isSel);
            b.classList.toggle('border-blue-200', isSel);
        });

        const fieldUrl = document.getElementById('field-url');
        const fieldRegion = document.getElementById('field-region');
        const fieldAk = document.getElementById('field-ak');
        const fieldSk = document.getElementById('field-sk');
        const tip = document.getElementById('sync-tip');

        if (source === 'jumpserver') {
            fieldUrl.classList.remove('hidden');
            fieldRegion.classList.add('hidden');
            fieldAk.querySelector('label').innerText = 'Token / Access Key ID';
            fieldSk.classList.remove('hidden');
            tip.innerText = '请输入 Private Token 或 Access Key (ID + Secret)。';
        } else if (source === 'spug') {
            fieldUrl.classList.remove('hidden');
            fieldRegion.classList.add('hidden');
            fieldAk.querySelector('label').innerText = 'API Token';
            fieldSk.classList.add('hidden');
            tip.innerText = '请输入 Spug 平台 URL 和 API Token (填入 Access Key 栏)。';
        } else if (['tencent', 'huawei', 'aliyun', 'jdcloud', 'ctyun'].includes(source)) {
            fieldUrl.classList.add('hidden');
            fieldRegion.classList.remove('hidden');
            fieldAk.querySelector('label').innerText = 'Access Key (AK)';
            fieldSk.classList.remove('hidden');
            
            const names = {tencent:'腾讯云', huawei:'华为云', aliyun:'阿里云', jdcloud:'京东云', ctyun:'天翼云'};
            tip.innerText = `请输入 ${names[source]} API 密钥。`;
        }
    };

    window.handleSyncSubmit = async function() {
        const btn = document.getElementById('btn-sync-submit');
        const originalText = btn.innerText;
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 同步中...';

        const payload = {
            source: currentSource,
            access_key: document.getElementById('sync-ak').value,
            secret_key: document.getElementById('sync-sk').value,
            region: document.getElementById('sync-region').value,
            url: document.getElementById('sync-url').value
        };

        try {
            if (typeof api === 'undefined') throw new Error("API function missing");
            const res = await api('/ssh/hosts/sync', 'POST', payload);
            if (!res) return; 
            alert(res.message || '同步成功');
            closeCloudSyncModal();
            if (typeof loadHosts === 'function') loadHosts();
        } catch (e) {
            alert('同步失败: ' + (e.message || String(e)));
        } finally {
            btn.disabled = false;
            btn.innerText = originalText;
        }
    };

    // --- 2. Inject UI Logic (Header & Key Toggle) ---
    function injectUI() {
        const headers = Array.from(document.querySelectorAll('h3'));
        const addHeader = headers.find(h => h.innerText.includes('添加主机资产'));
        
        if (addHeader && !document.getElementById('btn-import-header')) {
            const container = document.createElement('div');
            container.className = 'flex justify-between items-center mb-4';
            
            const newHeader = addHeader.cloneNode(true);
            newHeader.className = 'font-bold text-sm'; 
            newHeader.style.marginBottom = '0'; 
            newHeader.innerText = '添加主机资产';
            
            const btn = document.createElement('button');
            btn.id = 'btn-import-header';
            btn.className = 'text-blue-600 text-xs font-bold hover:underline bg-blue-50 px-3 py-1 rounded-full transition';
            btn.innerHTML = '<i class="fas fa-cloud-download-alt mr-1"></i>导入云主机';
            btn.onclick = openCloudSyncModal;
            
            container.appendChild(newHeader);
            container.appendChild(btn);
            
            if (addHeader.parentNode) {
                addHeader.parentNode.replaceChild(container, addHeader);
            }
        }

        const passInput = document.getElementById('ssh-pass');
        if (passInput && !document.getElementById('auth-wrapper')) {
            const wrapper = document.createElement('div');
            wrapper.id = 'auth-wrapper';
            wrapper.className = 'relative group w-full'; 
            passInput.parentNode.insertBefore(wrapper, passInput);
            wrapper.appendChild(passInput);
            
            const toggleHtml = `
                <div class="absolute -top-6 right-0 flex gap-2 text-[10px] text-slate-500">
                    <label class="cursor-pointer flex items-center gap-1 hover:text-blue-600"><input type="radio" name="auth_type" value="password" checked onchange="toggleAuthType(this.value)"> 密码</label>
                    <label class="cursor-pointer flex items-center gap-1 hover:text-blue-600"><input type="radio" name="auth_type" value="key" onchange="toggleAuthType(this.value)"> Key</label>
                </div>
                <textarea id="input-private-key" class="w-full px-3 py-2 border rounded-lg outline-none text-xs font-mono hidden resize-none" rows="1" placeholder="私钥内容 (-----BEGIN...)" style="height: 42px;"></textarea>
            `;
            wrapper.insertAdjacentHTML('beforeend', toggleHtml);
        }
    }

    window.toggleAuthType = function(type) {
        const pass = document.getElementById('ssh-pass');
        const key = document.getElementById('input-private-key');
        if (type === 'password') {
            pass.classList.remove('hidden');
            key.classList.add('hidden');
        } else {
            pass.classList.add('hidden');
            key.classList.remove('hidden');
        }
    };

    window.handleAddHost = async function() {
        const name = document.getElementById('ssh-name')?.value || '';
        const ip = document.getElementById('ssh-ip')?.value || '';
        const port = Number(document.getElementById('ssh-port')?.value || 22);
        const username = document.getElementById('ssh-user')?.value || '';
        
        const authTypeEl = document.querySelector('input[name="auth_type"]:checked');
        const authType = authTypeEl ? authTypeEl.value : 'password';
        
        let password = '';
        let private_key = '';
        
        if (authType === 'password') {
            password = document.getElementById('ssh-pass')?.value || '';
            if (!ip || !username || !password) return alert('请填写 IP/用户名/密码');
        } else {
            private_key = document.getElementById('input-private-key')?.value || '';
            if (!ip || !username || !private_key) return alert('请填写 IP/用户名/私钥');
        }
        
        try {
            const res = await api('/ssh/hosts', 'POST', { 
                name, ip, port, username, password, private_key 
            });
            if (res?.message) alert(res.message);
            if (typeof loadHosts === 'function') await loadHosts();
            
            if (authType === 'password') document.getElementById('ssh-pass').value = '';
            else document.getElementById('input-private-key').value = '';
            document.getElementById('ssh-ip').value = '';
            document.getElementById('ssh-name').value = '';
            
        } catch(e) {
            alert('添加失败: ' + e.message);
        }
    };

    const style = document.createElement('style');
    style.innerHTML = `
        .source-btn.active { background-color: #eff6ff; border-color: #bfdbfe; color: #2563eb; }
    `;
    document.head.appendChild(style);

    setInterval(injectUI, 1000);

})();
