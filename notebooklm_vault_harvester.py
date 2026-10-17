import os
import sys
import re
import time
import shutil
from datetime import datetime
from typing import Optional, List, Dict, Any

# 确保控制台 UTF-8
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

VAULT_ROOT = "D:\\柏雯博"
INBOX_DIR = os.path.join(VAULT_ROOT, "00 Inbox")
RESOURCE_DIR = os.path.join(VAULT_ROOT, "30 资源库", "07 外部资料")
ATTACHMENTS_DIR = os.path.join(VAULT_ROOT, "_附件")

os.makedirs(INBOX_DIR, exist_ok=True)
os.makedirs(RESOURCE_DIR, exist_ok=True)
os.makedirs(ATTACHMENTS_DIR, exist_ok=True)

class NotebookLMVaultHarvester:
    """
    NotebookLM 成果收割器：
    将官方 NotebookLM 产出的研读报告、简报、FAQ与播客音频，
    规范化清洗并安全落盘至 D:\\柏雯博 知识库，严格符合 AGENTS.md 规则。
    """

    def clean_filename(self, text: str) -> str:
        return re.sub(r'[\/\\:\*\?"<>\|]', '_', text).strip()

    def sanitize_content(self, text: str) -> str:
        """
        按 AGENTS.md 要求清洗文本：
        - 移除行业黑话与空话（如「综上所述」「不是……而是……」等）
        - 确保标点规范与段落完整
        """
        # 移除常见 AI 套话
        text = re.sub(r'(综上所述|一句话总结|总的来说)[，：,:]?', '', text)
        text = re.sub(r'不是\s*([^，,]+)[，,]\s*而是\s*([^。.]+)[。.]', r'实为 \2（非 \1）。', text)
        return text.strip()

    def extract_keywords_to_wikilinks(self, text: str, extra_tags: List[str] = None) -> str:
        """
        智能识别关键技术与认知概念，添加 Obsidian [[双链]]
        """
        # 常见核心词汇表（可随知识库扩展）
        common_terms = [
            "大模型", "工作流", "知识图谱", "向量数据库", "智能体", "微调", "量化", 
            "深度学习", "机器学习", "提示工程", "多模态", "Whisper", "LangChain", 
            "Docker", "PyTorch", "Python", "API", "MCP", "n8n", "Coze", "Dify",
            "自动化", "博弈论", "认知科学", "记忆网络", "Obsidian"
        ]
        if extra_tags:
            for t in extra_tags:
                if t and len(t) >= 2 and t not in common_terms:
                    common_terms.append(t)

        # 对正文中的术语打双链（每个术语在正文仅链接前2次，避免过度蓝链）
        for term in common_terms:
            pattern = re.compile(rf'(?<!\[\[)({re.escape(term)})(?!\]\])')
            matches = list(pattern.finditer(text))
            if matches:
                # 倒序替换前两次出现的词
                for m in reversed(matches[:2]):
                    start, end = m.span()
                    text = text[:start] + f"[[{term}]]" + text[end:]
        return text

    def harvest(
        self, 
        raw_text: str, 
        title: str, 
        source_url: str = "", 
        audio_file_path: Optional[str] = None,
        target_vault: str = "inbox", # 默认直接进入 00 Inbox 作为待整理收集箱
        summary_desc: str = "NotebookLM 官方深度研读整理"
    ) -> str:
        """
        核心落盘收割方法
        """
        today = datetime.now().strftime("%Y-%m-%d")
        clean_title = self.clean_filename(title)
        
        # 1. 处理音频播客附件（若用户提供了 NotebookLM 生成的 Audio Overview）
        audio_embed_md = ""
        if audio_file_path and os.path.exists(audio_file_path):
            ext = os.path.splitext(audio_file_path)[1]
            target_audio_name = f"{today}_{clean_title}_播客对谈{ext}"
            target_audio_path = os.path.join(ATTACHMENTS_DIR, target_audio_name)
            shutil.copy2(audio_file_path, target_audio_path)
            audio_embed_md = f"\n> 🎙️ **NotebookLM 双主播播客速览**：\n> ![[{target_audio_name}]]\n"
            print(f"✅ 已将播客音频移入附件库: {target_audio_name}")

        # 2. 清洗正文与添加双链
        sanitized_body = self.sanitize_content(raw_text)
        linked_body = self.extract_keywords_to_wikilinks(sanitized_body)

        # 3. 构造符合 AGENTS.md 规范的完整笔记
        note_content = f"""---
title: {clean_title}
date: {today}
source: {source_url if source_url else "Google NotebookLM"}
type: 外部资料/NotebookLM研读
tags:
  - 外部资料
  - NotebookLM
---

# {clean_title}
{audio_embed_md}
> 来源与出处：{source_url if source_url else "Google NotebookLM 官方分析与研读"}

---

{linked_body}
"""

        # 4. 落盘
        if target_vault == "resource":
            dest_dir = RESOURCE_DIR
            out_file = os.path.join(dest_dir, f"{clean_title}.md")
            index_file = os.path.join(VAULT_ROOT, "30 资源库", "30 资源库_索引.md")
        else:
            dest_dir = INBOX_DIR
            out_file = os.path.join(dest_dir, f"{clean_title}.md")
            index_file = None

        with open(out_file, "w", encoding="utf-8") as f:
            f.write(note_content)

        print(f"🎉 笔记已成功收割落盘！")
        print(f"📄 笔记位置: {out_file}")

        # 5. 更新索引文件（如 30 资源库_索引.md）
        if index_file and os.path.exists(index_file):
            self._update_index(index_file, clean_title, summary_desc)

        return out_file

    def _update_index(self, index_file: str, title: str, summary: str):
        """符合 AGENTS.md 索引页格式：- [[链接|显示名]] — 一句话说明（≤40 字）"""
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                content = f.read()

            entry_link = f"[[{title}]]"
            if entry_link in content:
                print(f"ℹ️ 索引页中已存在该条目，跳过追加")
                return

            entry_line = f"- [[{title}]] — {summary[:40]}\n"
            
            # 追加到对应章节末尾或文件末尾
            if "## 07 外部资料" in content:
                parts = content.split("## 07 外部资料")
                new_content = parts[0] + "## 07 外部资料\n\n" + entry_line + parts[1].lstrip("\n")
            else:
                new_content = content + "\n" + entry_line

            with open(index_file, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"✅ 已自动更新索引文件: {index_file}")
        except Exception as e:
            print(f"⚠️ 更新索引出错: {e}")

if __name__ == "__main__":
    harvester = NotebookLMVaultHarvester()
    print("NotebookLM 收割器已就绪。")
    if len(sys.argv) > 2:
        in_file = sys.argv[1]
        title = sys.argv[2]
        if os.path.exists(in_file):
            with open(in_file, "r", encoding="utf-8") as f:
                text = f.read()
            harvester.harvest(text, title)
