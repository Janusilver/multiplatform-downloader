// 多平台 Cookie 导出：抖音 / 小红书 / 快手（Netscape 格式，含 HttpOnly）
const SITES = {
  'btn-dy':  { domain: '.douyin.com',       file: 'douyin_cookies.txt',  name: '抖音' },
  'btn-xhs': { domain: '.xiaohongshu.com',  file: 'xhs_cookies.txt',     name: '小红书' },
  'btn-ks':  { domain: '.kuaishou.com',     file: 'kuaishou_cookies.txt', name: '快手' },
};

async function exportSite(btnId) {
  const status = document.getElementById('status');
  const site = SITES[btnId];
  try {
    const cookies = await chrome.cookies.getAll({ domain: site.domain });
    if (!cookies.length) {
      status.textContent = `没找到${site.name} Cookie。请先打开并登录对应网站（${site.domain.replace(/^\./, 'www.')}），再点一次。`;
      return;
    }
    const lines = ['# Netscape HTTP Cookie File'];
    for (const c of cookies) {
      if (!c.name) continue; // 个别平台有无名字的畸形 Cookie，导出会破坏格式，跳过
      const secure = c.secure ? 'TRUE' : 'FALSE';
      const expires = Math.floor(c.expirationDate || 0);
      const row = [c.domain, 'TRUE', c.path, secure, expires, c.name, c.value].join('\t');
      // HttpOnly Cookie 按 Netscape 格式加前缀，本地工具才能识别
      lines.push((c.httpOnly ? '#HttpOnly_' : '') + row);
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    await chrome.downloads.download({ url, filename: site.file });
    status.textContent = `✅ 已导出 ${cookies.length} 条 ${site.name} Cookie → ${site.file}\n放到 exe / 项目根目录即可。`;
  } catch (e) {
    status.textContent = '出错: ' + e.message;
  }
}

for (const id of Object.keys(SITES)) {
  document.getElementById(id).addEventListener('click', () => exportSite(id));
}
