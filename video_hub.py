import os
import sys
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional

# 确保控制台支持 UTF-8 打印
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from bilibili_extractor import BilibiliExtractor
from douyin_extractor import DouyinExtractor
from transcriber import AudioTranscriber

KNOWLEDGE_BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge_base")
TEMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")

os.makedirs(KNOWLEDGE_BASE_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

class VideoKnowledgeHub:
    """全域视频知识打通管道 (B站 + 抖音)"""

    def __init__(self):
        self.bili = BilibiliExtractor()
        self.douyin = DouyinExtractor()
        self._transcriber = None

    @property
    def transcriber(self):
        if self._transcriber is None:
            self._transcriber = AudioTranscriber(model_size="base")
        return self._transcriber

    def identify_platform(self, input_text: str) -> Optional[str]:
        """识别链接来源平台"""
        if "bilibili.com" in input_text or "BV" in input_text or "b23.tv" in input_text:
            return "bilibili"
        if "douyin.com" in input_text or "iesdouyin.com" in input_text:
            return "douyin"
        return None

    def process_bilibili(self, input_text: str) -> Dict[str, Any]:
        """处理 B 站视频"""
        bvid = self.bili.extract_bvid(input_text)
        if not bvid:
            raise ValueError(f"未在输入中找到有效的 B 站 BV 号: {input_text}")

        print(f"\n[B站] 正在获取视频基础信息 (BV: {bvid})...")
        info = self.bili.get_video_info(bvid)
        title = info.get("title", "未命名视频")
        owner = info.get("owner", "未知UP主")
        print(f"[B站] 标题: {title} | UP主: {owner}")

        # 1. 尝试直接获取已有字幕
        print("[B站] 检查是否自带字幕/AI字幕...")
        subs = self.bili.get_subtitles(bvid, info["cid"])
        transcript = ""
        source_type = "official_subtitle"

        if subs:
            print(f"[B站] 成功提取官方/AI字幕，共 {len(subs)} 句！(秒级完成)")
            transcript = self.bili.format_subtitles_to_text(subs)
        else:
            print("[B站] 未发现现有字幕，尝试下载音频流并启动本地 Whisper 转写...")
            source_type = "whisper_transcription"
            audio_url = self.bili.get_audio_stream_url(bvid, info["cid"])
            if not audio_url:
                raise Exception("无法提取 B 站音轨流地址")

            temp_audio = os.path.join(TEMP_DIR, f"bili_{bvid}.wav")
            print(f"[B站] 正在下载音频流至缓存: {temp_audio}...")
            ok = self.transcriber.download_audio_with_ffmpeg(
                audio_url, 
                temp_audio, 
                headers={"Referer": "https://www.bilibili.com"}
            )
            if not ok:
                raise Exception("音频流下载转换失败")

            print("[B站] 开始本地语音识别转写文本...")
            transcript = self.transcriber.transcribe(temp_audio)
            
            # 清理临时文件
            if os.path.exists(temp_audio):
                os.remove(temp_audio)

        result = {
            "platform": "bilibili",
            "video_id": bvid,
            "title": title,
            "author": owner,
            "description": info.get("desc", ""),
            "url": f"https://www.bilibili.com/video/{bvid}",
            "source_type": source_type,
            "transcript": transcript,
            "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        self.save_to_knowledge_base(result)
        return result

    def process_douyin(self, input_text: str) -> Dict[str, Any]:
        """处理抖音视频"""
        print(f"\n[抖音] 正在解析抖音分享链接...")
        share_url = self.douyin.extract_share_url(input_text)
        if not share_url:
            raise ValueError(f"未找到有效的抖音链接: {input_text}")

        aweme_id = self.douyin.get_real_video_id(share_url)
        if not aweme_id:
            raise ValueError(f"无法从抖音链接解析出真实作品ID: {share_url}")

        print(f"[抖音] 解析成功，作品ID: {aweme_id}，正在获取视频详情...")
        info = self.douyin.get_video_info(aweme_id)
        title = info.get("title", f"抖音作品_{aweme_id}")
        author = info.get("author", "抖音创作者")
        video_url = info.get("video_url") or info.get("music_url")

        print(f"[抖音] 标题/文案: {title} | 作者: {author}")

        transcript = ""
        source_type = "whisper_transcription"

        if video_url:
            temp_audio = os.path.join(TEMP_DIR, f"douyin_{aweme_id}.wav")
            print(f"[抖音] 正在下载音频流: {temp_audio}...")
            ok = self.transcriber.download_audio_with_ffmpeg(video_url, temp_audio)
            if ok:
                print("[抖音] 正在转录音频内容...")
                transcript = self.transcriber.transcribe(temp_audio)
                if os.path.exists(temp_audio):
                    os.remove(temp_audio)
            else:
                transcript = "(音频流下载受限，仅保留视频标题与文案)"
        else:
            transcript = "(未获取到无水印音频流，仅保留文本内容)"

        result = {
            "platform": "douyin",
            "video_id": aweme_id,
            "title": title,
            "author": author,
            "description": title,
            "url": info.get("source_url", share_url),
            "source_type": source_type,
            "transcript": transcript,
            "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        self.save_to_knowledge_base(result)
        return result

    def process(self, input_text: str) -> Dict[str, Any]:
        """统一分发处理"""
        platform = self.identify_platform(input_text)
        if platform == "bilibili":
            return self.process_bilibili(input_text)
        elif platform == "douyin":
            return self.process_douyin(input_text)
        else:
            raise ValueError("无法识别的链接，请传入 B 站或抖音的链接/口令")

    def save_to_knowledge_base(self, data: Dict[str, Any]):
        """将归档知识沉淀为标准 Markdown 文档，供全域 Agent 共享检索"""
        safe_title = "".join([c for c in data["title"] if c.isalnum() or c in (" ", "-", "_")])[:40].strip()
        filename = f"{data['platform']}_{data['video_id']}_{safe_title}.md"
        filepath = os.path.join(KNOWLEDGE_BASE_DIR, filename)

        md_content = f"""# {data['title']}

- **平台**: {data['platform'].upper()}
- **作者/UP主**: {data['author']}
- **视频ID**: `{data['video_id']}`
- **原链接**: [{data['url']}]({data['url']})
- **入库时间**: {data['processed_at']}
- **文本来源**: {data['source_type']}

## 视频简介 / 文案
{data['description']}

---

## 逐字稿 / 字幕全文内容
```text
{data['transcript']}
```
"""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md_content)

        print(f"\n[知识库] 数据已成功沉淀入个人知识中枢: {filepath}")

if __name__ == "__main__":
    hub = VideoKnowledgeHub()
    # 支持命令行参数输入，例如: python video_hub.py "https://www.bilibili.com/video/BV1GJ411x7h7"
    if len(sys.argv) > 1:
        target = sys.argv[1]
        hub.process(target)
    else:
        print("Video Knowledge Hub 就绪。用法: python video_hub.py <视频链接或口令>")
