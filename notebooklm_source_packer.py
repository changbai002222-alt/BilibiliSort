import os
import sys
import time
import re
from typing import Dict, Any, List, Optional

# 确保控制台 UTF-8
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from bilibili_extractor import BilibiliExtractor
from bilibili_user_sync import BilibiliUserSync

NOTEBOOKLM_SOURCES_DIR = os.path.join("D:\\柏雯博-数据", "notebooklm_sources")
os.makedirs(NOTEBOOKLM_SOURCES_DIR, exist_ok=True)

class NotebookLMSourcePacker:
    """
    官方 NotebookLM 专属粮草打包器：
    将 B 站等国内平台的长视频无缝转为带精准时间戳的 NotebookLM 极佳格式源文档。
    """

    def __init__(self):
        self.bili = BilibiliExtractor()
        self.user_sync = BilibiliUserSync()
        self._transcriber = None

    @property
    def transcriber(self):
        if self._transcriber is None:
            from transcriber import AudioTranscriber
            self._transcriber = AudioTranscriber(model_size="base")
        return self._transcriber

    def clean_filename(self, title: str) -> str:
        """清理 Windows 非法文件名字符"""
        return re.sub(r'[\/\\:\*\?"<>\|]', '_', title).strip()

    def process_bilibili_video(self, bvid_or_url: str) -> Optional[str]:
        """
        处理单个 B 站视频，提取元数据与字幕/音轨，生成 NotebookLM 格式源文件
        返回生成的本地文件绝对路径
        """
        bvid = self.bili.extract_bvid(bvid_or_url)
        if not bvid:
            print(f"[错误] 未能识别有效 BV 号: {bvid_or_url}")
            return None

        print(f"\n=======================================================")
        print(f"🎬 正在解析 B 站视频: {bvid}")
        info = self.bili.get_video_info(bvid)
        title = info.get("title", f"B站视频_{bvid}")
        owner = info.get("owner", "未知UP主")
        desc = info.get("desc", "").strip()
        cid = info.get("cid")
        video_url = f"https://www.bilibili.com/video/{bvid}"
        print(f"标题: {title}")
        print(f"UP主: {owner}")

        # 获取标签 Tags
        tags = []
        try:
            tag_resp = self.user_sync.session.get(f"https://api.bilibili.com/x/tag/archive/tags?aid={info.get('aid')}", timeout=5).json()
            tags = [t.get("tag_name") for t in tag_resp.get("data", [])]
        except Exception:
            pass
        tags_str = "、".join(tags) if tags else "无标签"

        # 提取字幕 / 转写
        print("🔍 正在检查 B 站原生字幕 / AI 字幕...")
        subtitles = self.bili.get_subtitles(bvid, cid)
        formatted_transcript_lines = []

        if subtitles:
            print(f"✅ 成功命中原生字幕，共提取 {len(subtitles)} 条带时间戳原话！")
            for sub in subtitles:
                from_sec = int(sub.get("from", 0))
                m, s = divmod(from_sec, 60)
                h, m = divmod(m, 60)
                time_str = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
                text = sub.get("content", "").strip()
                if text:
                    formatted_transcript_lines.append(f"[{time_str}] {text}")
        else:
            print("⚡ 未检测到原生字幕，正在下载音频流并启动本地 Whisper 语音转写...")
            audio_url = self.bili.get_audio_stream_url(bvid, cid)
            if not audio_url:
                print("❌ 无法提取音轨地址")
                return None

            temp_audio = os.path.join("D:\\柏雯博-数据", "tools", "cache", f"temp_{bvid}.wav")
            os.makedirs(os.path.dirname(temp_audio), exist_ok=True)

            print(f"正在下载音频流...")
            ok = self.transcriber.download_audio_with_ffmpeg(
                audio_url, temp_audio,
                headers={"Referer": "https://www.bilibili.com"}
            )
            if not ok:
                print("❌ 音频流下载失败")
                return None

            print("正在使用 Whisper 进行语音转写识别...")
            raw_text = self.transcriber.transcribe(temp_audio)
            if os.path.exists(temp_audio):
                os.remove(temp_audio)

            # 拆分为句子段落
            paragraphs = [p.strip() for p in raw_text.split("。") if p.strip()]
            for p in paragraphs:
                formatted_transcript_lines.append(f"{p}。")

        # 按照 NotebookLM 最佳实践组装结构化文档
        doc_content = f"""# {title}

- **作者 / UP主**：{owner}
- **视频来源**：{video_url}
- **内容标签**：{tags_str}
- **视频简介**：
> {desc if desc else "（无额外简介）"}

---

## 视频完整转录文字稿（含时间线）

{"\n".join(formatted_transcript_lines)}
"""

        clean_name = self.clean_filename(f"【B站】{title}_{bvid}")
        out_path = os.path.join(NOTEBOOKLM_SOURCES_DIR, f"{clean_name}.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(doc_content)

        print(f"🎉 NotebookLM 专属源文件已生成！")
        print(f"📁 本地保存路径: {out_path}")

        # 自动直传到本地挂载的 Google Drive (G 盘)
        gdrive_dir = "G:\\我的云端硬盘\\NotebookLM_Sources"
        if os.path.exists("G:\\我的云端硬盘"):
            try:
                os.makedirs(gdrive_dir, exist_ok=True)
                gdrive_path = os.path.join(gdrive_dir, f"{clean_name}.md")
                with open(gdrive_path, "w", encoding="utf-8") as gf:
                    gf.write(doc_content)
                print(f"☁️ 已自动同步至 Google Drive: {gdrive_path}")
            except Exception as ge:
                print(f"⚠️ 同步至 G 盘失败: {ge}")

        return out_path

    def process_folder(self, folder_index: int = 0, limit: int = 5) -> List[str]:
        """批量处理指定收藏夹中的最新视频并打包为 NotebookLM 源"""
        if not self.user_sync.check_login():
            print("请先登录 B 站...")
            if not self.user_sync.qrcode_login():
                return []

        folders = self.user_sync.get_favorite_folders()
        if not folders:
            print("未获取到收藏夹")
            return []

        target_folder = folders[folder_index]
        print(f"\n📦 开始批量打包收藏夹【{target_folder['title']}】的最新 {limit} 个视频...")
        videos = self.user_sync.get_favorite_videos(target_folder["id"], page_size=limit)

        generated_files = []
        for idx, v in enumerate(videos, 1):
            print(f"\n[{idx}/{len(videos)}] 正在处理: {v['title']}")
            path = self.process_bilibili_video(v["bvid"])
            if path:
                generated_files.append(path)
            time.sleep(1)

        print(f"\n=======================================================")
        print(f"🎉 批量打包完成！共生成 {len(generated_files)} 个 NotebookLM 源文件。")
        print(f"📁 文件夹位置: {NOTEBOOKLM_SOURCES_DIR}")
        return generated_files

    def open_export_folder(self):
        """在 Windows 资源管理器中打开导出文件夹，方便用户一键拖拽进 NotebookLM"""
        if os.path.exists(NOTEBOOKLM_SOURCES_DIR):
            os.startfile(NOTEBOOKLM_SOURCES_DIR)

PROCESSED_BVIDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "processed_bvids.json")

