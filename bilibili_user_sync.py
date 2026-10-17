import os
import sys
import time
import json
import requests
import qrcode
from typing import Dict, Any, List, Optional

# 确保 Windows 终端 UTF-8 编码
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bilibili_cookie.json")

class BilibiliUserSync:
    """B站个人收藏与点赞同步管理器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com"
        })
        self.mid = None
        self.load_cookies()

    def load_cookies(self):
        """尝试从本地加载已保存的凭证"""
        if os.path.exists(COOKIE_FILE):
            try:
                with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.mid = data.get("mid")
                    cookies = data.get("cookies", {})
                    self.session.cookies.update(cookies)
            except Exception as e:
                print(f"[Cookie] 加载本地 Cookie 失败: {e}")

    def save_cookies(self, cookies_dict: dict, mid: str):
        """保存凭证到本地"""
        data = {
            "mid": mid,
            "cookies": cookies_dict,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[Cookie] 凭证已安全保存至: {COOKIE_FILE}")

    def check_login(self) -> bool:
        """验证当前登录态是否有效"""
        url = "https://api.bilibili.com/x/web-interface/nav"
        try:
            resp = self.session.get(url, timeout=10)
            data = resp.json()
            if data.get("code") == 0 and data.get("data", {}).get("isLogin"):
                self.mid = data["data"]["mid"]
                uname = data["data"]["uname"]
                print(f"[B站] 已登录账号: {uname} (UID: {self.mid})")
                return True
        except Exception as e:
            print(f"[B站] 验证登录异常: {e}")
        return False

    def qrcode_login(self) -> bool:
        """通过二维码扫码登录"""
        print("\n=== 开始 B站 扫码登录 ===")
        # 1. 申请二维码
        gen_url = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
        resp = self.session.get(gen_url, timeout=10)
        res_data = resp.json()
        if res_data.get("code") != 0:
            print("获取二维码失败:", res_data)
            return False

        login_url = res_data["data"]["url"]
        qrcode_key = res_data["data"]["qrcode_key"]

        # 2. 生成本地二维码图片
        qr_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bili_login_qr.png")
        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data(login_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(qr_path)

        print(f"[扫码] 二维码已生成，正在为您打开二维码图片...")
        if sys.platform.startswith("win"):
            os.startfile(qr_path)
        print("请打开【手机哔哩哔哩 APP】扫描弹出的二维码图片并点击确认授权...")

        # 3. 轮询检查扫码结果
        poll_url = f"https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key={qrcode_key}"
        timeout = 180  # 3分钟有效
        start_time = time.time()

        while time.time() - start_time < timeout:
            poll_resp = self.session.get(poll_url, timeout=10)
            p_data = poll_resp.json()
            code = p_data.get("data", {}).get("code")

            if code == 0:
                print("\n[扫码成功] 登录成功！正在同步账号信息...")
                # 提取 cookies 并保存
                cookies_dict = requests.utils.dict_from_cookiejar(self.session.cookies)
                # 获取 mid
                self.check_login()
                if self.mid:
                    self.save_cookies(cookies_dict, self.mid)
                # 清理临时二维码图片
                if os.path.exists(qr_path):
                    try:
                        os.remove(qr_path)
                    except Exception:
                        pass
                return True
            elif code == 86101:
                # 未扫码
                time.sleep(2)
            elif code == 86090:
                print("\r[扫码中] 已扫码，请在手机上点击【确认登录】...", end="", flush=True)
                time.sleep(1.5)
            elif code == 86038:
                print("\n[失效] 二维码已失效，请重新运行登录")
                return False
            else:
                time.sleep(2)

        print("\n[超时] 扫码超时，请重新运行")
        return False

    def get_favorite_folders(self) -> List[Dict[str, Any]]:
        """获取用户创建的所有收藏夹"""
        if not self.mid:
            raise Exception("未登录，无法获取收藏夹")

        url = f"https://api.bilibili.com/x/v3/fav/folder/created/list-all?up_mid={self.mid}"
        resp = self.session.get(url, timeout=10)
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"获取收藏夹失败: {data.get('message')}")
        
        folders = data.get("data", {}).get("list", [])
        return folders

    def get_favorite_videos(self, media_id: int, page_size: int = 10) -> List[Dict[str, Any]]:
        """获取指定收藏夹内的视频列表"""
        url = f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={media_id}&pn=1&ps={page_size}"
        resp = self.session.get(url, timeout=10)
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"获取收藏内容失败: {data.get('message')}")

        medias = data.get("data", {}).get("medias", [])
        results = []
        for m in (medias or []):
            results.append({
                "bvid": m.get("bvid"),
                "title": m.get("title"),
                "intro": m.get("intro"),
                "owner": m.get("upper", {}).get("name"),
                "cover": m.get("cover"),
                "fav_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(m.get("fav_time", 0))),
                "link": f"https://www.bilibili.com/video/{m.get('bvid')}"
            })
        return results

    def get_liked_videos(self) -> List[Dict[str, Any]]:
        """获取用户最近点赞的视频"""
        if not self.mid:
            raise Exception("未登录")

        url = f"https://api.bilibili.com/x/space/like/video?mid={self.mid}"
        resp = self.session.get(url, timeout=10)
        data = resp.json()
        if data.get("code") != 0:
            # 常见提示：用户隐私设置关闭了点赞公开
            return []

        item_list = data.get("data", {}).get("list", [])
        results = []
        for item in item_list:
            results.append({
                "bvid": item.get("bvid"),
                "title": item.get("title"),
                "owner": item.get("owner", {}).get("name"),
                "link": f"https://www.bilibili.com/video/{item.get('bvid')}"
            })
        return results

if __name__ == "__main__":
    client = BilibiliUserSync()
    if not client.check_login():
        success = client.qrcode_login()
        if not success:
            sys.exit(1)

    print("\n--- 正在读取您的个人收藏夹 ---")
    folders = client.get_favorite_folders()
    for idx, f in enumerate(folders, 1):
        print(f"[{idx}] 收藏夹: {f['title']} (共 {f['media_count']} 个视频, ID: {f['id']})")

    if folders:
        default_folder = folders[0]
        print(f"\n--- 查看【{default_folder['title']}】最近收藏的 5 个视频 ---")
        videos = client.get_favorite_videos(default_folder["id"], page_size=5)
        for i, v in enumerate(videos, 1):
            print(f"  {i}. {v['title']} (UP主: {v['owner']})")
            print(f"     链接: {v['link']} | 收藏于: {v['fav_time']}")

    print("\n--- 正在读取您最近点赞的视频 ---")
    likes = client.get_liked_videos()
    if likes:
        for i, l in enumerate(likes[:5], 1):
            print(f"  {i}. {l['title']} (UP主: {l['owner']}) -> {l['link']}")
    else:
        print("  (提示: B站默认个人点赞列表可能在隐私设置中设为私密，或暂无最近公开点赞)")
