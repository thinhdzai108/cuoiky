/* ════════════════════════════════════════════════════════
   FaceSafe Dashboard — app.js
   SSE, Settings, AlertManager, AlertsHistoryPopup
════════════════════════════════════════════════════════ */


// ── Utility: API fetch ─────────────────────────────────────────────────────
async function api(url, { method = 'GET', body } = {}) {
    const opts = {
        method,
        headers: body ? { 'Content-Type': 'application/json' } : {},
        ...(body ? { body: JSON.stringify(body) } : {}),
    };
    const res = await fetch(url, opts);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}


// ── Utility: Toast ─────────────────────────────────────────────────────────
function showToast(message, type = 'success') {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icons = {
        success: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`,
        error:   `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
        loading: `<svg class="spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83"/></svg>`,
    };
    toast.innerHTML = `${icons[type] || ''}><span>${message}</span>`;
    container.appendChild(toast);

    if (type !== 'loading') {
        setTimeout(() => {
            toast.classList.add('fade-out');
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }
    return toast;
}


// ── Clock ──────────────────────────────────────────────────────────────────
function initClock() {
    const el = document.getElementById('liveClock');
    if (!el) return;
    const update = () => {
        const now = new Date();
        const pad = n => String(n).padStart(2, '0');
        el.textContent = `${pad(now.getDate())}/${pad(now.getMonth()+1)}/${now.getFullYear()} — ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
    };
    update();
    setInterval(update, 1000);
}


// ── Alert state counters ────────────────────────────────────────────────────
const alertState = {
    total: 0, maskCount: 0, distCount: 0,
    lastStr: '—',
};

function updateAlertSummary(data) {
    alertState.total++;
    alertState.lastStr = data.time ? (data.time.split(' ')[1] || data.time) : '—';

    if (data.vtype === 'no_mask') alertState.maskCount++;
    else                          alertState.distCount++;

    // Card 1 stats
    const $ = id => document.getElementById(id);
    if ($('sumAlertsTotal')) $('sumAlertsTotal').textContent = alertState.total;
    if ($('sumMaskViol'))    $('sumMaskViol').textContent    = alertState.maskCount;
    if ($('sumDistViol'))    $('sumDistViol').textContent    = alertState.distCount;
    if ($('sumLastAlert'))   $('sumLastAlert').textContent   = alertState.lastStr;

    // Status chip
    const chip = $('sumStatus');
    if (chip) {
        const isMask = data.vtype === 'no_mask';
        chip.textContent = isMask ? 'Không đeo KT!' : 'Vi phạm KC!';
        chip.className   = `sum-status ${isMask ? 'danger' : 'warning'}`;
        clearTimeout(alertState._resetTimer);
        alertState._resetTimer = setTimeout(() => {
            chip.textContent = 'An toàn';
            chip.className   = 'sum-status safe';
        }, 10000);
    }
}


// ── Alert Manager (SSE) ────────────────────────────────────────────────────
class AlertManager {
    constructor() {
        this.list  = document.getElementById('alertList');
        this.badge = document.getElementById('alertBadge');
        this.empty = document.getElementById('emptyState');
        this.count = 0;
        if (this.list) this._connect();
    }


    _updateStatus(data) {
        const pc = document.getElementById('peopleCount');
        if (pc) pc.textContent = `${data.count} người`;

        const mv = document.getElementById('maskViolCount');
        const dv = document.getElementById('distViolCount');
        const om = document.getElementById('ovMaskViol');
        const od = document.getElementById('ovDistViol');

        if (mv) mv.textContent = `Đeo KT: ${data.mask_v}`;
        if (dv) dv.textContent = `Khoảng cách: ${data.dist_v}`;
        if (om) om.classList.toggle('active', data.mask_v > 0);
        if (od) od.classList.toggle('active', data.dist_v > 0);
    }

    _connect() {
        const es = new EventSource('/api/alerts');
        es.onmessage = e => {
            let data;
            try { data = JSON.parse(e.data); } catch { return; }

            if      (data.type === 'status') this._updateStatus(data);
            else if (data.type === 'alert')  this._add(data);
            // ignore: detections, unknown events
        };
        es.onerror = () => setTimeout(() => this._connect(), 3000);
    }

    _add(data) {
        this.count++;
        if (this.badge) this.badge.textContent = this.count;
        if (this.empty) this.empty.style.display = 'none';

        updateAlertSummary(data);

        const isMask = data.vtype === 'no_mask';
        const cls    = isMask ? 'alert-mask' : 'alert-dist';
        const icon   = isMask ? '😷' : '📏';
        const label  = data.msg || (isMask ? 'Không đeo khẩu trang' : 'Vi phạm khoảng cách');
        const timeStr = data.time ? (data.time.split(' ')[1] || data.time) : '';

        const el = document.createElement('div');
        el.className = `alert-item ${cls}`;
        el.innerHTML = `
            <div class="ai-icon">${icon}</div>
            <div class="ai-content">
                <div class="ai-title">${label}</div>
                <div class="ai-meta">
                    <span class="ai-time">${data.time || ''}</span>
                    <span class="ai-cam">· ID #${data.id}</span>
                    <span class="ai-tg-sent">✓ Telegram</span>
                </div>
            </div>`;

        el.addEventListener('click', () => window.currentAlertsPopup?.open());
        if (this.list) this.list.prepend(el);
    }
}


async function initSettings() {
    const overlay  = document.getElementById('settingsOverlay');
    const backdrop = document.getElementById('settingsBackdrop');
    const btnSave  = document.getElementById('btnSaveSettings');
    const btnTest  = document.getElementById('btnTestTelegram');
    const btnTest2 = document.getElementById('btnTestTelegram2');

    const iConfirm = document.getElementById('inpConfirmFrames');
    const iDist    = document.getElementById('inpDistThreshold');
    const iMaskCD  = document.getElementById('inpMaskCooldown');
    const iDistCD  = document.getElementById('inpDistCooldown');
    const iToken   = document.getElementById('inpTeleToken');
    const iChat    = document.getElementById('inpTeleChat');

    const open  = () => overlay.classList.add('open');
    const close = () => overlay.classList.remove('open');

    ['btnOpenSettings', 'btnOpenSettings3'].forEach(id => {
        document.getElementById(id)?.addEventListener('click', open);
    });
    document.getElementById('btnCloseSettings')?.addEventListener('click', close);
    backdrop?.addEventListener('click', close);

    // Tải config từ server
    try {
        const data = await api('/api/config');
        if (data.status === 'ok') {
            if (iConfirm) iConfirm.value = data.confirm_frames;
            if (iDist)    iDist.value    = data.dist_threshold;
            if (iMaskCD)  iMaskCD.value  = data.mask_cooldown;
            if (iDistCD)  iDistCD.value  = data.dist_cooldown;
            if (iToken)   iToken.value   = data.telegram_token;
            if (iChat)    iChat.value    = data.telegram_chat_id;
            syncQuickSettings(data);
        }
    } catch (e) {
        console.error('Failed to load config', e);
    }

    // Lưu config
    btnSave?.addEventListener('click', async () => {
        const orig = btnSave.innerHTML;
        btnSave.innerHTML = '<span>Đang lưu...</span>';
        try {
            const body = {
                confirm_frames:   parseInt(iConfirm?.value || 5),
                dist_threshold:   parseInt(iDist?.value    || 120),
                mask_cooldown:    parseInt(iMaskCD?.value  || 30),
                dist_cooldown:    parseInt(iDistCD?.value  || 20),
                telegram_token:   iToken?.value  || '',
                telegram_chat_id: iChat?.value   || '',
            };
            await api('/api/config', { method: 'POST', body });
            syncQuickSettings(body);
            showToast('Cài đặt đã được lưu!');
            close();
        } catch {
            showToast('Lưu thất bại!', 'error');
        } finally {
            btnSave.innerHTML = orig;
        }
    });

    // Test Telegram
    const doTest = async () => {
        const t = showToast('Đang kiểm tra kết nối Telegram...', 'loading');
        try {
            const res = await api('/api/test-telegram', { method: 'POST' });
            t.remove();
            if (res.status === 'ok') showToast('✓ Đã gửi! Hãy kiểm tra Telegram.', 'success');
            else                     showToast(res.message || 'Kết nối thất bại.', 'error');
        } catch {
            t.remove();
            showToast('Lỗi kết nối server.', 'error');
        }
    };
    btnTest?.addEventListener('click', doTest);
    btnTest2?.addEventListener('click', doTest);
}

function syncQuickSettings(cfg) {
    const $ = id => document.getElementById(id);
    if ($('qsConfirmFrames')) $('qsConfirmFrames').textContent = `${cfg.confirm_frames || 5}f`;
    if ($('qsDistThreshold')) $('qsDistThreshold').textContent = `${cfg.dist_threshold || 120}px`;
    if ($('qsMaskCooldown'))  $('qsMaskCooldown').textContent  = `${cfg.mask_cooldown  || 30}s`;
    if ($('qsDistCooldown'))  $('qsDistCooldown').textContent  = `${cfg.dist_cooldown  || 20}s`;
    if ($('qsTelegram')) {
        const hasTg = cfg.telegram_token && cfg.telegram_token.length > 10;
        $('qsTelegram').textContent = hasTg ? 'Đã cấu hình' : 'Chưa cấu hình';
        $('qsTelegram').className   = `qs-val ${hasTg ? 'green' : 'red'}`;
    }
}


// ── Alerts History Popup ────────────────────────────────────────────────────
class AlertsHistoryPopup {
    constructor() {
        this.popup     = document.getElementById('alertsHistoryPopup');
        this.backdrop  = document.getElementById('alertsHistoryBackdrop');
        this.listDiv   = document.getElementById('alertsHistoryList');
        this.detailDiv = document.getElementById('alertsHistoryDetail');
        this.searchBox = document.getElementById('alertsSearchBox');
        this.sortBox   = document.getElementById('alertsSortBox');
        this.filterType = document.getElementById('alertsFilterType');
        this.btnClose  = document.getElementById('btnCloseAlertsHistory');

        this.records    = [];
        this.selectedId = null;
        this.filters    = { search: '', sort: 'newest', type: 'all' };

        this._bindEvents();
    }

    _bindEvents() {
        this.backdrop?.addEventListener('click', () => this.close());
        this.btnClose?.addEventListener('click', () => this.close());
        this.searchBox?.addEventListener('input', e => { this.filters.search = e.target.value.toLowerCase(); this._render(); });
        this.sortBox?.addEventListener('change', e => { this.filters.sort = e.target.value; this._render(); });
        this.filterType?.addEventListener('change', e => { this.filters.type = e.target.value; this._render(); });
    }

    open() { this.popup?.classList.add('active'); this._loadRecords(); }
    close() { this.popup?.classList.remove('active'); }

    async _loadRecords() {
        try {
            const res = await api('/api/history');
            if (res.status === 'ok') { this.records = res.data || []; this._render(); }
        } catch (e) { console.error('History load error:', e); }
    }

    _render() {
        let filtered = this.records;

        if (this.filters.type !== 'all')
            filtered = filtered.filter(r => r.vtype === this.filters.type);

        if (this.filters.search)
            filtered = filtered.filter(r =>
                r.track_id.toString().includes(this.filters.search) ||
                r.time.includes(this.filters.search)
            );

        filtered.sort((a, b) =>
            this.filters.sort === 'oldest' ? a.timestamp - b.timestamp : b.timestamp - a.timestamp
        );

        this.listDiv.innerHTML = filtered.map(r => {
            const isMask = r.vtype === 'no_mask';
            const icon   = isMask ? '😷' : '📏';
            const label  = isMask ? 'Không đeo khẩu trang' : 'Vi phạm khoảng cách';
            const cls    = isMask ? 'item-mask' : 'item-dist';
            return `
                <div class="alerts-history-item ${cls} ${this.selectedId === r.id ? 'active' : ''}"
                     onclick="event.stopPropagation(); window.currentAlertsPopup?.selectRecord('${r.id}')">
                    <div class="item-thumb-wrapper">
                        <img src="${r.img_url}" class="item-thumb" onerror="this.style.display='none'">
                    </div>
                    <div class="item-content">
                        <div class="item-meta">
                            <span class="item-time">${r.time}</span>
                            <span class="item-id">#${r.track_id}</span>
                        </div>
                        <div class="item-type">${icon} ${label}</div>
                    </div>
                </div>`;
        }).join('');

        if (!this.selectedId && filtered.length > 0)
            this.selectRecord(filtered[0].id);
    }

    selectRecord(recordId) {
        this.selectedId = recordId;
        const r = this.records.find(r => r.id === recordId);

        this.listDiv.querySelectorAll('.alerts-history-item').forEach(el => {
            el.classList.toggle('active', el.getAttribute('onclick')?.includes(recordId));
        });

        if (!r) { this.detailDiv.innerHTML = '<div class="alerts-detail-empty"><p>Không tìm thấy bản ghi.</p></div>'; return; }

        const isMask = r.vtype === 'no_mask';
        const badgeCls = isMask ? 'mask' : 'dist';
        const badgeTxt = isMask ? '😷 Không đeo khẩu trang' : '📏 Vi phạm khoảng cách';

        this.detailDiv.innerHTML = `
            <div class="detail-view-container">
                <div class="detail-image-wrapper">
                    <img src="${r.img_url}" alt="Alert Evidence" onerror="this.alt='Ảnh không tồn tại'">
                    <span class="detail-type-badge ${badgeCls}">${badgeTxt}</span>
                </div>
                <div class="detail-info-grid">
                    <div class="detail-info-card">
                        <h4>Thời điểm phát hiện</h4>
                        <p>${r.date} ${r.time}</p>
                    </div>
                    <div class="detail-info-card">
                        <h4>Loại vi phạm</h4>
                        <p><span class="type-badge ${badgeCls}">${badgeTxt}</span></p>
                    </div>
                    <div class="detail-info-card">
                        <h4>Định danh đối tượng</h4>
                        <p>Track ID: #${r.track_id}</p>
                    </div>
                </div>
            </div>`;
    }
}


// ════════════════════════════════════════════════════════
// BOOTSTRAP
// ════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
    initClock();

    if (document.getElementById('alertList')) {
        new AlertManager();
        initSettings();

        const popup = new AlertsHistoryPopup();
        window.currentAlertsPopup = popup;

        document.getElementById('btnOpenAlertsHistory')?.addEventListener('click', () => popup.open());
        document.getElementById('btnOpenAlertsHistoryFromLog')?.addEventListener('click', () => popup.open());
    }
});
