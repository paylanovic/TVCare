'use strict';
(() => {
  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => [...scope.querySelectorAll(selector)];
  const state = { token: '', serial: '', inspection: null, history: [], plan: null, busy: false, page: 'overview' };
  const hash = new URLSearchParams(location.hash.slice(1));
  try { state.token = hash.get('token') || sessionStorage.getItem('tvcare-token') || ''; if (state.token) sessionStorage.setItem('tvcare-token', state.token); } catch (_) { state.token = hash.get('token') || ''; }
  if (location.hash) history.replaceState(null, '', location.pathname + location.search);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const display = value => { if (value === null || value === undefined || value === '') return 'Bilinmiyor'; if (typeof value === 'object' && 'present' in value) return value.present === false ? 'Tanımlı değil (sistem varsayılanı)' : value.present === null ? 'Okunamadı' : String(value.value ?? 'Bilinmiyor'); return typeof value === 'object' ? JSON.stringify(value) : ({'disabled-user':'Devre dışı','enabled':'Etkin','default':'Sistem varsayılanı','running':'Çalışıyor','stopped':'Durmuş','installed':'Kurulu','absent':'Kurulu değil'}[value] || String(value)); };
  const date = value => { if (!value) return ''; const d = new Date(value); return Number.isNaN(d.valueOf()) ? String(value) : d.toLocaleString('tr-TR', {dateStyle:'medium',timeStyle:'short'}); };
  const statusLabels = { succeeded:'Tamamlandı', completed:'Tamamlandı', applied:'Tamamlandı', success:'Tamamlandı', failed:'Başarısız', partial:'Kısmen tamamlandı', rolled_back:'Geri alındı', running:'Sürüyor', queued:'Sırada', conflict:'Çakışma', dry_run:'Ön izleme', verified:'Doğrulandı', pending:'Uygulanmadı', interrupted:'Kesintiye uğradı', unreadable:'Kayıt okunamadı' };
  function notice(message, kind = 'success') { const node = $('#notice'); node.textContent = message; node.className = `notice ${kind}`; node.hidden = false; if (kind !== 'success' && !$('#plan-dialog').open) node.scrollIntoView({block:'start',behavior:'instant'}); }
  function page(name, focus = true) {
    if (!$('#page-' + name)) return;
    state.page = name; $$('.page').forEach(node => node.hidden = node.id !== `page-${name}` || !state.token);
    $$('.nav-button').forEach(node => { const active = node.dataset.page === name; node.classList.toggle('active', active); if (active) node.setAttribute('aria-current','page'); else node.removeAttribute('aria-current'); });
    if (focus) { $('#main').focus({preventScroll:true}); window.scrollTo({top:0,behavior:'instant'}); }
  }
  function setBusy(busy, title = '', detail = '') {
    state.busy = busy; $('#job-panel').hidden = !busy; $('#job-title').textContent = title; $('#job-detail').textContent = detail || 'Lütfen bu pencereyi açık tut.';
    $$('button, input, select').forEach(node => {
      if (node.closest('nav') || node.hasAttribute('data-goto') || node.id === 'connection-shortcut') return;
      if (busy) { node.dataset.preBusyDisabled = String(node.disabled); node.disabled = true; }
      else if ('preBusyDisabled' in node.dataset) { node.disabled = node.dataset.preBusyDisabled === 'true'; delete node.dataset.preBusyDisabled; }
    });
  }
  async function api(path, body) {
    const response = await fetch(path, {method:body === undefined ? 'GET':'POST', headers:{'Authorization':`Bearer ${state.token}`, ...(body === undefined ? {} : {'Content-Type':'application/json'})}, ...(body === undefined ? {} : {body:JSON.stringify(body)}), cache:'no-store'});
    let data; try { data = await response.json(); } catch (_) { throw new Error('Sunucudan geçerli bir yanıt alınamadı. TVCare’in çalıştığından emin ol.'); }
    if (!response.ok) { if (response.status === 401) throw new Error('Oturum anahtarı geçersiz veya süresi dolmuş. Terminaldeki tam TVCare bağlantısını yeniden aç.'); throw new Error(typeof data.error === 'object' ? data.error.message || JSON.stringify(data.error) : data.error || `İşlem başarısız (${response.status}).`); }
    return data;
  }
  async function job(path, body, label) {
    if (state.busy) throw new Error('Önce devam eden işlemin bitmesini bekle.');
    setBusy(true,label);
    try {
      const response = await api(path,body); let item = response.job || response;
      if (!item.id || !item.status) return item;
      let failures = 0;
      while (['queued','running','pending'].includes(item.status)) {
        await new Promise(resolve => setTimeout(resolve,700));
        try { const updated = await api(`/api/jobs/${encodeURIComponent(item.id)}`); item = updated.job || updated; failures = 0; }
        catch (error) { failures++; if (failures >= 4) throw new Error('İşlem durumuna ulaşılamıyor. İşlem sunucuda sürüyor olabilir; tekrar uygulamadan önce geçmişi kontrol et. ' + error.message); }
        const latest = item.logs?.at(-1); if (latest) $('#job-detail').textContent = typeof latest === 'string' ? latest : latest.message || JSON.stringify(latest);
      }
      if (!['succeeded','completed','success'].includes(item.status)) throw new Error(typeof item.error === 'object' ? item.error.message || JSON.stringify(item.error) : item.error || 'İşlem tamamlanamadı. Ayrıntılar için işlem geçmişini kontrol et.');
      return item.result;
    } finally { setBusy(false); }
  }
  function run(handler) { return async event => { try { await handler(event); } catch(error) { notice(error.message || String(error),'error'); } }; }
  function devices(items = []) {
    if (!Array.isArray(items)) items = [];
    $('#devices-list').innerHTML = items.length ? items.map(item => {
      const serial = item.serial || item.id; const available = ['device','online'].includes(item.state || item.status || 'device');
      const name = item.model || item.name || serial; const detail = item.state || item.status || 'device';
      return `<div class="device-row"><div><strong>${escape(name)}</strong><p>${escape(serial)} · ${escape(detail === 'device' ? 'Bağlantı hazır' : detail === 'unauthorized' ? 'TV’de izin bekleniyor' : detail === 'offline' ? 'Çevrimdışı' : detail)}</p></div><button class="button secondary compact inspect-device" data-serial="${escape(serial)}" ${available ? '' : 'disabled'}>Seç ve kontrol et</button></div>`;
    }).join('') : '<p class="empty-copy">Cihaz bulunamadı. TV’nin adresini girerek bağlantı kur.</p>';
    $$('.inspect-device').forEach(button => button.addEventListener('click',run(() => inspect(button.dataset.serial))));
  }
  async function refreshStatus() {
    const data = await api('/api/status');
    $('#version').textContent = `TVCare ${data.version || ''}`; $('#demo-banner').hidden = !data.demo;
    const adb = data.adb || {}; $('#adb-status').textContent = data.demo ? 'Örnek modunda bağlantı simüle edilir.' : adb.available ? 'ADB hazır. Cihazını seçerek bilgi kontrolünü başlat.' : 'ADB bulunamadı. Windows’ta Install-Requirements.cmd dosyasını çalıştırıp TVCare’i yeniden aç. macOS/Linux için hızlı başlangıç rehberindeki Platform Tools adımlarını izle.';
    $('#adb-error').hidden = !adb.error; $('#adb-error').textContent = adb.error ? 'ADB hata ayrıntısı: ' + adb.error : '';
    devices(data.devices); if (data.history) { state.history = data.history; renderHistory(); }
    const pending = (data.jobs || []).filter(item => ['queued','running'].includes(item.status));
    if (pending.length) notice('Sunucuda devam eden bir işlem var. Yeniden işlem başlatmadan önce tamamlanmasını ve geçmişi kontrol et.','warning');
  }
  async function discover() {
    const data = await api('/api/discover'); devices(data.devices);
    $('#discovery-services').textContent = data.services?.length ? 'Ağda görünen servisler: ' + data.services.map(item => typeof item === 'string' ? item : item.endpoint || item.address || item.name || JSON.stringify(item)).join(', ') : '';
  }
  async function inspect(serial) {
    const result = await job('/api/inspect',{serial},'TV’nin durumu okunuyor');
    state.serial = serial; state.inspection = result; renderInspection(); page('overview');
    notice('Cihaz kontrolü tamamlandı. Bu adımda ayarlar değiştirilmedi.');
  }
  const pick = (object, keys) => keys.map(key => object?.[key]).find(value => value !== undefined && value !== null);
  function bytes(value) { if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'Bilinmiyor'; const n = Number(value); return n >= 1073741824 ? (n / 1073741824).toLocaleString('tr-TR',{maximumFractionDigits:1})+' GB' : (n / 1048576).toLocaleString('tr-TR',{maximumFractionDigits:0})+' MB'; }
  function metric(label, value, foot, percent) { return `<article class="metric"><span class="metric-label">${escape(label)}</span><strong class="metric-value">${escape(value)}</strong><span class="metric-foot">${escape(foot)}</span>${Number.isFinite(percent) ? `<progress class="meter" max="100" value="${Math.max(0,Math.min(percent,100))}" aria-label="${escape(label)}: yüzde ${Math.round(percent)}"></progress>` : ''}</article>`; }
  function renderInspection() {
    const data = state.inspection || {}, id = data.identity || {}, health = data.health || {};
    $('#inspection-summary').textContent = 'Cihaz bilgileri güncellendi';
    const writable = data.capabilities?.is_tv !== false && data.capabilities?.stable_identity !== false && data.capabilities?.owner_user !== false;
    const maker = id.manufacturer || id.brand || ''; $('#device-title').textContent = id.model && id.model.toLowerCase().startsWith(maker.toLowerCase()) ? id.model : [maker,id.model].filter(Boolean).join(' ') || state.serial;
    $('#welcome-panel').hidden = true; $('#device-overview').hidden = false; $('#refresh-inspect').disabled = false; $('#maintenance-gate').hidden = writable; $('#maintenance-content').hidden = !writable;
    $('#maintenance-gate h2').textContent = writable ? 'Önce TV’yi kontrol edelim.' : 'Bu cihazda yalnızca tanı kullanılabilir.';
    $('#maintenance-gate p').textContent = writable ? 'Uygun bakım seçenekleri, seçtiğin cihazın bilgileri okunduktan sonra açılır.' : data.capabilities?.is_tv === false ? 'Cihaz Android TV / Google TV olarak doğrulanamadı. Ayar değişiklikleri kapalıdır.' : data.capabilities?.owner_user === false ? 'TV’nin ana kullanıcı profiline (kullanıcı 0) geç ve cihazı yeniden kontrol et. Misafir veya diğer profillerde bakım uygulanmaz.' : 'Kalıcı cihaz kimliği okunamadı. Yanlış cihaza işlem yapmamak için ayar değişiklikleri kapalıdır.';
    $('#inspection-time').textContent = date(data.inspected_at || data.created_at || data.timestamp || new Date().toISOString());
    const mem = health.memory || {}, disk = health.storage || health.disk || {};
    const memTotal = mem.total_kb != null ? mem.total_kb * 1024 : pick(mem,['total_bytes','total']), memAvailable = mem.available_kb != null ? mem.available_kb * 1024 : pick(mem,['available_bytes','available']);
    const diskTotal = disk.total_kb != null ? disk.total_kb * 1024 : pick(disk,['total_bytes','total']), diskFree = disk.available_kb != null ? disk.available_kb * 1024 : pick(disk,['free_bytes','available_bytes','available','free']);
    const uptime = pick(health,['uptime_seconds','uptime']);
    const uptimeText = typeof uptime === 'number' ? `${Math.floor(uptime / 3600)} sa ${Math.floor(uptime % 3600 / 60)} dk` : uptime || 'Bilinmiyor';
    $('#health-metrics').innerHTML = metric('Kullanılabilir bellek',bytes(memAvailable),memTotal ? `${bytes(memTotal)} toplam · Anlık ölçüm` : 'Bellek ölçümü alınamadı',memTotal && memAvailable != null ? 100*memAvailable/memTotal : NaN) + metric('Boş depolama',bytes(diskFree),diskTotal ? `${bytes(diskTotal)} toplam depolama` : 'Depolama ölçümü alınamadı',diskTotal && diskFree != null ? 100*diskFree/diskTotal : NaN) + metric('Açık kalma süresi',uptimeText,'Son yeniden başlatmadan bu yana',NaN);
    const profile = id.profile || data.profile; const supported = profile === 'tcl_beyondtv4_rtd288o_a11';
    $('#profile-tag').textContent = supported ? 'TCL cihaz profili' : 'Genel cihaz profili';
    $('#identity-list').innerHTML = [['Üretici',id.manufacturer || id.brand],['Model',id.model],['Android',id.android || id.android_version || id.android_release || id.release],['Donanım',id.platform || id.hardware || id.board],['Cihaz profili',supported ? 'TCL / Realtek özel profili' : 'Genel Android TV']].map(([label,value]) => `<div><dt>${escape(label)}</dt><dd>${escape(display(value))}</dd></div>`).join('');
    const notes = [...(Array.isArray(health.warnings) ? health.warnings : []), ...(Array.isArray(data.warnings) ? data.warnings : []), ...(data.read_errors || []).map(item => `${item.source || 'Ölçüm'}: ${item.error || 'Bilgi okunamadı'}`), ...(health.read_errors || []).map(item => `${item.source || 'Ölçüm'}: ${item.error || 'Bilgi okunamadı'}`)];
    $('#health-notes').textContent = notes.length ? notes.map(n => typeof n === 'string' ? n : n.message || JSON.stringify(n)).join(' ') : 'Bu değerler anlık ölçümlerdir. Boş belleğin az olması tek başına bir sorun olduğunu göstermez. Görüntü, ses ve kumanda davranışı TV’de kontrol edilmelidir.';
    $('#guard-tag').textContent = supported ? 'Cihaz profili eşleşti' : 'Destek doğrulanmadı';
    $('#guard-eligibility').textContent = supported ? 'Bu cihaz için profil bulundu. Kurulum planı, ilgili hata kanıtını ve gerekli izinleri ayrıca kontrol eder.' : 'Bu çözüm yalnızca doğrulanmış TCL / Realtek profili için kullanılabilir. Genel bakım seçeneklerini kullanabilirsin.';
    $$('.guard-action').forEach(button => button.disabled = !supported || !writable);
    renderMaintenance(); renderHistory();
  }
  function packageItems() { const packages = state.inspection?.packages || []; return Array.isArray(packages) ? packages : Object.entries(packages).map(([name, value]) => typeof value === 'object' ? {package:name,...value} : {package:name,state:value}); }
  function renderMaintenance() {
    $('input[name="animation"][value="keep"]').checked = true;
    const settings = state.inspection.settings || {}, globals = settings.global || settings;
    $('#current-animations').textContent = 'Mevcut değerler · Pencere: '+display(globals.window_animation_scale)+' · Geçiş: '+display(globals.transition_animation_scale)+' · Animatör: '+display(globals.animator_duration_scale);
    const items = packageItems(); $('#package-count').textContent = `${items.filter(item => item.eligible).length} bakım seçeneği`;
    $('#package-list').innerHTML = items.length ? items.map((item,index) => {
      const name = item.id || item.package || item.name || item.package_name; const present = item.installed !== false && item.present !== false;
      const eligible = item.eligible !== false && item.supported !== false && present;
      const disabled = item.enabled === false || ['disabled-user','disabled','disabled_user'].includes(item.state || item.current_state);
      return `<div class="package-item"><input type="checkbox" id="pkg-${index}" data-package="${escape(name)}" data-value="${disabled ? 'enabled' : 'disabled-user'}" ${eligible ? '' : 'disabled'}><label for="pkg-${index}"><strong>${escape(item.label || item.title || name)} ${!eligible ? '' : disabled ? '— Etkinleştir' : '— Devre dışı bırak'}</strong><p>${escape(item.description || 'Bu uygulamanın TV üzerindeki işlevini bildiğinden emin ol.')}</p>${item.warning ? `<p>${escape(item.warning)}</p>`:''}${!eligible ? `<p>${escape(item.reason || item.ineligible_reason || (!present ? 'Bu TV’de kurulu değil.' : 'Bu cihazda değiştirilemez.'))}</p>`:''}<span class="package-id">${escape(name)}</span></label><span class="pill neutral">${!present ? 'Kurulu değil' : (item.state === 'unknown' || item.enabled === null) ? 'Durum bilinmiyor' : disabled ? 'Devre dışı' : 'Etkin'}</span></div>`;
    }).join('') : '<p class="empty-copy">Bu cihazda yönetilebilir tanımlı bir uygulama bulunamadı.</p>';
    const excluded = $$('#package-list .package-item').filter(row => $('input',row).disabled);
    if (excluded.length) { const details = document.createElement('details'); details.className = 'excluded-packages'; const summary = document.createElement('summary'); summary.textContent = `${excluded.length} korunan veya desteklenmeyen uygulamayı göster`; details.append(summary); excluded.forEach(row => details.append(row)); $('#package-list').append(details); }
    $$('#package-list input').forEach(input => input.addEventListener('change',updateSelection));
    renderComponents(); updateSelection();
  }
  function renderComponents() {
    $('#component-panel')?.remove();
    const launchers = state.inspection.launchers || [], savers = state.inspection.screensavers || [];
    if (!launchers.length && !savers.length) return;
    const panel = document.createElement('section'); panel.id = 'component-panel'; panel.className = 'panel';
    panel.innerHTML = '<div class="panel-heading"><div><span class="eyebrow">KİŞİSELLEŞTİRME</span><h2>Ana ekran ve ekran koruyucu</h2></div><span class="pill neutral">Kurulu seçenekler</span></div><p class="muted">Yalnızca TV’de kurulu ve doğrulanmış bileşenler gösterilir.</p>' + [[launchers,'launcher-select','Ana ekran uygulaması'],[savers,'screensaver-select','Ekran koruyucu']].filter(([list]) => list.length).map(([list,id,label]) => `<div class="component-choice"><label for="${id}">${label}</label><select id="${id}"><option value="">Olduğu gibi bırak</option>${list.map(item => `<option value="${escape(item.component)}">${escape(item.label || item.component)}${item.current ? ' (şu anki)' : ''}</option>`).join('')}</select></div>`).join('');
    $('#guard-panel').before(panel); $$('select',panel).forEach(select => select.addEventListener('change',updateSelection));
  }
  function actions() {
    const list = [], animation = $('input[name="animation"]:checked')?.value;
    if (animation && animation !== 'keep') for (const key of ['window_animation_scale','transition_animation_scale','animator_duration_scale']) list.push({type:'setting',namespace:'global',key,value:animation});
    $$('#package-list input:checked').forEach(input => list.push({type:'package',package:input.dataset.package,value:input.dataset.value}));
    const launcher = $('#launcher-select')?.value, saver = $('#screensaver-select')?.value;
    if (launcher) list.push({type:'launcher',component:launcher});
    if (saver) list.push({type:'setting',namespace:'secure',key:'screensaver_components',value:saver});
    return list;
  }
  function updateSelection() { const count = actions().length; $('#selection-count').textContent = count ? `${count} değişiklik seçildi` : 'Değişiklik seçilmedi'; $('#review-plan').disabled = !count || state.busy; }
  function showPlan(plan) {
    if (!plan?.id) throw new Error('Sunucu geçerli bir değişiklik planı döndürmedi.');
    state.plan = plan; $('#plan-title').textContent = plan.kind === 'rollback' ? 'Geri alma planını incele.' : 'Değişiklikleri incele.';
    $('#plan-device').textContent = `${plan.device?.model || state.inspection?.identity?.model || 'Seçili TV'} · ${date(plan.created_at)}`;
    $('#plan-warnings').innerHTML = (plan.warnings || []).map(warning => `<p class="plan-warning">${escape(typeof warning === 'string' ? warning : warning.message || JSON.stringify(warning))}</p>`).join('');
    $('#plan-actions').innerHTML = (plan.actions || []).map(action => `<div class="plan-action"><strong>${escape(action.label || action.key || action.package || action.type)}</strong><div><span>ÖNCEKİ DURUM</span><code>${escape(display(action.before))}</code></div><div class="after"><span>SONRAKİ DURUM</span><code>${escape(display(action.after ?? action.value))}</code></div></div>`).join('') || '<p class="inline-note">Uygulanacak bir değişiklik yok. Cihaz zaten seçilen durumda olabilir.</p>';
    $('#confirm-checkbox').checked = false; $('#confirm-plan').disabled = true; $('#plan-dialog').showModal(); $('#close-plan').focus();
  }
  async function refreshHistory() { const data = await api('/api/history'); state.history = Array.isArray(data) ? data : data.history || []; renderHistory(); }
  function renderHistory() {
    $('#history-list').innerHTML = state.history.length ? state.history.map((item,index) => `<article class="panel"><div class="history-header"><div><h2>${escape(item.kind === 'rollback' ? 'Önceki duruma dönüş' : 'TV bakımı')} · ${escape(item.device?.model || 'TV')}</h2><p>${escape(date(item.created_at))} · ${escape(item.id)}</p></div><span class="pill ${['failed','partial','conflict','interrupted','unreadable'].includes(item.status) ? 'warning' : 'neutral'}">${escape(item.rolled_back_by ? 'Geri alındı' : statusLabels[item.status] || item.status)}</span></div>${item.error ? `<p class="plan-warning">${escape(typeof item.error === 'string' ? item.error : JSON.stringify(item.error))}</p>` : ''}<ul class="history-actions">${(item.actions || []).map(action => `<li>${escape(action.label || action.key || action.package || action.type)}${action.status ? ' · '+escape(statusLabels[action.status] || action.status) : ''}${action.error ? ' — '+escape(typeof action.error === 'string' ? action.error : JSON.stringify(action.error)) : ''}</li>`).join('')}</ul><div class="button-row"><button class="button secondary compact rollback-button" data-index="${index}" ${state.serial && !state.busy && !item.rolled_back_by && item.kind !== 'rollback' && !['unreadable','running','queued'].includes(item.status) ? '' : 'disabled'}>Geri alma planını incele</button><button class="text-button export-transaction" data-index="${index}">Raporu indir ↓</button></div>${item.rolled_back_by ? '<p class="field-hint">Bu işlem daha önce geri alındı.</p>' : item.kind === 'rollback' ? '<p class="field-hint">Geri alma kaydı tekrar geri alınamaz. Yeni değişiklik için bakım seçeneklerini kullan.</p>' : !state.serial ? '<p class="field-hint">Geri almak için önce işlemin yapıldığı TV’yi bağlayıp seç.</p>' : ''}</article>`).join('') : '<div class="panel empty-state"><h2>Henüz bir işlem yok.</h2><p>Uyguladığın bakım işlemleri ve önceki durumları burada görünür.</p><button class="button secondary" data-goto="maintenance">Bakım seçeneklerini gör →</button></div>';
    $$('.rollback-button').forEach(button => button.addEventListener('click',run(async () => showPlan(await job('/api/rollback-plan',{transaction_id:state.history[button.dataset.index].id,serial:state.serial},'Geri alma planı hazırlanıyor')))));
    $$('.export-transaction').forEach(button => button.addEventListener('click',run(() => download(`/api/report/${encodeURIComponent(state.history[button.dataset.index].id)}`,'tvcare-islem-raporu.json'))));
    $$('#history-list [data-goto]').forEach(button => button.addEventListener('click',() => page(button.dataset.goto)));
  }
  async function download(path,name) { const data = await api(path); const url = URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})); const link = document.createElement('a'); link.href = url; link.download = name; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url),1000); notice('Rapor indirildi. Paylaşmadan önce içeriğini gözden geçir.'); }
  $$('.nav-button').forEach(button => button.addEventListener('click',run(async () => { page(button.dataset.page); if (button.dataset.page === 'history' && state.token) await refreshHistory(); })));
  $$('[data-goto]').forEach(button => button.addEventListener('click',() => page(button.dataset.goto)));
  $('.brand').addEventListener('click',event => { event.preventDefault(); page('overview'); });
  $('#connection-shortcut').addEventListener('click',() => page('connection'));
  $('#discover').addEventListener('click',run(discover));
  $('#connect-form').addEventListener('submit',run(async event => { event.preventDefault(); const endpoint = $('#endpoint').value.trim(); await job('/api/connect',{endpoint},'TV’ye bağlanılıyor'); notice('Bağlantı isteği tamamlandı. TV’de izin ekranı varsa onayla, ardından cihazını seç.'); await discover(); }));
  $('#pair-form').addEventListener('submit',run(async event => { event.preventDefault(); const endpoint = $('#pair-endpoint').value.trim(), code = $('#pair-code').value.trim(); await job('/api/pair',{endpoint,code},'TV ile eşleştiriliyor'); $('#pair-code').value = ''; notice('Eşleştirme tamamlandı. TV’nin bağlantı portunu kullanarak bağlantı kur.'); await discover(); }));
  $('#refresh-inspect').addEventListener('click',run(() => inspect(state.serial)));
  $$('input[name="animation"]').forEach(input => input.addEventListener('change',updateSelection));
  $('#review-plan').addEventListener('click',run(async () => showPlan(await job('/api/plan',{serial:state.serial,actions:actions()},'Değişiklik planı hazırlanıyor'))));
  $('#close-plan').addEventListener('click',() => $('#plan-dialog').close()); $('#cancel-plan').addEventListener('click',() => $('#plan-dialog').close());
  $('#confirm-checkbox').addEventListener('change',() => $('#confirm-plan').disabled = !$('#confirm-checkbox').checked || !(state.plan?.actions?.length));
  $('#confirm-plan').addEventListener('click',run(async () => {
    if (!$('#confirm-checkbox').checked || !state.plan || state.busy) return;
    const planId = state.plan.id; $('#plan-dialog').close();
    try {
      const result = await job('/api/apply',{plan_id:planId,confirmed:true},'Onayladığın değişiklikler uygulanıyor'); state.plan = null;
      if (!['succeeded','completed','success'].includes(result?.status)) notice('İşlem tamamen uygulanamadı. Hangi adımların değiştiğini işlem geçmişinden kontrol et.','warning');
      else notice('İşlem tamamlandı. Sonucu TV’de kontrol et; gerekirse işlem geçmişinden geri al.');
      await refreshHistory(); page('history');
      // An inspection is deliberately requested by the user; stale choices must not be reused after a mutation.
      state.inspection = null; $('#inspection-summary').textContent = 'Önceki ölçüm · Bakım sonrası yeniden kontrol et'; $('#maintenance-content').hidden = true; $('#maintenance-gate').hidden = false; $('#maintenance-gate h2').textContent = 'Bakım sonrası yeniden kontrol edelim.'; $('#maintenance-gate p').textContent = 'Güncel seçenekler için genel bakıştan TV’yi yeniden kontrol et.'; $('#refresh-inspect').disabled = false;
    } catch(error) { await refreshHistory().catch(() => {}); page('history'); throw error; }
  }));
  $$('.guard-action').forEach(button => button.addEventListener('click',run(async () => { const result = await job('/api/guard/plan',{serial:state.serial,operation:button.dataset.operation},'Koruyucu durumu kontrol ediliyor'); if (button.dataset.operation === 'status') { const guardStates = {running:'Koruyucu çalışıyor.',stopped:'Koruyucu kurulu, bekçi şu anda çalışmıyor.',stopping:'Koruyucu durduruluyor. Biraz sonra yeniden kontrol et.',unknown:'Koruyucu kurulu; bekçinin çalışma durumu doğrulanamadı.',not_installed:'Koruyucu bu TV’de kurulu değil.'}; $('#guard-result').textContent = (guardStates[result?.state] || 'Koruyucu durumu doğrulanamadı.') + (result?.checked_at ? ' Son kontrol: ' + date(result.checked_at) + '.' : '') + ' Bu sonuç yalnızca kontrol anını gösterir.'; $('#guard-result').hidden = false; } else showPlan(result); })));
  $('#refresh-history').addEventListener('click',run(refreshHistory));
  $('#export-inspection').addEventListener('click',run(() => download('/api/report','tvcare-tani-raporu.json')));
  window.addEventListener('beforeunload',event => { if (state.busy) { event.preventDefault(); event.returnValue = ''; } });
  if (!state.token) { $('#auth-gate').hidden = false; page('overview',false); $('#adb-status').textContent = 'Önce geçerli oturum bağlantısını aç.'; }
  else refreshStatus().catch(error => notice(error.message,'error'));
})();
