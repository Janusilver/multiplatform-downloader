document.getElementById('btn').addEventListener('click', async () => {
  const status = document.getElementById('status');
  try {
    const cookies = await chrome.cookies.getAll({ domain: '.douyin.com' });
    if (!cookies.length) {
      status.textContent = '没找到抖音 Cookie。请先打开并登录 www.douyin.com，再点一次。';
      return;
    }
    const lines = ['# Netscape HTTP Cookie File'];
    for (const c of cookies) {
      if (!c.name) continue; // 抖音有个别无名字的畸形 Cookie，导出会破坏格式，跳过
      const secure = c.secure ? 'TRUE' : 'FALSE';
      const expires = Math.floor(c.expirationDate || 0);
      const row = [c.domain, 'TRUE', c.path, secure, expires, c.name, c.value].join('\t');
      // HttpOnly Cookie 按 Netscape 格式加前缀，本地工具才能识别
      lines.push((c.httpOnly ? '#HttpOnly_' : '') + row);
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    await chrome.downloads.download({ url, filename: 'douyin_cookies.txt' });
    status.textContent = `✅ 已导出 ${cookies.length} 条 Cookie → douyin_cookies.txt`;
  } catch (e) {
    status.textContent = '出错: ' + e.message;
  }
});