def load_processed_bvids() -> List[str]:
    if os.path.exists(PROCESSED_BVIDS_FILE):
        try:
            with open(PROCESSED_BVIDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_processed_bvids(bvids: List[str]):
    try:
        with open(PROCESSED_BVIDS_FILE, "w", encoding="utf-8") as f:
            json.dump(bvids, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def sync_new_favorites(limit: int = 10) -> List[Dict[str, Any]]:
    """增量监听最新收藏：全自动对比并只处理最新收藏的新视频"""
    packer = NotebookLMSourcePacker()
    if not packer.user_sync.check_login():
        print("尚未登录，无法监听收藏夹")
        return []

    folders = packer.user_sync.get_favorite_folders()
    if not folders:
        return []

    default_f = folders[0]
    videos = packer.user_sync.get_favorite_videos(default_f["id"], page_size=limit)
    processed = load_processed_bvids()

    new_results = []
    for v in videos:
        bvid = v["bvid"]
        if bvid in processed:
            continue

        print(f"\n=======================================================")
        print(f"✨ 监听到新收藏视频: 【{v['title']}】 ({bvid})")
        src_path = packer.process_bilibili_video(bvid)
        if src_path:
            # 自动收割进 Obsidian 资源库
            try:
                from notebooklm_vault_harvester import NotebookLMVaultHarvester
                harvester = NotebookLMVaultHarvester()
                with open(src_path, "r", encoding="utf-8") as f:
                    content = f.read()
                note_path = harvester.harvest(
                    raw_text=content,
                    title=v["title"],
                    source_url=f"https://www.bilibili.com/video/{bvid}",
                    summary_desc=f"{v.get('owner', '')} 视频整理"
                )
                print(f"✅ 已全自动落盘入库 Obsidian: {note_path}")
            except Exception as he:
                print(f"⚠️ 自动收割 Obsidian 异常: {he}")

            processed.append(bvid)
            new_results.append({
                "bvid": bvid,
                "title": v["title"],
                "source_path": src_path
            })
            time.sleep(1)

    save_processed_bvids(processed)
    if not new_results:
        print("ℹ️ 暂无新的未处理收藏视频")
    else:
        print(f"\n🎉 增量处理完毕，本次新增处理 {len(new_results)} 个视频！")
    return new_results

if __name__ == "__main__":
    packer = NotebookLMSourcePacker()
    if len(sys.argv) > 1:
        target = sys.argv[1]
        if target == "--auto" or target == "-a":
            sync_new_favorites(limit=10)
        elif "BV" in target or "bilibili" in target:
            packer.process_bilibili_video(target)
            packer.open_export_folder()
        elif target.isdigit():
            packer.process_folder(folder_index=int(target), limit=3)
            packer.open_export_folder()
    else:
        sync_new_favorites(limit=10)
