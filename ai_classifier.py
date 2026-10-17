import os
import sys
import json
import re
import time
from typing import Dict, Any, List, Optional, Callable, Tuple
import requests
from config import ConfigManager, DEFAULT_SELECTED_TOPICS

# 确保 UTF-8 打印
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

class DualEngineClassifier:
    """双引擎智能分类器：
    - DeepSeek 大模型模式：结合用户挑选的文件夹 + 个人需求上下文，智能统筹归类
    - 本地模式：按用户挑选的文件夹进行多维特征加权匹配
    """

    def __init__(self):
        self.reload_config()

    def reload_config(self):
        self.cfg = ConfigManager.load_config()
        self.api_key = self.cfg.get("api_key", "").strip()
        self.base_url = self.cfg.get("base_url", "https://api.deepseek.com/v1").strip()
        self.model = self.cfg.get("model", "deepseek-flash").strip()
        # 用户当前选定的目标文件夹
        self.selected_topics = self.cfg.get("selected_topics", DEFAULT_SELECTED_TOPICS)
        self.user_instruction = self.cfg.get("user_instruction", "").strip()
        self.default_category = "综合知识与备忘"

    def has_llm(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def test_connection(api_key: str, base_url: str, model: str) -> Tuple[bool, str]:
        """测试 DeepSeek 接口连通性"""
        if not api_key:
            return False, "请先输入 API Key！"
        if not base_url:
            return False, "接口地址 (Base URL) 不能为空！"
        if not model:
            return False, "请选择模型！"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "请只回复两个字：收到"}],
            "max_tokens": 10
        }

        start_t = time.time()
        try:
            url = f"{base_url.rstrip('/')}/chat/completions"
            resp = requests.post(url, headers=headers, json=payload, timeout=12)
            elapsed = int((time.time() - start_t) * 1000)

            if resp.status_code == 200:
                res_json = resp.json()
                reply = res_json["choices"][0]["message"]["content"].strip()
                return True, f"连接成功！延迟: {elapsed}ms\n模型回复: {reply}"
            elif resp.status_code == 401:
                return False, "【401 未授权】API Key 错误、已过期或未激活！"
            elif resp.status_code == 402:
                return False, "【402 余额不足】您的账户余额已用尽，请先充值！"
            elif resp.status_code == 404:
                return False, f"【404 模型未找到】当前平台未找到模型【{model}】，请核对！"
            elif resp.status_code == 429:
                return False, "【429 请求过多】触发官方限流，请稍后重试！"
            else:
                return False, f"HTTP {resp.status_code} 错误: {resp.text[:120]}"
        except requests.exceptions.Timeout:
            return False, "连接超时 (12秒)，请检查网络连接！"
        except requests.exceptions.ConnectionError:
            return False, f"无法连接到地址: {base_url}，请检查 URL！"
        except Exception as e:
            return False, f"连接异常: {e}"

    def classify_batch_with_llm(
        self,
        videos: List[Dict[str, Any]],
        log_callback: Optional[Callable[[str], None]] = None
    ) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        """
        大模型自主统揽分类：
        将用户选定的期望文件夹 + 用户的个性化需求 + 视频真实特征，作为完整上下文交由 DeepSeek 一体化决策
        """
        if not self.api_key or not videos:
            return None

        # 用户选定的文件夹列表
        user_topics_str = "、".join([f"【{t['name']}】" for t in self.selected_topics])
        topics_desc = "\n".join([f"- 【{t['name']}】：关注方向 ({t.get('keywords', '')})" for t in self.selected_topics])

        # 视频列表上下文
        video_items_prompt = []
        for i, v in enumerate(videos, 1):
            tags_str = ", ".join(v.get("tags", [])[:5])
            tags_part = f" | 标签: {tags_str}" if tags_str else ""
            intro_clean = v.get("intro", "").replace("\n", " ")[:60]
            intro_part = f" | 简介: {intro_clean}" if intro_clean else ""
            video_items_prompt.append(f"{i}. [UP: {v.get('owner', '未知')}{tags_part}] 《{v.get('title', '')}》{intro_part}")

        context_videos_text = "\n".join(video_items_prompt)

        user_req_text = self.user_instruction.strip()
        user_req_prompt = f"【用户提出的特别归档偏好】: \"{user_req_text}\"\n" if user_req_text else ""

        system_prompt = """你是一个顶级的个人知识与收藏夹智能组织专家。
你的任务是：深入理解用户的分类偏好与需求，整体审阅用户的全部待整理视频，将所有视频精准归入最贴合的分类文件夹中。"""

        user_prompt = f"""【用户已选定的主要文件夹】:
{topics_desc}
- 【{self.default_category}】：若确实完全不匹配任何主要分类，可归入此项。
{user_req_prompt}
【待整理归档的视频清单 (共 {len(videos)} 个)】:
{context_videos_text}

【分类执行与输出规范】:
1. 优先使用用户【已选定的主要文件夹】进行归纳；若用户的【特别归档偏好】有明确指示，必须严格遵守！
2. 将清单中的每个视频（按序号 1 到 {len(videos)}），分配到对应的分类中，确保不漏掉任何一个视频。
3. 必须且只能输出严格的 JSON 对象（不要添加 ```json 等任何包裹标记），格式如下：
{{
  "分类名称A": [1, 3],
  "分类名称B": [2, 4]
}}"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 1200
        }

        if log_callback:
            log_callback(f"🤖 正在调用 DeepSeek ({self.model}) 统揽整理 {len(videos)} 条视频...")

        try:
            url = f"{self.base_url.rstrip('/')}/chat/completions"
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if resp.status_code != 200:
                if log_callback:
                    log_callback(f"⚠️ DeepSeek 响应异常 HTTP {resp.status_code}，已无缝回退本地多维引擎")
                return None

            res_json = resp.json()
            raw_text = res_json["choices"][0]["message"].get("content", "").strip()
            
            # 清除代码块标记
            cleaned_text = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
            cleaned_text = re.sub(r"```\s*$", "", cleaned_text, flags=re.MULTILINE).strip()
            
            json_match = re.search(r"\{.*\}", cleaned_text, re.DOTALL)
            if not json_match:
                if log_callback:
                    log_callback("⚠️ 未能解析出有效 JSON 分类结果，已回退本地引擎")
                return None

            result_map = json.loads(json_match.group(0))
            
            categorized = {}
            for cat_name, idx_list in result_map.items():
                cat_videos = []
                for idx in idx_list:
                    if isinstance(idx, int) and 1 <= idx <= len(videos):
                        cat_videos.append(videos[idx - 1])
                if cat_videos:
                    categorized[cat_name] = cat_videos

            if log_callback:
                log_callback(f"✨ DeepSeek 成功归纳整理出 {len(categorized)} 个分类文件夹！")
            return categorized

        except Exception as e:
            if log_callback:
                log_callback(f"⚠️ 大模型调用异常: {e}，已自动回退本地引擎")
            return None

    def classify_local(self, videos: List[Dict[str, Any]], log_callback: Optional[Callable[[str], None]] = None) -> Dict[str, List[Dict[str, Any]]]:
        """本地模式：使用用户选定的主题进行多维加权匹配"""
        if log_callback:
            log_callback("⚡ 正在使用本地多维加权引擎匹配您挑选的文件夹...")

        categorized: Dict[str, List[Dict[str, Any]]] = {}
        for v in videos:
            tags = v.get("tags", [])
            tags_text = " ".join(tags).lower()
            title_lower = v.get("title", "").lower()
            intro_lower = v.get("intro", "").lower()
            owner_lower = v.get("owner", "").lower()

            best_cat = self.default_category
            highest_score = 0

            for cat in self.selected_topics:
                cat_name = cat["name"]
                kw_str = cat.get("keywords", "")
                raw_keywords = re.findall(r"[\w\u4e00-\u9fa5]+", f"{cat_name} {kw_str}")
                keywords = [kw.lower() for kw in raw_keywords if len(kw) >= 2]

                score = 0
                for kw in keywords:
                    if kw in tags_text: score += 5
                    if kw in title_lower: score += 3
                    elif kw in intro_lower or kw in owner_lower: score += 1

                if score > highest_score:
                    highest_score = score
                    best_cat = cat_name

            target_category = best_cat if highest_score >= 3 else self.default_category
            categorized.setdefault(target_category, []).append(v)

        return categorized

    def classify_all(
        self,
        videos: List[Dict[str, Any]],
        log_callback: Optional[Callable[[str], None]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        if self.has_llm():
            res = self.classify_batch_with_llm(videos, log_callback)
            if res:
                return res
        return self.classify_local(videos, log_callback)

# 兼容别名
EnhancedSemanticClassifier = DualEngineClassifier
CATEGORIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "categories.json")
