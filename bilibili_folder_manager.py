import os
import sys
import json
import time
import requests
from typing import Dict, Any, List, Optional
from bilibili_user_sync import BilibiliUserSync, COOKIE_FILE
from ai_classifier import EnhancedSemanticClassifier, CATEGORIES_FILE

CREATED_FOLDERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "created_folders.json")

# 确保控制台支持 UTF-8 打印
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

class BilibiliFolderManager:
    """B站收藏夹智能分类与整理器 (免 API Key，多维特征融合优化版)"""

    def __init__(self):
        self.sync_client = BilibiliUserSync()
        self.csrf = self._get_csrf()
        self.classifier = EnhancedSemanticClassifier()

    def _get_csrf(self) -> Optional[str]:
        if os.path.exists(COOKIE_FILE):
            try:
                with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("cookies", {}).get("bili_jct")
            except Exception:
                pass
        return None

    def ensure_login(self) -> bool:
        if not self.sync_client.check_login():
            print("检测到未登录，请先扫码登录...")
            return self.sync_client.qrcode_login()
        self.csrf = self._get_csrf()
        return True

    def _load_created_folders(self) -> List[Dict[str, Any]]:
        if os.path.exists(CREATED_FOLDERS_FILE):
            try:
                with open(CREATED_FOLDERS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_created_folders(self, folders: List[Dict[str, Any]]):
        try:
            with open(CREATED_FOLDERS_FILE, "w", encoding="utf-8") as f:
                json.dump(folders, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def record_created_folder(self, folder_id: int, title: str):
        records = self._load_created_folders()
        if not any(r.get("id") == folder_id for r in records):
            records.append({
                "id": folder_id,
                "title": title,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
            })
            self._save_created_folders(records)

    def remove_recorded_folder(self, folder_id: int):
        records = [r for r in self._load_created_folders() if r.get("id") != folder_id]
        self._save_created_folders(records)

    def get_default_folder(self) -> Optional[Dict[str, Any]]:
        """获取账号的默认收藏夹"""
        folders = self.sync_client.get_favorite_folders()
        if not folders:
            return None
        for f in folders:
            if f.get("title") == "默认收藏夹":
                return f
        for f in folders:
            if f.get("attr") == 0:
                return f
        return folders[0]

    def get_all_folder_aids(self, media_id: int) -> List[int]:
        """获取指定收藏夹内的所有视频 aid (支持自动翻页全量获取)"""
        aids = []
        page = 1
        page_size = 20
        while True:
            url = f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={media_id}&pn={page}&ps={page_size}"
            try:
                resp = self.sync_client.session.get(url, timeout=10).json()
                data = resp.get("data") or {}
                medias = data.get("medias") or []
                if not medias:
                    break
                for m in medias:
                    aid = m.get("id")
                    if aid and aid not in aids and m.get("title") != "已失效视频":
                        aids.append(aid)
                has_more = data.get("has_more", False)
                if not has_more:
                    break
                page += 1
                time.sleep(0.08)
            except Exception:
                break
        return aids

    def create_folder(self, title: str, intro: str = "由智能助理自动分类整理", privacy: int = 1) -> Optional[int]:
        if not self.csrf:
            raise Exception("缺少 csrf 凭据，请重新扫码登录")

        url = "https://api.bilibili.com/x/v3/fav/folder/add"
        data = {
            "title": title,
            "intro": intro,
            "privacy": privacy,
            "csrf": self.csrf
        }
        resp = self.sync_client.session.post(url, data=data, timeout=10)
        res = resp.json()
        if res.get("code") == 0:
            folder_id = res.get("data", {}).get("id")
            print(f"[创建成功] 新建收藏夹【{title}】，ID: {folder_id}")
            self.record_created_folder(folder_id, title)
            return folder_id
        elif res.get("code") == 11203: # 收藏夹已存在
            folders = self.sync_client.get_favorite_folders()
            for f in folders:
                if f["title"] == title:
                    self.record_created_folder(f["id"], title)
                    return f["id"]
        else:
            print(f"[创建失败] 错误: {res.get('message')}")
        return None

    def delete_folder(self, media_id: int) -> bool:
        """删除单个收藏夹"""
        if not self.csrf:
            raise Exception("缺少 csrf 凭据")
        url = "https://api.bilibili.com/x/v3/fav/folder/del"
        data = {
            "media_ids": str(media_id),
            "csrf": self.csrf
        }
        resp = self.sync_client.session.post(url, data=data, timeout=10)
        res = resp.json()
        if res.get("code") == 0:
            self.remove_recorded_folder(media_id)
            return True
        else:
            print(f"删除收藏夹 {media_id} 失败: {res.get('message')}")
            return False

    def batch_copy_to_folder(self, src_media_id: int, tar_media_id: int, aids: List[int]) -> bool:
        if not self.csrf:
            raise Exception("缺少 csrf 凭证")

        if not aids:
            return True

        # 分批复制，每批最多 20 个
        chunk_size = 20
        all_ok = True
        for i in range(0, len(aids), chunk_size):
            chunk = aids[i:i + chunk_size]
            resources_str = ",".join([f"{aid}:2" for aid in chunk])
            copy_url = "https://api.bilibili.com/x/v3/fav/resource/copy"
            data = {
                "src_media_id": src_media_id,
                "tar_media_id": tar_media_id,
                "mid": self.sync_client.mid,
                "resources": resources_str,
                "csrf": self.csrf
            }
            try:
                resp = self.sync_client.session.post(copy_url, data=data, timeout=10)
                res = resp.json()
                if res.get("code") != 0 and res.get("code") != 11201:
                    print(f"  批量复制提示: {res.get('message', '未知错误')}")
                    all_ok = False
            except Exception as e:
                print(f"  批量复制网络异常: {e}")
                all_ok = False
            time.sleep(0.15)
        return all_ok

    def restore_and_delete_folders(
        self, 
        folder_ids: List[int], 
        target_media_id: int, 
        log_callback=None, 
        progress_callback=None
    ) -> Dict[str, Any]:
        """
        核心还原功能：将所选收藏夹中的视频全部搬运复制回默认收藏夹，随后彻底删除这些分类收藏夹。
        """
        if not self.csrf:
            raise Exception("缺少 csrf 凭据，请先登录")

        folders_map = {f["id"]: f for f in self.sync_client.get_favorite_folders()}
        target_folder = folders_map.get(target_media_id)
        target_name = target_folder["title"] if target_folder else "默认收藏夹"

        total = len(folder_ids)
        restored_vids_count = 0
        deleted_folders_count = 0

        for idx, fid in enumerate(folder_ids, 1):
            if fid == target_media_id:
                if log_callback: log_callback(f"⚠️ 跳过目标收藏夹【{target_name}】，不能删除自己")
                continue

            f_info = folders_map.get(fid, {})
            title = f_info.get("title", f"ID:{fid}")

            # 1. 抓取该文件夹下所有视频
            if log_callback: log_callback(f"[{idx}/{total}] 正在读取【{title}】中的所有视频...")
            aids = self.get_all_folder_aids(fid)

            # 2. 复制回默认收藏夹
            if aids:
                if log_callback: log_callback(f"  -> 正在将 {len(aids)} 个视频安全合并回【{target_name}】...")
                self.batch_copy_to_folder(src_media_id=fid, tar_media_id=target_media_id, aids=aids)
                restored_vids_count += len(aids)
            else:
                if log_callback: log_callback(f"  -> 【{title}】为空文件夹，无需搬运视频")

            # 3. 删除该分类文件夹
            if log_callback: log_callback(f"  -> 正在从 B 站删除收藏夹【{title}】...")
            ok = self.delete_folder(fid)
            if ok:
                deleted_folders_count += 1
                if log_callback: log_callback(f"  ✅ 成功删除【{title}】")
            else:
                if log_callback: log_callback(f"  ⚠️ 删除【{title}】失败，可能已被删除")

            if progress_callback:
                progress_callback(idx / total)
            time.sleep(0.3)

        return {
            "deleted_folders": deleted_folders_count,
            "restored_videos": restored_vids_count
        }

    def get_video_tags(self, aid: int) -> List[str]:
        """获取视频 UP 主设置的原生标签 Tags"""
        url = f"https://api.bilibili.com/x/tag/archive/tags?aid={aid}"
        try:
            resp = self.sync_client.session.get(url, timeout=5).json()
            tags = [t.get("tag_name", "") for t in resp.get("data", [])]
            return tags
        except Exception:
            return []

    def auto_classify_favorites(self, limit: int = 30, sync_to_bilibili: bool = False):
        if not self.ensure_login():
            return

        folders = self.sync_client.get_favorite_folders()
        if not folders:
            print("未找到任何收藏夹")
            return

        default_folder = folders[0]
        print(f"\n=======================================================")
        print(f"源收藏夹：【{default_folder['title']}】(共 {default_folder['media_count']} 个视频)")
        print(f"采用模式: ⚡ 免API-Key 本地多维特征加权 (标题 + 简介 + UP主精准Tags)")
        print(f"配置文件: {CATEGORIES_FILE}")
        print(f"正在读取最近收藏的 {limit} 个视频...")
        print(f"=======================================================")

        # 分页获取指定的视频数量
        videos_raw = []
        page = 1
        page_size = 20
        while len(videos_raw) < limit:
            cur_ps = min(page_size, limit - len(videos_raw))
            url = f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={default_folder['id']}&pn={page}&ps={cur_ps}"
            resp = self.sync_client.session.get(url, timeout=10).json()
            data = resp.get("data") or {}
            medias = data.get("medias") or []
            if not medias:
                break
            for m in medias:
                if not m.get("id") or m.get("title") == "已失效视频":
                    continue
                videos_raw.append({
                    "aid": m.get("id"),
                    "bvid": m.get("bvid"),
                    "title": m.get("title"),
                    "intro": m.get("intro", ""),
                    "owner": m.get("upper", {}).get("name", "")
                })
                if len(videos_raw) >= limit:
                    break
            has_more = data.get("has_more", False)
            if not has_more:
                break
            page += 1
            time.sleep(0.08)

        print(f"成功获取到 {len(videos_raw)} 个待整理视频！正在进行特征提取与分类...\n")

        categorized: Dict[str, List[Dict[str, Any]]] = {}
        for idx, v in enumerate(videos_raw, 1):
            # 获取 UP 主精准标签
            tags = self.get_video_tags(v["aid"])
            cat = self.classifier.classify(v["title"], v["intro"], v["owner"], tags=tags)
            categorized.setdefault(cat, []).append(v)
            tags_preview = ",".join(tags[:3]) if tags else "无标签"
            print(f"[{idx:02d}] 归入【{cat}】: {v['title'][:28]}... (标签: {tags_preview})")
            time.sleep(0.05)

        print("\n================== 📊 优化后的分类归纳总览 ==================")
        for cat, vids in categorized.items():
            print(f"📂 分类【{cat}】 ({len(vids)} 个视频):")
            for i, vid in enumerate(vids[:4], 1):
                print(f"   {i}. {vid['title'][:32]} (UP主: {vid['owner']})")
            if len(vids) > 4:
                print(f"   ...以及其余 {len(vids) - 4} 个视频")
            print()

        if not sync_to_bilibili:
            print("-------------------------------------------------------")
            print("💡 当前为【预览模式】。")
            print("如果确认分类效果满意，请执行：")
            print(f"python bilibili_folder_manager.py {limit} --apply")
            print("-------------------------------------------------------")
            return

        print("🚀 正在批量同步至您的 B 站账号...")
        all_folders = {f["title"]: f["id"] for f in self.sync_client.get_favorite_folders()}

        for cat, vids in categorized.items():
            tar_id = all_folders.get(cat)
            if not tar_id:
                tar_id = self.create_folder(title=cat, intro="AI智能归档分类", privacy=1)
                if tar_id:
                    all_folders[cat] = tar_id

            if not tar_id:
                print(f"[跳过] 无法获取分类【{cat}】的收藏夹ID")
                continue

            aids = [v["aid"] for v in vids if v.get("aid")]
            print(f"正在将 {len(aids)} 个视频批量复制到【{cat}】...")
            ok = self.batch_copy_to_folder(
                src_media_id=default_folder["id"],
                tar_media_id=tar_id,
                aids=aids
            )
            if ok:
                print(f"✅ 成功将 {len(aids)} 个视频归入【{cat}】！")
            else:
                print(f"⚠️ 分类【{cat}】部分视频复制失败或已在其中")
            time.sleep(0.5)

        print("\n🎉 全部整理归纳完成！您可以现在打开手机【哔哩哔哩 APP】的【我的收藏】刷新查看！")

if __name__ == "__main__":
    manager = BilibiliFolderManager()
    if "--restore" in sys.argv:
        if not manager.ensure_login():
            sys.exit(1)
        default_f = manager.get_default_folder()
        if not default_f:
            print("未找到默认收藏夹！")
            sys.exit(1)
        folders = manager.sync_client.get_favorite_folders()
        custom_f = [f for f in folders if f["id"] != default_f["id"]]
        if not custom_f:
            print("没有找到需要清理的分类收藏夹。")
            sys.exit(0)
        print(f"找到 {len(custom_f)} 个分类收藏夹，准备全部搬回【{default_f['title']}】并删除...")
        res = manager.restore_and_delete_folders(
            folder_ids=[f["id"] for f in custom_f],
            target_media_id=default_f["id"],
            log_callback=print
        )
        print(f"还原完成: {res}")
        sys.exit(0)

    apply_mode = "--apply" in sys.argv
    count = 15
    for arg in sys.argv:
        if arg.isdigit():
            count = int(arg)
    manager.auto_classify_favorites(limit=count, sync_to_bilibili=apply_mode)
