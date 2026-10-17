import re
import requests
import json
from typing import Dict, Any, Optional

class DouyinExtractor:
    """抖音视频信息与无水印音频/视频提取器"""

    def __init__(self):
        # 移动端 User-Agent 便于访问分享页面
        self.mobile_headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
        }
        self.web_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.douyin.com/"
        }

    def extract_share_url(self, text: str) -> Optional[str]:
        """从带有文本的口令中提取出抖音短链接或原始链接"""
        match = re.search(r"https?://(?:v\.douyin\.com|www\.douyin\.com|www\.iesdouyin\.com)/[a-zA-Z0-9_\-\./]+", text)
        return match.group(0) if match else None

    def get_real_video_id(self, url: str) -> Optional[str]:
        """跟随重定向获取真实的 aweme_id"""
        try:
            # 抖音短链接会 302 重定向
            resp = requests.get(url, headers=self.mobile_headers, allow_redirects=True, timeout=10)
            final_url = resp.url
            # 从目标URL中提取数字ID
            match = re.search(r"/(?:video|note)/(\d+)", final_url)
            if match:
                return match.group(1)
            # 或者从页面内容中提取
            match_html = re.search(r'modal_id=(\d+)', final_url)
            if match_html:
                return match_html.group(1)
            return None
        except Exception as e:
            print(f"Error resolving real video id: {e}")
            return None

    def get_video_info(self, aweme_id: str) -> Dict[str, Any]:
        """根据 aweme_id 提取视频数据"""
        # 方式1：通过 iesdouyin share 页面解析内嵌数据
        share_url = f"https://www.iesdouyin.com/share/video/{aweme_id}/"
        resp = requests.get(share_url, headers=self.mobile_headers, timeout=10)
        html = resp.text

        # 尝试提取 _ROUTER_DATA
        router_data_match = re.search(r'window\._ROUTER_DATA\s*=\s*(\{.*?\});</script>', html, re.DOTALL)
        
        title = ""
        author = ""
        video_url = ""
        music_url = ""

        if router_data_match:
            try:
                data = json.loads(router_data_match.group(1))
                # 遍历查找 item_list 或 loaderData
                loader_data = data.get("loaderData", {})
                for key, val in loader_data.items():
                    item = val.get("itemInfo", {}).get("itemStruct")
                    if item:
                        title = item.get("desc", "")
                        author = item.get("author", {}).get("nickname", "")
                        video_url = item.get("video", {}).get("playAddr", [{}])[0].get("src", "")
                        music_url = item.get("music", {}).get("playUrl", {}).get("uri", "")
                        break
            except Exception as e:
                print(f"Failed parsing _ROUTER_DATA: {e}")

        # 降级备用：如果解析不到，尝试调用开放/web端接口
        if not title:
            # 尝试正文 meta 标签提取
            title_match = re.search(r'<title>(.*?)</title>', html)
            if title_match:
                title = title_match.group(1).replace(" - 抖音", "").strip()

        return {
            "platform": "douyin",
            "aweme_id": aweme_id,
            "title": title,
            "author": author,
            "video_url": video_url,
            "music_url": music_url,
            "source_url": share_url
        }

if __name__ == "__main__":
    extractor = DouyinExtractor()
    test_text = "7.12 复制打开抖音，看看【央视新闻的作品】 https://v.douyin.com/iLNxXxX/ "
    print("Testing Douyin text parsing...")
    extracted_url = extractor.extract_share_url(test_text)
    print("Extracted URL:", extracted_url)
