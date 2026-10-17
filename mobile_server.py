import os
import sys
import json
import time
import socket
import qrcode
import requests
from flask import Flask, request, jsonify, render_template_string

# 确保 UTF-8
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from bilibili_user_sync import BilibiliUserSync, COOKIE_FILE
from ai_classifier import EnhancedSemanticClassifier, CATEGORIES_FILE
from bilibili_folder_manager import BilibiliFolderManager

app = Flask(__name__)

folder_manager = BilibiliFolderManager()
user_sync = folder_manager.sync_client
classifier = EnhancedSemanticClassifier()

# 存储临时扫描状态
current_scan_status = {
    "status": "idle",
    "progress": 0,
    "current_text": "",
    "results": {},
    "total": 0
}

MOBILE_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>BiliSort - 手机整理助手</title>
    <!-- PWA 配置，支持添加到手机主屏幕成为 App -->
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="theme-color" content="#18191c">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
        body { background: #121214; color: #fff; padding: 16px; padding-bottom: 50px; }
        .header { text-align: center; padding: 15px 0 20px; }
        .header h1 { font-size: 22px; font-weight: 700; color: #00AEEC; display: flex; align-items: center; justify-content: center; gap: 8px; }
        .header p { font-size: 13px; color: #888; margin-top: 4px; }
        
        .card { background: #1E1E22; border-radius: 16px; padding: 16px; margin-bottom: 16px; border: 1px solid #2B2B30; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
        .card-title { font-size: 15px; font-weight: 600; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; }
        
        .user-status { font-size: 14px; display: flex; align-items: center; gap: 6px; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
        .online { background: #00C853; }
        .offline { background: #FF5252; }

        .btn { width: 100%; border: none; border-radius: 12px; padding: 14px; font-size: 15px; font-weight: 600; cursor: pointer; text-align: center; transition: 0.2s; }
        .btn-primary { background: #00AEEC; color: #fff; }
        .btn-primary:active { background: #0093C7; }
        .btn-success { background: #00C853; color: #fff; margin-top: 10px; }
        .btn-secondary { background: #2B2B30; color: #ddd; margin-top: 10px; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }

        .form-group { margin-bottom: 14px; }
        .form-group label { display: block; font-size: 13px; color: #aaa; margin-bottom: 6px; }
        select, input[type="range"] { width: 100%; background: #2B2B30; border: 1px solid #3E3E46; border-radius: 10px; color: #fff; padding: 12px; font-size: 14px; outline: none; }
        
        .slider-val { font-size: 13px; color: #00AEEC; float: right; }
        
        .progress-box { margin: 15px 0; display: none; }
        .progress-bar-bg { width: 100%; height: 8px; background: #2B2B30; border-radius: 4px; overflow: hidden; }
        .progress-bar { width: 0%; height: 100%; background: #00AEEC; transition: width 0.2s; }
        .progress-text { font-size: 12px; color: #aaa; margin-top: 6px; text-align: center; }

        /* 分类结果列表 */
        .cat-group { background: #26262B; border-radius: 12px; padding: 12px; margin-bottom: 10px; }
        .cat-header { font-size: 14px; font-weight: 600; color: #00AEEC; display: flex; justify-content: space-between; }
        .cat-item { font-size: 12px; color: #ddd; padding: 6px 0; border-bottom: 1px solid #333; line-height: 1.4; }
        .cat-item:last-child { border-bottom: none; }
        .cat-tags { font-size: 11px; color: #888; }

        /* 模态弹窗 */
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 999; justify-content: center; align-items: center; }
        .modal-body { background: #1E1E22; border-radius: 20px; padding: 24px; text-align: center; width: 85%; max-width: 320px; }
        .modal-body img { width: 200px; height: 200px; border-radius: 12px; margin: 15px 0; }
        .modal-body p { font-size: 13px; color: #bbb; line-height: 1.5; }
        .modal-close { margin-top: 15px; color: #888; font-size: 13px; cursor: pointer; }
    </style>
</head>
<body>

    <div class="header">
        <h1>⚡ BiliSort 手机版</h1>
        <p>B 站杂乱收藏夹一键智能分类</p>
    </div>

    <!-- 1. 账号卡片 -->
    <div class="card">
        <div class="card-title">
            <span>当前 B 站账号</span>
            <span id="userStatus" class="user-status"><span class="status-dot offline"></span> 检测中...</span>
        </div>
        <button id="loginBtn" class="btn btn-secondary" onclick="openLoginModal()">📱 扫码授权登录</button>
    </div>

    <!-- 2. 整理配置 -->
    <div class="card">
        <div class="card-title">整理设置</div>
        <div class="form-group">
            <label>选择源收藏夹：</label>
            <select id="folderSelect"><option>请先登录</option></select>
        </div>
        <div class="form-group">
            <label>整理视频数量：<span id="countDisplay" class="slider-val">30 个</span></label>
            <input type="range" id="countSlider" min="5" max="75" step="5" value="30" oninput="document.getElementById('countDisplay').innerText = this.value + ' 个'">
        </div>
        <button id="analyzeBtn" class="btn btn-primary" onclick="startAnalyze()">🔍 1. 智能分析分类 (预览)</button>
        <button id="syncBtn" class="btn btn-success" style="display:none;" onclick="startSync()">🚀 2. 一键同步归类至 B 站</button>
        
        <div id="progressBox" class="progress-box">
            <div class="progress-bar-bg"><div id="progressBar" class="progress-bar"></div></div>
            <div id="progressText" class="progress-text">准备开始...</div>
        </div>
    </div>

    <!-- 3. 结果看板 -->
    <div class="card">
        <div class="card-title">📊 智能分类结果预览</div>
        <div id="resultContainer"><p style="color:#666;font-size:13px;text-align:center;padding:20px 0;">点击上方【智能分析分类】后在此处展示预览</p></div>
    </div>

    <!-- 扫码弹窗 -->
    <div id="loginModal" class="modal">
        <div class="modal-body">
            <h3 style="font-size:16px;">手机 B 站扫码授权</h3>
            <img id="qrImg" src="" alt="二维码加载中...">
            <p>【截图保存】此二维码<br>打开手机哔哩哔哩APP -> 扫一扫 -> 选相册图片授权即可</p>
            <div id="qrTip" style="font-size:12px;color:#00AEEC;margin-top:10px;">等待扫码中...</div>
            <div class="modal-close" onclick="closeLoginModal()">取消关闭</div>
        </div>
    </div>

    <script>
        let isPolling = false;

        async function checkStatus() {
            const res = await fetch('/api/status').then(r => r.json());
            const statusEl = document.getElementById('userStatus');
            const loginBtn = document.getElementById('loginBtn');
            if (res.is_logged_in) {
                statusEl.innerHTML = `<span class="status-dot online"></span> ${res.uname || 'UID:' + res.mid}`;
                loginBtn.innerText = "切换账号";
                loadFolders();
            } else {
                statusEl.innerHTML = `<span class="status-dot offline"></span> 未登录`;
                loginBtn.innerText = "📱 扫码授权登录";
            }
        }

        async function loadFolders() {
            const res = await fetch('/api/folders').then(r => r.json());
            if (res.folders && res.folders.length > 0) {
                const select = document.getElementById('folderSelect');
                select.innerHTML = res.folders.map(f => `<option value="${f.id}">${f.title} (${f.media_count}个)</option>`).join('');
            }
        }

        let qrTimer = null;
        async function openLoginModal() {
            document.getElementById('loginModal').style.display = 'flex';
            const res = await fetch('/api/qr/generate').then(r => r.json());
            if (res.code === 0) {
                document.getElementById('qrImg').src = res.qr_img;
                pollQr(res.qrcode_key);
            }
        }

        function closeLoginModal() {
            document.getElementById('loginModal').style.display = 'none';
            if (qrTimer) clearInterval(qrTimer);
        }

        function pollQr(key) {
            if (qrTimer) clearInterval(qrTimer);
            qrTimer = setInterval(async () => {
                const res = await fetch('/api/qr/poll?key=' + key).then(r => r.json());
                const tip = document.getElementById('qrTip');
                if (res.code === 0) {
                    tip.innerText = "✅ 登录成功！";
                    clearInterval(qrTimer);
                    setTimeout(() => {
                        closeLoginModal();
                        checkStatus();
                    }, 1000);
                } else if (res.code === 86090) {
                    tip.innerText = "已扫码，请在手机上确认...";
                }
            }, 1500);
        }

        async function startAnalyze() {
            const folderId = document.getElementById('folderSelect').value;
            const count = document.getElementById('countSlider').value;
            document.getElementById('progressBox').style.display = 'block';
            document.getElementById('analyzeBtn').disabled = true;

            await fetch('/api/analyze', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ folder_id: folderId, count: parseInt(count) })
            });

            // 轮询进度
            const interval = setInterval(async () => {
                const status = await fetch('/api/analyze/status').then(r => r.json());
                const percent = Math.round(status.progress * 100);
                document.getElementById('progressBar').style.width = percent + '%';
                document.getElementById('progressText').innerText = status.current_text || (percent + '%');

                if (status.status === 'done') {
                    clearInterval(interval);
                    document.getElementById('analyzeBtn').disabled = false;
                    document.getElementById('syncBtn').style.display = 'block';
                    renderResults(status.results);
                }
            }, 800);
        }

        function renderResults(results) {
            const container = document.getElementById('resultContainer');
            let html = '';
            for (let cat in results) {
                const list = results[cat];
                html += `
                <div class="cat-group">
                    <div class="cat-header">
                        <span>${cat}</span>
                        <span>${list.length} 个</span>
                    </div>
                    ${list.map((v, i) => `
                        <div class="cat-item">
                            <div>${i+1}. <b>${v.title}</b></div>
                            <div class="cat-tags">UP主: ${v.owner} | 标签: ${v.tags ? v.tags.slice(0,3).join(', ') : '无'}</div>
                        </div>
                    `).join('')}
                </div>`;
            }
            container.innerHTML = html;
        }

        async function startSync() {
            if (!confirm("确认在您的 B 站账号中新建这些分类收藏夹并同步视频吗？")) return;
            const folderId = document.getElementById('folderSelect').value;
            document.getElementById('syncBtn').disabled = true;
            document.getElementById('syncBtn').innerText = "正在同步至 B 站中...";

            const res = await fetch('/api/sync', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ folder_id: folderId })
            }).then(r => r.json());

            if (res.code === 0) {
                alert("🎉 同步完成！请打开手机哔哩哔哩 APP【我的】->【我的收藏】下拉刷新查看！");
                document.getElementById('syncBtn').innerText = "✅ 同步成功";
            } else {
                alert("同步提示: " + res.message);
                document.getElementById('syncBtn').disabled = false;
            }
        }

        checkStatus();
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(MOBILE_HTML)

@app.route("/api/status")
def api_status():
    logged_in = user_sync.check_login()
    uname = ""
    if logged_in:
        try:
            nav = user_sync.session.get("https://api.bilibili.com/x/web-interface/nav").json()
            uname = nav.get("data", {}).get("uname", "")
        except Exception:
            pass
    return jsonify({
        "is_logged_in": logged_in,
        "mid": user_sync.mid,
        "uname": uname
    })

@app.route("/api/folders")
def api_folders():
    try:
        folders = user_sync.get_favorite_folders()
        return jsonify({"code": 0, "folders": folders})
    except Exception as e:
        return jsonify({"code": -1, "message": str(e)})

@app.route("/api/qr/generate")
def api_qr_generate():
    gen_url = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
    r = user_sync.session.get(gen_url, timeout=10).json()
    if r.get("code") != 0:
        return jsonify({"code": -1, "message": "获取二维码失败"})
    login_url = r["data"]["url"]
    qrcode_key = r["data"]["qrcode_key"]
    
    # 转为 base64 data uri 图片
    import io, base64
    qr = qrcode.QRCode(box_size=6, border=1)
    qr.add_data(login_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64_img = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")

    return jsonify({"code": 0, "qr_img": b64_img, "qrcode_key": qrcode_key})

@app.route("/api/qr/poll")
def api_qr_poll():
    key = request.args.get("key")
    poll_url = f"https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key={key}"
    resp = user_sync.session.get(poll_url, timeout=10).json()
    code = resp.get("data", {}).get("code")
    if code == 0:
        cookies_dict = requests.utils.dict_from_cookiejar(user_sync.session.cookies)
        user_sync.check_login()
        user_sync.save_cookies(cookies_dict, user_sync.mid)
        folder_manager.csrf = folder_manager._get_csrf()
    return jsonify({"code": code})

@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.json or {}
    folder_id = data.get("folder_id")
    count = data.get("count", 30)

    def run_analyze():
        global current_scan_status
        current_scan_status["status"] = "running"
        current_scan_status["progress"] = 0.1
        current_scan_status["current_text"] = "正在获取收藏夹视频..."
        
        videos_raw = []
        page = 1
        page_size = 20
        while len(videos_raw) < count:
            cur_ps = min(page_size, count - len(videos_raw))
            url = f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={folder_id}&pn={page}&ps={cur_ps}"
            resp = user_sync.session.get(url, timeout=10).json()
            medias = resp.get("data", {}).get("medias", [])
            if not medias:
                break
            for m in medias:
                videos_raw.append({
                    "aid": m.get("id"),
                    "bvid": m.get("bvid"),
                    "title": m.get("title"),
                    "intro": m.get("intro", ""),
                    "owner": m.get("upper", {}).get("name", "")
                })
            if len(medias) < cur_ps:
                break
            page += 1

        total = len(videos_raw)
        results = {}
        for idx, v in enumerate(videos_raw, 1):
            tags = folder_manager.get_video_tags(v["aid"])
            v["tags"] = tags
            cat = classifier.classify(v["title"], v["intro"], v["owner"], tags=tags)
            results.setdefault(cat, []).append(v)
            current_scan_status["progress"] = idx / total
            current_scan_status["current_text"] = f"分析中 ({idx}/{total}): {v['title'][:15]}..."
            time.sleep(0.03)

        current_scan_status["status"] = "done"
        current_scan_status["results"] = results
        current_scan_status["total"] = total
        current_scan_status["current_text"] = "分析完成！"

    import threading
    threading.Thread(target=run_analyze, daemon=True).start()
    return jsonify({"code": 0, "message": "started"})

@app.route("/api/analyze/status")
def api_analyze_status():
    return jsonify(current_scan_status)

@app.route("/api/sync", methods=["POST"])
def api_sync():
    data = request.json or {}
    src_folder_id = data.get("folder_id")
    results = current_scan_status.get("results", {})
    if not results:
        return jsonify({"code": -1, "message": "无分类结果"})

    try:
        all_folders = {f["title"]: f["id"] for f in user_sync.get_favorite_folders()}
        for cat, vids in results.items():
            tar_id = all_folders.get(cat)
            if not tar_id:
                tar_id = folder_manager.create_folder(title=cat, intro="BiliSort智能分类", privacy=1)
                if tar_id:
                    all_folders[cat] = tar_id
            if tar_id:
                aids = [v["aid"] for v in vids if v.get("aid")]
                folder_manager.batch_copy_to_folder(src_media_id=src_folder_id, tar_media_id=tar_id, aids=aids)
        return jsonify({"code": 0, "message": "ok"})
    except Exception as e:
        return jsonify({"code": -1, "message": str(e)})

def get_local_ip():
    """获取本机局域网 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

if __name__ == "__main__":
    local_ip = get_local_ip()
    port = 5000
    mobile_url = f"http://{local_ip}:{port}"
    print("\n" + "="*60)
    print("🚀 BiliSort 手机移动端服务已成功启动！")
    print(f"📱 手机浏览器直接访问地址: {mobile_url}")
    print("💡 手机连接同一 Wi-Fi 后打开该链接，即可享受手机端 App 体验！")
    print("💡 同学在手机浏览器菜单点击【添加到主屏幕】，即成为桌面独立 App！")
    print("="*60 + "\n")
    app.run(host="0.0.0.0", port=port, debug=False)
