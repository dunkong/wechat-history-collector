const $ = id => document.getElementById(id);
const api = async (path, opts={}) => {
  const r = await fetch(path, {headers:{'Content-Type':'application/json'}, ...opts});
  return r.json();
};
const post = (path, body={}) => api(path, {method:'POST', body:JSON.stringify(body)});
let captureTimer = null, progressTimer = null, contentTimer = null;


$('btnSeed').onclick = async () => {
  const url = $('seedUrl').value.trim();
  if (!url) return setLine('seedResult','请先粘贴文章链接','err');
  setLine('seedResult','解析中…','');
  const res = await post('/api/seed', {url});
  if (res.ok) {
    setLine('seedResult','✓ 已识别公众号，账号标识：'+res.biz,'ok');
    $('nameRow').style.display = 'flex';
    $('captureCard').scrollIntoView({behavior:'smooth'});
  } else setLine('seedResult','✗ '+res.error,'err');
};
$('btnName').onclick = async () => {
  await post('/api/account/name', {name:$('acctName').value.trim()});
  setLine('seedResult','✓ 名称已保存','ok');
};

$('btnCapture').onclick = async () => {
  setLine('captureStatus','正在启动抓包与系统代理…','');
  const res = await post('/api/capture/start');
  if (!res.ok) return setLine('captureStatus','✗ '+res.mitm+' / '+res.proxy,'err');
  $('proxyTip').style.display='block';
  $('proxyTip').innerHTML = '系统代理已开启（'+ (res.proxy||'') +'）。' +
    '如微信里点链接后一直检测不到，请确认已安装 mitmproxy 证书：浏览器打开 <a href="http://mitm.it" target="_blank">http://mitm.it</a> 安装 Windows 证书。';
  if (res.profile_url) {
    $('profileBox').style.display='block';
    $('profileUrl').value = res.profile_url;
  }
  setLine('captureStatus','抓包已启动，等待在微信里点开链接…','');
  checkCapture();
};
async function checkCapture(){
  const st = await api('/api/capture/status');
  let bits = [];
  bits.push(st.mitm_running ? '● 抓包进程：运行中' : '○ 抓包进程：未运行');
  bits.push(st.proxy_on ? '● 系统代理：已开启' : '○ 系统代理：未开启');
  bits.push(st.auth_fresh ? '● 凭证：已捕获（新鲜）' : (st.auth_captured ? '● 凭证：已捕获但可能过期' : '○ 凭证：等待中'));
  $('captureStatus').textContent = bits.join('　|　');

  renderNetBanner(st);

  // 抓包进程在跑但还没拿到凭证 → 自动显示可复制的微信链接
  if (st.mitm_running && !st.auth_fresh && st.profile_url) {
    $('profileBox').style.display = 'block';
    if (!$('profileUrl').value) $('profileUrl').value = st.profile_url;
  }

  // 危险状态：代理开着但抓包进程没跑 → 提示并引导急救
  if (st.proxy_on && st.proxy_points_to_us && !st.mitm_running) {
    $('netBanner').className = 'net-banner bad';
    $('netBanner').textContent = '⚠ 系统代理已开启，但抓包进程未运行——这会导致无法上网。请点「一键恢复网络」，或等待自动恢复。';
    $('netBanner').style.display = 'block';
  }
  if (st.auth_fresh) {
    clearInterval(captureTimer);
    $('captureWait').textContent = '✓ 凭证已捕获！现在去第 3 步采集。';
    setLine('captureStatus','✓ 凭证捕获成功，可以进行采集','ok');
  }
}

function renderNetBanner(st){
  const b = $('netBanner');
  if (st.auto_recovered) {
    b.className = 'net-banner warn';
    b.textContent = 'ℹ ' + st.auto_recovered;
    b.style.display = 'block';
    return;
  }
  if (!st.proxy_on) {
    b.className = 'net-banner ok';
    b.textContent = '✓ 网络正常：系统代理未开启，可正常上网。';
    b.style.display = 'block';
  }
}
$('btnCopy').onclick = async () => {
  try { await navigator.clipboard.writeText($('profileUrl').value); $('btnCopy').textContent='已复制'; }
  catch(e){ $('profileUrl').select(); document.execCommand('copy'); $('btnCopy').textContent='已复制'; }
};
$('btnStop').onclick = async () => {
  const res = await post('/api/capture/stop');
  clearInterval(captureTimer);
  setLine('captureStatus','✓ '+res.msg,'ok');
  checkCapture();
};
$('btnReset').onclick = async () => {
  const res = await post('/api/network/reset');
  clearInterval(captureTimer);
  setLine('captureStatus','✓ '+res.msg,'ok');
  $('netBanner').className = 'net-banner ok';
  $('netBanner').textContent = '✓ '+res.msg;
  $('netBanner').style.display = 'block';
};

