import re
import os
import requests
import json
from typing import Dict, Any, Optional, List
from bilibili_user_sync import COOKIE_FILE

class BilibiliExtractor:
    """B站视频信息与字幕/音频提取器"""

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com"
        }
        self._load_cookie_headers()

    def _load_cookie_headers(self):
        if os.path.exists(COOKIE_FILE):
            try:
                with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cookies = data.get("cookies", {})
                    if cookies:
                        self.headers["Cookie"] = "; ".join([f"{k}={v}" for k, v in cookies.items()])
            except Exception:
                pass

    def extract_bvid(self, text: str) -> Optional[str]:
        """从URL或文本中提取BV号"""
        match = re.search(r"(BV[a-zA-Z0-9]{10})", text)
        return match.group(1) if match else None

    def get_video_info(self, bvid: str) -> Dict[str, Any]:
        """获取视频基本元数据"""
        url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        resp = requests.get(url, headers=self.headers, timeout=10)
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"Bilibili API Error: {data.get('message', 'Unknown error')}")
        
        d = data["data"]
        return {
            "platform": "bilibili",
            "bvid": bvid,
            "aid": d.get("aid"),
            "cid": d.get("cid"),
            "title": d.get("title"),
            "desc": d.get("desc"),
            "owner": d.get("owner", {}).get("name"),
            "owner_mid": d.get("owner", {}).get("mid"),
            "pic": d.get("pic"),
            "duration": d.get("duration"),
            "pubdate": d.get("pubdate")
        }

    def get_subtitles(self, bvid: str, cid: int) -> Optional[List[Dict[str, Any]]]:
        """尝试获取官方/AI字幕"""
        url = f"https://api.bilibili.com/x/player/v2?bvid={bvid}&cid={cid}"
        resp = requests.get(url, headers=self.headers, timeout=10)
        data = resp.json()
        
        subtitles_info = data.get("data", {}).get("subtitle", {}).get("subtitles", [])
        if not subtitles_info:
            return None
        
        # 优先选用中文或AI生成的字幕
        sub_url = None
        for s in subtitles_info:
            if "zh" in s.get("lan", "") or "ai" in s.get("lan", ""):
                sub_url = s.get("subtitle_url")
                break
        if not sub_url and subtitles_info:
            sub_url = subtitles_info[0].get("subtitle_url")

        if not sub_url:
            return None

        if sub_url.startswith("//"):
            sub_url = "https:" + sub_url

        sub_resp = requests.get(sub_url, headers=self.headers, timeout=10)
        sub_data = sub_resp.json()
        return sub_data.get("body", [])

    def format_subtitles_to_text(self, subtitle_body: List[Dict[str, Any]]) -> str:
        """格式化字幕为纯文本"""
        lines = []
        for item in subtitle_body:
            from_time = item.get("from", 0)
            content = item.get("content", "").strip()
            # 格式化时间为 mm:ss
            m, s = divmod(int(from_time), 60)
            if content:
                lines.append(f"[{m:02d}:{s:02d}] {content}")
        return "\n".join(lines)

    def get_audio_stream_url(self, bvid: str, cid: int) -> Optional[str]:
        """获取视频音轨流地址（用于无字幕时下载转写）"""
        url = f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&fnval=16"
        resp = requests.get(url, headers=self.headers, timeout=10)
        data = resp.json()
        dash = data.get("data", {}).get("dash", {})
        audio_list = dash.get("audio", [])
        if audio_list:
            return audio_list[0].get("baseUrl") or audio_list[0].get("backupUrl", [None])[0]
        return None

if __name__ == "__main__":
    extractor = BilibiliExtractor()
    # 测试获取一个常见视频信息，例如科普视频
    test_bv = "BV1GJ411x7h7" # B站经典视频
    print(f"Testing BV: {test_bv}")
    info = extractor.get_video_info(test_bv)
    print("Video Info:", json.dumps(info, ensure_ascii=False, indent=2))
    
    subs = extractor.get_subtitles(test_bv, info["cid"])
    if subs:
        print(f"Found {len(subs)} subtitle lines!")
        print("Preview:")
        print(extractor.format_subtitles_to_text(subs[:5]))
    else:
        print("No subtitle found, audio stream URL:", extractor.get_audio_stream_url(test_bv, info["cid"]))
