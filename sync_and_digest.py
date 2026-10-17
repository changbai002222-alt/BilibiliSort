import os
import sys
from bilibili_user_sync import BilibiliUserSync
from video_hub import VideoKnowledgeHub

# 确保控制台支持 UTF-8 打印
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def sync_my_favorites(limit_per_folder: int = 3):
    """同步个人收藏夹并自动提炼知识"""
    user_sync = BilibiliUserSync()
    
    # 检查登录
    if not user_sync.check_login():
        print("尚未登录，正在启动扫码登录...")
        if not user_sync.qrcode_login():
            print("登录失败，已退出")
            return

    hub = VideoKnowledgeHub()

    # 获取所有收藏夹
    folders = user_sync.get_favorite_folders()
    if not folders:
        print("未获取到任何收藏夹")
        return

    print(f"\n[B站] 找到 {len(folders)} 个收藏夹：")
    for idx, f in enumerate(folders, 1):
        print(f"  [{idx}] {f['title']} (共 {f['media_count']} 个视频)")

    # 默认处理第一个收藏夹（通常为“默认收藏夹”）
    target_folder = folders[0]
    print(f"\n===> 正在处理收藏夹：【{target_folder['title']}】 (获取最新 {limit_per_folder} 条)")
    videos = user_sync.get_favorite_videos(target_folder["id"], page_size=limit_per_folder)

    for idx, v in enumerate(videos, 1):
        print(f"\n---------------------------------------------")
        print(f"[{idx}/{len(videos)}] 开始同步: {v['title']}")
        print(f"UP主: {v['owner']} | 链接: {v['link']}")
        try:
            hub.process_bilibili(v["bvid"])
        except Exception as e:
            print(f"[跳过] 提取失败: {e}")

    print("\n=============================================")
    print("全部最新收藏视频已成功转录并沉淀至 knowledge_base/ 目录！")

if __name__ == "__main__":
    count = 3
    if len(sys.argv) > 1:
        try:
            count = int(sys.argv[1])
        except ValueError:
            pass
    sync_my_favorites(limit_per_folder=count)