$('btnCollect').onclick = async () => {
  $('progressBar').parentElement.classList.add('show');
  setLine('collectResult','采集中…','');
  let maxPages = parseInt($('maxPages').value, 10);
  if (isNaN(maxPages) || maxPages < 0) maxPages = 500;
  if (maxPages === 0) maxPages = 3000; // 0 = 尽量拉全
  const res = await post('/api/collect', {max_pages:maxPages});
  if (!res.ok) return setLine('collectResult','✗ '+res.error,'err');
  $('btnCollect').disabled = true;
  $('btnCollectPause').style.display = '';
  $('btnCollectStop').style.display = '';
  $('btnCollectPause').textContent = '暂停';
  clearInterval(progressTimer);
  progressTimer = setInterval(async () => {
    const p = await api('/api/progress');
    if (p.paused) {
      $('progressText').textContent = `⏸ 已暂停（第 ${p.page} 页 · 累计 ${p.total} 篇）`;
      $('btnCollectPause').textContent = '继续';
    } else {
      $('btnCollectPause').textContent = '暂停';
      $('progressText').textContent = p.running ? `第 ${p.page} 页 · 本页 ${p.got} 篇 · 累计 ${p.total} 篇` : '';
    }
    $('progressBar').style.width = p.running ? Math.min(p.page*10, 95)+'%' : (p.done?'100%':'0%');
    if (!p.running) {
      clearInterval(progressTimer);
      $('btnCollect').disabled = false;
      $('btnCollectPause').style.display = 'none';
      $('btnCollectStop').style.display = 'none';
      if (p.stopped) setLine('collectResult',`⏹ 已停止：翻页 ${p.page} 页，已入库 ${p.total} 篇（保留）`,'');
      else if (p.error && !p.reached_end) setLine('collectResult','⚠ '+p.error,'err');
      else {
        const tail = p.reached_end ? '（已翻到微信返回没有更多）' : '';
        setLine('collectResult',`✓ 采集完成：翻页 ${p.page} 页，新增入库 ${p.total} 篇 ${tail}`,'ok');
      }
      loadArticles();
    }
  }, 1200);
};

$('btnCollectPause').onclick = async () => {
  const res = await post('/api/collect/pause');
  if (res.ok) $('btnCollectPause').textContent = res.action==='paused' ? '继续' : '暂停';
};
$('btnCollectStop').onclick = async () => {
  await post('/api/collect/stop');
  setLine('collectResult','正在停止…','');
};

// 演示模式：URL 带 ?demo=1 时用脱敏示例数据渲染，便于文档截图/快速预览，不读取真实数据库
const DEMO_MODE = new URLSearchParams(location.search).get('demo') === '1';
const DEMO_ROWS = [
  {id:1, publish_time:'2026-11-18 09:30', title:'示例文章：如何用 AI 提升写作效率', url:'https://mp.weixin.qq.com/', content_status:'ok'},
  {id:2, publish_time:'2026-11-15 20:10', title:'示例文章：一份给新手的入门指南', url:'https://mp.weixin.qq.com/', content_status:'ok'},
  {id:3, publish_time:'2026-11-12 08:00', title:'示例文章：聊聊最近的一点心得', url:'https://mp.weixin.qq.com/', content_status:'ok'},
  {id:4, publish_time:'2026-11-08 18:45', title:'示例文章：三个值得收藏的小技巧', url:'https://mp.weixin.qq.com/', content_status:''},
  {id:5, publish_time:'2026-11-03 12:20', title:'示例文章：从零开始完整实践记录', url:'https://mp.weixin.qq.com/', content_status:''},
  {id:6, publish_time:'2026-10-28 07:15', title:'示例文章：常见问题一次讲清楚', url:'https://mp.weixin.qq.com/', content_status:''},
];

async function loadArticles(kw=''){
  const rows = DEMO_MODE ? DEMO_ROWS : await api('/api/articles'+(kw?'?keyword='+encodeURIComponent(kw):''));
  $('stat').textContent = `共 ${rows.length} 篇` + (kw?'（搜索结果）':'');
  if (!rows.length) { $('tableWrap').innerHTML='<div style="padding:20px;color:#999;font-size:13px">暂无文章，先完成采集</div>'; return; }
  let h = '<table><thead><tr><th style="width:34px"><input type="checkbox" id="chkAll" title="全选/取消"></th><th style="width:120px">发布时间</th><th>标题</th><th style="width:78px">正文</th></tr></thead><tbody>';
  for (const r of rows) {
    const arc = r.content_status==='ok' ? '<span class="tag-ok">已归档</span>' : (r.content_status ? '<span class="tag-fail" title="'+esc(r.content_status)+'">失败</span>' : '<span class="tag-no">未抓</span>');
    h += `<tr><td><input type="checkbox" class="rowchk" value="${r.id}"></td><td>${esc(r.publish_time||'')}</td><td><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a></td><td>${arc}</td></tr>`;
  }
  $('tableWrap').innerHTML = h+'</tbody></table>';
  $('chkAll').onchange = e => document.querySelectorAll('.rowchk').forEach(c=>c.checked=e.target.checked);
}
function selectedIds(){ return Array.from(document.querySelectorAll('.rowchk:checked')).map(c=>parseInt(c.value,10)); }
const esc = s => String(s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

$('btnFetchContent').onclick = async () => {
  const ids = selectedIds();
  if (!ids.length) return setLine('contentResult','请先在上方表格勾选文章','err');
  const res = await post('/api/content/fetch', {ids});
  if (!res.ok) return setLine('contentResult','✗ '+res.error,'err');
  $('btnFetchContent').disabled = true;
  $('btnContentPause').style.display = '';
  $('btnContentStop').style.display = '';
  $('btnContentPause').textContent = '暂停';
  $('contentBarWrap').classList.add('show');
  setLine('contentResult',`抓取正文 0 / ${res.total}…`,'');
  clearInterval(contentTimer);
  contentTimer = setInterval(async () => {
    const p = await api('/api/content/progress');
    if (p.paused) {
      $('contentProgress').textContent = `⏸ 已暂停 ${p.done}/${p.total}`;
      $('btnContentPause').textContent = '继续';
    } else {
      $('btnContentPause').textContent = '暂停';
      $('contentProgress').textContent = `${p.done}/${p.total} 篇`;
    }
    $('contentBar').style.width = (p.total ? (p.done/p.total*100) : 0)+'%';
    if (!p.running && p.finished) {
      clearInterval(contentTimer);
      $('btnFetchContent').disabled = false;
      $('btnContentPause').style.display = 'none';
      $('btnContentStop').style.display = 'none';
      if (p.stopped) setLine('contentResult',`⏹ 已停止：抓取 ${p.done} 篇（成功 ${p.ok}，保留）`,'');
      else setLine('contentResult',`✓ 正文抓取完成：成功 ${p.ok} 篇，失败 ${p.fail} 篇`,'ok');
      loadArticles();
    }
  }, 1000);
};

$('btnContentPause').onclick = async () => {
  const res = await post('/api/content/pause');
  if (res.ok) $('btnContentPause').textContent = res.action==='paused' ? '继续' : '暂停';
};
$('btnContentStop').onclick = async () => {
  await post('/api/content/stop');
  setLine('contentResult','正在停止…','');
};

async function doArchive(kind){
  const kw = $('arcKw').value.trim();
  const res = await post('/api/export/archive', {keyword:kw});
  if (!res.ok) return alert(res.error);
  window.location.href = '/api/download?path='+encodeURIComponent(res[kind]);
}
$('btnArcHtml').onclick = () => doArchive('html');
$('btnArcZip').onclick = () => doArchive('zip');

function setLine(id, text, cls){ const e=$(id); e.textContent=text; e.className='result-line '+cls; }

$('btnSearch').onclick = () => loadArticles($('kw').value.trim());
$('kw').onkeydown = e => { if(e.key==='Enter') loadArticles($('kw').value.trim()); };

async function doExport(fmt){
  const res = await post('/api/export', {format:fmt});
  if (!res.ok) return alert(res.error);
  window.location.href = '/api/download?path='+encodeURIComponent(res.file);
}
$('btnXlsx').onclick=()=>doExport('xlsx');
$('btnCsv').onclick=()=>doExport('csv');
$('btnHtml').onclick=()=>doExport('html');
$('btnJson').onclick=()=>doExport('json');

// 页面加载时同步正在运行的任务状态（刷新后仍能显示暂停/停止按钮并继续轮询）
async function syncRunningTasks(){
  const cp = await api('/api/content/progress');
  if (cp.running && !contentTimer) {
    $('btnFetchContent').disabled = true;
    $('btnContentPause').style.display = ''; $('btnContentStop').style.display = '';
    $('contentBarWrap').classList.add('show');
    contentTimer = setInterval(async () => {
      const p = await api('/api/content/progress');
      $('contentProgress').textContent = p.paused ? `⏸ 已暂停 ${p.done}/${p.total}` : `${p.done}/${p.total} 篇`;
      $('contentBar').style.width = (p.total ? (p.done/p.total*100) : 0)+'%';
      if (!p.running && p.finished) {
        clearInterval(contentTimer); contentTimer = null;
        $('btnFetchContent').disabled = false;
        $('btnContentPause').style.display = 'none'; $('btnContentStop').style.display = 'none';
        setLine('contentResult', p.stopped ? `⏹ 已停止（保留已抓）` : `✓ 正文抓取完成：成功 ${p.ok} 篇`, 'ok');
        loadArticles();
      }
    }, 1000);
  }
  const pp = await api('/api/progress');
  if (pp.running && !progressTimer) {
    $('btnCollect').disabled = true;
    $('btnCollectPause').style.display = ''; $('btnCollectStop').style.display = '';
  }
}
loadArticles();
checkCapture();
syncRunningTasks();
setInterval(checkCapture, 3000);
