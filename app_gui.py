import os
import sys
import json
import time
import threading
import requests
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from PIL import Image, ImageTk
import qrcode

# 确保 UTF-8 打印
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from bilibili_user_sync import BilibiliUserSync, COOKIE_FILE
from ai_classifier import DualEngineClassifier
from bilibili_folder_manager import BilibiliFolderManager
from config import ConfigManager, SUGGESTED_TOPICS_POOL, DEFAULT_SELECTED_TOPICS

ICON_ICO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.ico")
ICON_PNG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.png")

# 配色规范：元气粉蓝
THEME_PINK = "#FB7299"
THEME_PINK_HOVER = "#E05A80"
THEME_BLUE = "#00AEEC"
THEME_BLUE_HOVER = "#0093C7"
THEME_YELLOW = "#FFB027"
THEME_GREEN = "#10B981"
BG_DARK = "#1E1B24"
CARD_DARK = "#272431"
CARD_INNER = "#1B1922"

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class CuteBiliSortApp(ctk.CTk):
    """BiliSort - 哔哩哔哩智能收藏夹整理助手 (主题灵感池点选版)"""

    def __init__(self):
        super().__init__()

        self.title("BiliSort · 哔哩哔哩收藏夹智能整理")
        self.geometry("1080x760")
        self.minsize(980, 680)

        # 设置窗口图标
        if os.path.exists(ICON_ICO_PATH):
            try:
                self.iconbitmap(ICON_ICO_PATH)
            except Exception:
                pass

        # 核心逻辑实例
        self.folder_manager = BilibiliFolderManager()
        self.user_sync = self.folder_manager.sync_client
        self.classifier = DualEngineClassifier()

        self.categorized_results = {}
        self.current_videos_raw = []
        self.folders_cache = []

        # 构建界面布局
        self._init_layout()

        # 异步检查已有登录
        threading.Thread(target=self._check_login_async, daemon=True).start()

    def _init_layout(self):
        self.configure(fg_color=BG_DARK)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ================= 1. 左侧边栏 (控制与主题点选) =================
        self.sidebar = ctk.CTkFrame(self, width=330, corner_radius=20, fg_color=CARD_DARK)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(15, 10), pady=15)
        self.sidebar.grid_rowconfigure(14, weight=1)

        # 1.1 品牌 Logo 与图标
        self.brand_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.brand_frame.grid(row=0, column=0, padx=20, pady=(20, 8), sticky="ew")

        if os.path.exists(ICON_PNG_PATH):
            try:
                pil_icon = Image.open(ICON_PNG_PATH)
                self.app_icon_img = ctk.CTkImage(light_image=pil_icon, dark_image=pil_icon, size=(52, 52))
                self.icon_lbl = ctk.CTkLabel(self.brand_frame, image=self.app_icon_img, text="")
                self.icon_lbl.pack(side="left", padx=(0, 10))
            except Exception:
                pass

        self.brand_text_frame = ctk.CTkFrame(self.brand_frame, fg_color="transparent")
        self.brand_text_frame.pack(side="left", fill="both", expand=True)

        self.logo_label = ctk.CTkLabel(
            self.brand_text_frame, text="BiliSort", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=22, weight="bold"),
            text_color="#FFFFFF"
        )
        self.logo_label.pack(anchor="w")

        self.sub_logo = ctk.CTkLabel(
            self.brand_text_frame, text="AI 收藏夹整理官 ✨", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=12),
            text_color=THEME_PINK
        )
        self.sub_logo.pack(anchor="w")

        # 1.2 账号卡片
        self.user_card = ctk.CTkFrame(self.sidebar, corner_radius=14, fg_color=CARD_INNER, border_width=1, border_color="#363242")
        self.user_card.grid(row=1, column=0, padx=15, pady=6, sticky="ew")

        self.user_status_label = ctk.CTkLabel(
            self.user_card, text="⚪ 检测登录状态中...", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=13, weight="bold"),
            text_color="#B3B0BE"
        )
        self.user_status_label.pack(padx=14, pady=(10, 4), anchor="w")

        self.login_btn = ctk.CTkButton(
            self.user_card, text="📱 手机扫码登录 B 站", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold"),
            fg_color=THEME_PINK, hover_color=THEME_PINK_HOVER,
            corner_radius=10, height=32,
            command=self.open_qr_window
        )
        self.login_btn.pack(padx=12, pady=(4, 10), fill="x")

        # 1.3 DeepSeek 引擎状态与设置
        self.ai_card = ctk.CTkFrame(self.sidebar, corner_radius=14, fg_color=CARD_INNER, border_width=1, border_color="#363242")
        self.ai_card.grid(row=2, column=0, padx=15, pady=6, sticky="ew")

        self.ai_status_lbl = ctk.CTkLabel(
            self.ai_card, text=self._get_ai_status_text(),
            font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold"),
            text_color=THEME_GREEN if self.classifier.has_llm() else THEME_BLUE
        )
        self.ai_status_lbl.pack(padx=14, pady=(8, 4), anchor="w")

        self.api_btn = ctk.CTkButton(
            self.ai_card, text="🤖 配置 DeepSeek API Key", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=12),
            fg_color="#363242", hover_color="#454054",
            corner_radius=10, height=30,
            command=self.open_deepseek_settings
        )
        self.api_btn.pack(padx=12, pady=(2, 8), fill="x")

        # 1.4 当前选中的目标文件夹管理面板
        self.topics_frame = ctk.CTkFrame(self.sidebar, corner_radius=14, fg_color=CARD_INNER, border_width=1, border_color="#363242")
        self.topics_frame.grid(row=3, column=0, padx=15, pady=6, sticky="ew")

        self.topics_title_bar = ctk.CTkFrame(self.topics_frame, fg_color="transparent")
        self.topics_title_bar.pack(fill="x", padx=12, pady=(8, 4))

        self.topics_title_lbl = ctk.CTkLabel(
            self.topics_title_bar, 
            text=f"📁 当前目标文件夹 ({len(self.classifier.selected_topics)}个)", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold"),
            text_color="#EDEAF5"
        )
        self.topics_title_lbl.pack(side="left")

        # 主题库弹窗挑选按钮
        self.pick_topics_btn = ctk.CTkButton(
            self.topics_title_bar, text="➕ 挑选题材库", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=11),
            fg_color=THEME_BLUE, hover_color=THEME_BLUE_HOVER,
            corner_radius=8, width=86, height=24,
            command=self.open_topics_market
        )
        self.pick_topics_btn.pack(side="right")

        # 展示当前选中的文件夹徽章 (滚动小卡片)
        self.badges_box = ctk.CTkScrollableFrame(self.topics_frame, height=110, corner_radius=8, fg_color="#18161F")
        self.badges_box.pack(fill="x", padx=10, pady=(0, 8))
        self._refresh_selected_badges()

        # 1.5 你的特别个性化需求
        self.pref_lbl = ctk.CTkLabel(
            self.sidebar, text="💡 你的特别偏好说明 (可选)：", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=11, weight="bold"),
            text_color="#EDEAF5"
        )
        self.pref_lbl.grid(row=4, column=0, padx=18, pady=(8, 2), sticky="w")

        cfg = ConfigManager.load_config()
        self.pref_entry = ctk.CTkEntry(
            self.sidebar, 
            placeholder_text="例如: 考研内容放优先; 搞笑放单独类...",
            corner_radius=10, fg_color=CARD_INNER, border_color="#363242",
            height=32, font=ctk.CTkFont(family="Microsoft YaHei", size=11)
        )
        if cfg.get("user_instruction"):
            self.pref_entry.insert(0, cfg["user_instruction"])
        self.pref_entry.grid(row=5, column=0, padx=15, pady=(2, 6), sticky="ew")

        # 1.6 收藏夹与数量选择
        self.folder_select_label = ctk.CTkLabel(
            self.sidebar, text="选择源收藏夹：", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=12),
            text_color="#9B97A8"
        )
        self.folder_select_label.grid(row=6, column=0, padx=18, pady=(4, 2), sticky="w")
        
        self.folder_combo = ctk.CTkComboBox(
            self.sidebar, values=["请先登录以加载"],
            corner_radius=10, fg_color=CARD_INNER, border_color="#363242",
            button_color=THEME_BLUE, button_hover_color=THEME_BLUE_HOVER
        )
        self.folder_combo.grid(row=7, column=0, padx=15, pady=(2, 6), sticky="ew")

        # 全量整理勾选框
        self.all_vids_var = tk.BooleanVar(value=False)
        self.all_vids_cb = ctk.CTkCheckBox(
            self.sidebar, text="🔥 全量整理 (整个收藏夹全部视频)", 
            variable=self.all_vids_var,
            font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold"),
            fg_color=THEME_PINK, hover_color=THEME_PINK_HOVER,
            command=self._on_toggle_all_vids
        )
        self.all_vids_cb.grid(row=8, column=0, padx=18, pady=(4, 4), sticky="w")

        self.count_label = ctk.CTkLabel(
            self.sidebar, text="整理最近收藏: 50 个", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=12),
            text_color="#9B97A8"
        )
        self.count_label.grid(row=9, column=0, padx=18, pady=(2, 2), sticky="w")

        self.count_slider = ctk.CTkSlider(
            self.sidebar, from_=10, to=1500, number_of_steps=149,
            button_color=THEME_PINK, button_hover_color=THEME_PINK_HOVER,
            progress_color=THEME_BLUE, command=self._on_slider_change
        )
        self.count_slider.set(50)
        self.count_slider.grid(row=10, column=0, padx=15, pady=(2, 12), sticky="ew")

        # ================= 2. 右侧主工作区 =================
        self.main_frame = ctk.CTkFrame(self, corner_radius=20, fg_color=CARD_DARK)
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 15), pady=15)
        self.main_frame.grid_rowconfigure(2, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        # 2.1 顶部操作条
        self.action_frame = ctk.CTkFrame(self.main_frame, corner_radius=16, fg_color=CARD_INNER, border_width=1, border_color="#363242")
        self.action_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=16)

        self.analyze_btn = ctk.CTkButton(
            self.action_frame, 
            text="🔍 智能分析 (预览)", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=13, weight="bold"),
            fg_color=THEME_BLUE, hover_color=THEME_BLUE_HOVER,
            corner_radius=12, width=145, height=38,
            command=self.start_analyze
        )
        self.analyze_btn.pack(side="left", padx=(14, 6), pady=12)

        self.sync_btn = ctk.CTkButton(
            self.action_frame, 
            text="🚀 一键归类到 B 站", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=13, weight="bold"),
            fg_color=THEME_PINK, hover_color=THEME_PINK_HOVER,
            corner_radius=12, width=145, height=38,
            command=self.start_sync, state="disabled"
        )
        self.sync_btn.pack(side="left", padx=6, pady=12)

        self.restore_btn = ctk.CTkButton(
            self.action_frame, 
            text="🧹 撤销并还原收藏夹", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=13, weight="bold"),
            fg_color="#363242", hover_color="#EF4444", text_color="#EDEAF5",
            corner_radius=12, width=155, height=38,
            command=self.open_restore_dialog
        )
        self.restore_btn.pack(side="left", padx=6, pady=12)

        self.status_tip = ctk.CTkLabel(
            self.action_frame, 
            text="✨ 就绪：请点击【智能分析】开始预览", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=12),
            text_color="#B3B0BE"
        )
        self.status_tip.pack(side="right", padx=16, pady=12)

        # 2.2 进度条
        self.progress_bar = ctk.CTkProgressBar(
            self.main_frame, corner_radius=6, height=8,
            progress_color=THEME_PINK, fg_color=CARD_INNER
        )
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        self.progress_bar.set(0)

        # 2.3 分类卡片展示区
        self.result_scroll = ctk.CTkScrollableFrame(
            self.main_frame, label_text="📊 智能分类结果看板 (未开始)",
            label_font=ctk.CTkFont(family="Microsoft YaHei", size=14, weight="bold"),
            label_text_color="#EDEAF5", corner_radius=16, fg_color=CARD_INNER
        )
        self.result_scroll.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 14))
        self.result_scroll.grid_columnconfigure(0, weight=1)

        self.empty_lbl = ctk.CTkLabel(
            self.result_scroll, 
            text="🎉 点击上方【智能分析】，AI 将根据您挑好的目标文件夹进行分类！", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=13),
            text_color="#7B7788"
        )
        self.empty_lbl.pack(pady=60)

        # 2.4 底部控制台日志
        self.log_box = ctk.CTkTextbox(
            self.main_frame, height=96, corner_radius=12,
            fg_color=CARD_INNER, border_width=1, border_color="#363242",
            font=ctk.CTkFont(family="Consolas", size=11), text_color="#B3B0BE"
        )
        self.log_box.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 16))
        self.log("BiliSort 智能收藏夹整理助手已就绪！")

    def _get_ai_status_text(self) -> str:
        if self.classifier.has_llm():
            return f"🟢 DeepSeek 意图自主归类 ({self.classifier.model})"
        return "⚡ 本地多维加权引擎 (免 Key)"

    def log(self, text: str):
        t_str = time.strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{t_str}] {text}\n")
        self.log_box.see("end")

    def _on_slider_change(self, value):
        self.count_label.configure(text=f"整理最近收藏: {int(value)} 个")

    def _on_toggle_all_vids(self):
        if self.all_vids_var.get():
            self.count_slider.configure(state="disabled")
            self.count_label.configure(text="整理范围: ⚡ 收藏夹全部视频 (全量扫描)", text_color=THEME_PINK)
        else:
            self.count_slider.configure(state="normal")
            val = int(self.count_slider.get())
            self.count_label.configure(text=f"整理最近收藏: {val} 个", text_color="#9B97A8")

    def _refresh_selected_badges(self):
        """刷新侧边栏已选中的文件夹胶囊列表"""
        for w in self.badges_box.winfo_children(): w.destroy()
        topics = self.classifier.selected_topics
        self.topics_title_lbl.configure(text=f"📁 当前目标文件夹 ({len(topics)}个)")

        for idx, t in enumerate(topics):
            row = ctk.CTkFrame(self.badges_box, fg_color="transparent")
            row.pack(fill="x", pady=2)

            name_lbl = ctk.CTkLabel(
                row, text=f"• {t['name']}", 
                font=ctk.CTkFont(family="Microsoft YaHei", size=12),
                text_color="#E0DDEB", anchor="w"
            )
            name_lbl.pack(side="left", fill="x", expand=True)

            def make_del_badge_cmd(i=idx):
                def del_badge():
                    if len(topics) <= 1:
                        messagebox.showwarning("提示", "至少保留一个文件夹分类哦！")
                        return
                    topics.pop(i)
                    cfg = ConfigManager.load_config()
                    cfg["selected_topics"] = topics
                    ConfigManager.save_config(cfg)
                    self.classifier.reload_config()
                    self._refresh_selected_badges()
                return del_badge

            del_btn = ctk.CTkButton(
                row, text="✕", width=22, height=18,
                fg_color="#363242", hover_color="#EF4444", text_color="#B3B0BE",
                corner_radius=4, font=ctk.CTkFont(size=10),
                command=make_del_badge_cmd(idx)
            )
            del_btn.pack(side="right")

    # ================= 弹窗：海量常见主题灵感超市 (点击直接加) =================
    def open_topics_market(self):
        win = ctk.CTkToplevel(self)
        win.title("💡 常见收藏夹主题灵感池 (点击直接添加)")
        win.geometry("680x580")
        win.configure(fg_color=BG_DARK)
        win.grab_set()

        ctk.CTkLabel(
            win, text="🌟 为您想好的精选文件夹主题（看中哪个，点一下直接加入）：", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=13, weight="bold"),
            text_color="#EDEAF5"
        ).pack(pady=(16, 6))

        scroll = ctk.CTkScrollableFrame(win, width=620, height=380, corner_radius=14, fg_color=CARD_DARK)
        scroll.pack(padx=20, pady=6, fill="both", expand=True)

        current_names = {t["name"] for t in self.classifier.selected_topics}

        # 按照 2 列网格卡片排列
        grid_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        grid_frame.pack(fill="both", expand=True, padx=4, pady=4)
        grid_frame.grid_columnconfigure((0, 1), weight=1)

        for idx, item in enumerate(SUGGESTED_TOPICS_POOL):
            card = ctk.CTkFrame(grid_frame, corner_radius=10, fg_color=CARD_INNER, border_width=1, border_color="#363242")
            r = idx // 2
            c = idx % 2
            card.grid(row=r, column=c, padx=6, pady=5, sticky="ew")

            top_line = ctk.CTkFrame(card, fg_color="transparent")
            top_line.pack(fill="x", padx=10, pady=(6, 2))

            ctk.CTkLabel(
                top_line, text=item["name"], 
                font=ctk.CTkFont(family="Microsoft YaHei", size=13, weight="bold"),
                text_color=THEME_BLUE
            ).pack(side="left")

            is_already_added = item["name"] in current_names

            def make_add_cmd(topic=item):
                def add_it():
                    if topic["name"] in {t["name"] for t in self.classifier.selected_topics}:
                        return
                    self.classifier.selected_topics.append(topic)
                    cfg = ConfigManager.load_config()
                    cfg["selected_topics"] = self.classifier.selected_topics
                    ConfigManager.save_config(cfg)
                    self.classifier.reload_config()
                    self._refresh_selected_badges()
                    win.destroy()
                    self.open_topics_market() # 刷新状态
                return add_it

            status_btn = ctk.CTkButton(
                top_line, 
                text="已添加 ✓" if is_already_added else "+ 点击添加",
                width=72, height=24, corner_radius=6,
                font=ctk.CTkFont(family="Microsoft YaHei", size=11),
                fg_color="#363242" if is_already_added else THEME_PINK,
                hover_color=THEME_PINK_HOVER,
                state="disabled" if is_already_added else "normal",
                command=make_add_cmd(item)
            )
            status_btn.pack(side="right")

            # 简略关键词
            ctk.CTkLabel(
                card, text=f"包含: {item['keywords'][:26]}...", 
                font=ctk.CTkFont(family="Microsoft YaHei", size=11),
                text_color="#9B97A8", anchor="w"
            ).pack(fill="x", padx=10, pady=(0, 6))

        # 底部手打自定义输入框
        custom_bar = ctk.CTkFrame(win, corner_radius=12, fg_color=CARD_DARK, border_width=1, border_color="#363242")
        custom_bar.pack(padx=20, pady=(4, 15), fill="x")

        inputs = ctk.CTkFrame(custom_bar, fg_color="transparent")
        inputs.pack(fill="x", padx=12, pady=10)

        name_in = ctk.CTkEntry(inputs, placeholder_text="没找到想要的主题？直接手打名字 (如: 吉他指弹教学)", width=230, corner_radius=8)
        name_in.pack(side="left", padx=(0, 8))

        kw_in = ctk.CTkEntry(inputs, placeholder_text="相关关注词 (如: 吉他, 和弦, 谱子)", corner_radius=8)
        kw_in.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def add_custom():
            n = name_in.get().strip()
            k = kw_in.get().strip()
            if not n:
                messagebox.showwarning("提示", "请输入主题名字！")
                return
            new_item = {"name": n, "keywords": k}
            self.classifier.selected_topics.append(new_item)
            cfg = ConfigManager.load_config()
            cfg["selected_topics"] = self.classifier.selected_topics
            ConfigManager.save_config(cfg)
            self.classifier.reload_config()
            self._refresh_selected_badges()
            name_in.delete(0, "end")
            kw_in.delete(0, "end")
            win.destroy()
            self.open_topics_market()

        ctk.CTkButton(
            inputs, text="+ 添加", width=68, 
            fg_color=THEME_PINK, hover_color=THEME_PINK_HOVER, corner_radius=8,
            command=add_custom
        ).pack(side="right")

    # ================= 弹窗：DeepSeek 专属极简配置 =================
    def open_deepseek_settings(self):
        win = ctk.CTkToplevel(self)
        win.title("🤖 配置 DeepSeek API")
        win.geometry("480x400")
        win.configure(fg_color=BG_DARK)
        win.grab_set()

        ctk.CTkLabel(
            win, text="🌟 DeepSeek 专属配置 (结合您挑选的主题统筹分类)", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=13, weight="bold"),
            text_color="#EDEAF5"
        ).pack(pady=(18, 8))

        frame = ctk.CTkFrame(win, corner_radius=14, fg_color=CARD_DARK, border_width=1, border_color="#363242")
        frame.pack(padx=20, pady=8, fill="both", expand=True)

        cfg = ConfigManager.load_config()

        ctk.CTkLabel(frame, text="选择 DeepSeek 模型版本：", font=ctk.CTkFont(family="Microsoft YaHei", size=12)).pack(padx=16, pady=(12, 4), anchor="w")
        
        model_options = ["deepseek-flash", "deepseek-v4-pro"]
        model_combo = ctk.CTkComboBox(frame, values=model_options, corner_radius=10, width=420)
        cur_model = cfg.get("model", "deepseek-flash")
        if cur_model not in model_options:
            cur_model = "deepseek-flash"
        model_combo.set(cur_model)
        model_combo.pack(padx=16, pady=(0, 10))

        ctk.CTkLabel(frame, text="API Key：", font=ctk.CTkFont(family="Microsoft YaHei", size=12)).pack(padx=16, pady=(4, 2), anchor="w")
        key_entry = ctk.CTkEntry(frame, placeholder_text="sk-...", show="*", corner_radius=10, width=420)
        if cfg.get("api_key"):
            key_entry.insert(0, cfg["api_key"])
        key_entry.pack(padx=16, pady=(0, 10))

        ctk.CTkLabel(frame, text="接口地址 (Base URL)：", font=ctk.CTkFont(family="Microsoft YaHei", size=12)).pack(padx=16, pady=(4, 2), anchor="w")
        url_entry = ctk.CTkEntry(frame, corner_radius=10, width=420)
        url_entry.insert(0, cfg.get("base_url", "https://api.deepseek.com/v1"))
        url_entry.pack(padx=16, pady=(0, 12))

        btn_bar = ctk.CTkFrame(win, fg_color="transparent")
        btn_bar.pack(pady=(0, 16), padx=20, fill="x")

        def test_llm():
            k = key_entry.get().strip()
            u = url_entry.get().strip()
            m = model_combo.get().strip()
            test_btn.configure(state="disabled", text="测试中...")
            
            def run_test():
                ok, msg = DualEngineClassifier.test_connection(k, u, m)
                test_btn.configure(state="normal", text="⚡ 测试连通性")
                if ok:
                    messagebox.showinfo("测试通过", f"🎉 {msg}")
                else:
                    messagebox.showerror("测试失败", f"❌ 连接失败:\n\n{msg}")

            threading.Thread(target=run_test, daemon=True).start()

        test_btn = ctk.CTkButton(
            btn_bar, text="⚡ 测试连通性", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=13),
            fg_color=THEME_BLUE, hover_color=THEME_BLUE_HOVER,
            corner_radius=10, height=36, width=130,
            command=test_llm
        )
        test_btn.pack(side="left", padx=(0, 10))

        def save_llm():
            cfg["api_key"] = key_entry.get().strip()
            cfg["base_url"] = url_entry.get().strip()
            cfg["model"] = model_combo.get().strip()
            ConfigManager.save_config(cfg)
            self.classifier.reload_config()
            self.ai_status_lbl.configure(
                text=self._get_ai_status_text(),
                text_color=THEME_GREEN if self.classifier.has_llm() else THEME_BLUE
            )
            self.log(f"已保存 DeepSeek 配置: {cfg['model']} @ {cfg['base_url']}")
            messagebox.showinfo("成功", f"🎉 DeepSeek【{cfg['model']}】配置已生效！")
            win.destroy()

        save_btn = ctk.CTkButton(
            btn_bar, text="💾 保存并应用配置", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=13, weight="bold"),
            fg_color=THEME_PINK, hover_color=THEME_PINK_HOVER,
            corner_radius=10, height=36,
            command=save_llm
        )
        save_btn.pack(side="right", fill="x", expand=True)

    # ================= 扫码弹窗 =================
    def open_qr_window(self):
        qr_win = ctk.CTkToplevel(self)
        qr_win.title("手机 B 站扫码授权")
        qr_win.geometry("360x450")
        qr_win.configure(fg_color=BG_DARK)
        qr_win.grab_set()

        tip = ctk.CTkLabel(
            qr_win, text="📱 请打开【手机哔哩哔哩 APP】\n扫一扫下方二维码确认登录", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=14, weight="bold"),
            text_color="#EDEAF5"
        )
        tip.pack(pady=(22, 10))

        qr_card = ctk.CTkFrame(qr_win, corner_radius=16, fg_color=CARD_DARK, border_width=1, border_color="#363242")
        qr_card.pack(padx=20, pady=5)

        qr_label = ctk.CTkLabel(qr_card, text="正在加载二维码...")
        qr_label.pack(padx=16, pady=16)

        status_lbl = ctk.CTkLabel(
            qr_win, text="等待扫码中...", 
            font=ctk.CTkFont(family="Microsoft YaHei", size=13),
            text_color=THEME_BLUE
        )
        status_lbl.pack(pady=10)

        def poll_qr():
            gen_url = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
            r = self.user_sync.session.get(gen_url, timeout=10).json()
            if r.get("code") != 0:
                status_lbl.configure(text="二维码生成失败", text_color="#EF4444")
                return

            login_url = r["data"]["url"]
            qrcode_key = r["data"]["qrcode_key"]

            qr = qrcode.QRCode(box_size=5, border=1)
            qr.add_data(login_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            ctk_img = ctk.CTkImage(light_image=img.get_image(), size=(190, 190))
            qr_label.configure(image=ctk_img, text="")

            poll_url = f"https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key={qrcode_key}"
            start_t = time.time()
            while time.time() - start_t < 180 and qr_win.winfo_exists():
                p_resp = self.user_sync.session.get(poll_url, timeout=10).json()
                code = p_resp.get("data", {}).get("code")
                if code == 0:
                    status_lbl.configure(text="🎉 登录成功！", text_color="#10B981")
                    cookies_dict = requests.utils.dict_from_cookiejar(self.user_sync.session.cookies)
                    self.user_sync.check_login()
                    self.user_sync.save_cookies(cookies_dict, self.user_sync.mid)
                    self.folder_manager.csrf = self.folder_manager._get_csrf()
                    time.sleep(1)
                    qr_win.destroy()
                    self._check_login_async()
                    return
                elif code == 86090:
                    status_lbl.configure(text="已扫码，请在手机上点击确认", text_color=THEME_PINK)
                elif code == 86038:
                    status_lbl.configure(text="二维码已失效，请重新打开", text_color="#EF4444")
                    break
                time.sleep(1.5)

        threading.Thread(target=poll_qr, daemon=True).start()

    def _check_login_async(self):
        self.log("正在验证登录状态...")
        if self.user_sync.check_login():
            uname = ""
            try:
                nav = self.user_sync.session.get("https://api.bilibili.com/x/web-interface/nav").json()
                uname = nav.get("data", {}).get("uname", "")
            except Exception:
                pass
            display_name = f"🟢 已登录: {uname}" if uname else f"🟢 UID: {self.user_sync.mid}"
            self.user_status_label.configure(text=display_name, text_color=THEME_GREEN)
            self.login_btn.configure(text="切换登录账号")
            self.log(f"登录有效，账号: {uname} (UID: {self.user_sync.mid})")
            self._reload_folders()
        else:
            self.user_status_label.configure(text="🔴 尚未登录", text_color="#EF4444")
            self.log("尚未登录，请点击【手机扫码登录 B 站】")

    def _reload_folders(self):
        try:
            self.folders_cache = self.user_sync.get_favorite_folders()
            titles = [f"{f['title']} ({f['media_count']}个)" for f in self.folders_cache]
            if titles:
                self.folder_combo.configure(values=titles)
                self.folder_combo.set(titles[0])
                self.log(f"已同步加载 {len(titles)} 个收藏夹！")
        except Exception as e:
            self.log(f"加载收藏夹失败: {e}")

    # ================= 撤销整理：一键放回默认收藏夹并删除分类 =================
    def open_restore_dialog(self):
        """打开一键撤销整理、放回默认收藏夹并删除分类收藏夹的对话框"""
        if not self.user_sync.mid:
            messagebox.showwarning("提示", "请先点击左侧【手机扫码登录 B 站】哦！")
            return

        try:
            folders = self.user_sync.get_favorite_folders()
        except Exception as e:
            messagebox.showerror("错误", f"获取收藏夹列表失败: {e}")
            return

        default_folder = self.folder_manager.get_default_folder()
        if not default_folder:
            messagebox.showwarning("提示", "未能识别到您的【默认收藏夹】")
            return

        # 筛选出除默认收藏夹以外的全部自定义分类收藏夹
        custom_folders = [f for f in folders if f["id"] != default_folder["id"]]
        if not custom_folders:
            messagebox.showinfo("提示", f"您的账号当前仅有【{default_folder['title']}】，没有需要还原清理的分类收藏夹。")
            return

        created_records = self.folder_manager._load_created_folders()
        created_ids = {r.get("id") for r in created_records}

        win = ctk.CTkToplevel(self)
        win.title("🧹 撤销整理 · 还原并删除分类收藏夹")
        win.geometry("640x600")
        win.minsize(580, 520)
        win.configure(fg_color=BG_DARK)
        win.grab_set()

        # 顶部提示卡片
        info_card = ctk.CTkFrame(win, corner_radius=14, fg_color=CARD_DARK, border_width=1, border_color="#363242")
        info_card.pack(fill="x", padx=18, pady=(16, 8))

        ctk.CTkLabel(
            info_card, text="📦 收藏内容安全放回默认收藏夹",
            font=ctk.CTkFont(family="Microsoft YaHei", size=14, weight="bold"),
            text_color="#EDEAF5"
        ).pack(anchor="w", padx=16, pady=(12, 4))

        ctk.CTkLabel(
            info_card, 
            text="💡 系统会将所选分类收藏夹内的全部视频完整合并/复制回【默认收藏夹】（确保收藏永不丢失），合并完毕后自动从 B 站删除对应分类文件夹，恢复整洁状态。",
            font=ctk.CTkFont(family="Microsoft YaHei", size=11),
            text_color="#A9A5B6", wraplength=570, justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 8))

        target_banner = ctk.CTkFrame(info_card, corner_radius=8, fg_color=CARD_INNER)
        target_banner.pack(fill="x", padx=14, pady=(0, 12))

        ctk.CTkLabel(
            target_banner,
            text=f"🎯 放回目标：【{default_folder['title']}】(当前已有 {default_folder['media_count']} 个视频)",
            font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold"),
            text_color=THEME_BLUE
        ).pack(anchor="w", padx=12, pady=8)

        # 中部待删除文件夹勾选列表
        list_container = ctk.CTkFrame(win, corner_radius=14, fg_color=CARD_DARK, border_width=1, border_color="#363242")
        list_container.pack(fill="both", expand=True, padx=18, pady=6)

        header_bar = ctk.CTkFrame(list_container, fg_color="transparent")
        header_bar.pack(fill="x", padx=14, pady=(10, 6))

        ctk.CTkLabel(
            header_bar,
            text=f"待清理的分类收藏夹列表 ({len(custom_folders)}个)：",
            font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold"),
            text_color="#EDEAF5"
        ).pack(side="left")

        checkbox_vars = {}

        def get_selected_ids():
            return [fid for fid, var in checkbox_vars.items() if var.get()]

        def select_all():
            for var in checkbox_vars.values():
                var.set(True)
            update_confirm_btn_text()

        def deselect_all():
            for var in checkbox_vars.values():
                var.set(False)
            update_confirm_btn_text()

        btn_deselect = ctk.CTkButton(
            header_bar, text="全部取消", width=68, height=24,
            font=ctk.CTkFont(size=11), fg_color="#363242", hover_color="#454054",
            command=deselect_all
        )
        btn_deselect.pack(side="right", padx=(4, 0))

        btn_select_all = ctk.CTkButton(
            header_bar, text="全部勾选", width=68, height=24,
            font=ctk.CTkFont(size=11), fg_color="#363242", hover_color="#454054",
            command=select_all
        )
        btn_select_all.pack(side="right")

        scroll_list = ctk.CTkScrollableFrame(list_container, fg_color=CARD_INNER, corner_radius=10)
        scroll_list.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        for f in custom_folders:
            fid = f["id"]
            title = f["title"]
            count = f["media_count"]
            is_created = fid in created_ids

            row = ctk.CTkFrame(scroll_list, fg_color="transparent")
            row.pack(fill="x", pady=3)

            var = tk.BooleanVar(value=True)
            checkbox_vars[fid] = var

            cb = ctk.CTkCheckBox(
                row, text=f"📂 {title}", variable=var,
                font=ctk.CTkFont(family="Microsoft YaHei", size=12),
                fg_color=THEME_PINK, hover_color=THEME_PINK_HOVER,
                command=lambda: update_confirm_btn_text()
            )
            cb.pack(side="left", padx=(6, 4))

            tag_text = f"({count} 个视频)"
            if is_created:
                tag_text += "  ✨[由 BiliSort 创建]"

            ctk.CTkLabel(
                row, text=tag_text,
                font=ctk.CTkFont(family="Microsoft YaHei", size=11),
                text_color=THEME_BLUE if is_created else "#9B97A8"
            ).pack(side="left", padx=4)

        # 进度与状态区
        status_bar = ctk.CTkFrame(win, fg_color="transparent")
        status_bar.pack(fill="x", padx=18, pady=(4, 2))

        progress = ctk.CTkProgressBar(status_bar, corner_radius=4, height=6, progress_color=THEME_PINK, fg_color=CARD_INNER)
        progress.pack(fill="x", pady=(0, 4))
        progress.set(0)

        modal_status_lbl = ctk.CTkLabel(
            status_bar, text="请勾选需要合并并删除的收藏夹，点击下方按钮开始",
            font=ctk.CTkFont(family="Microsoft YaHei", size=11),
            text_color="#B3B0BE"
        )
        modal_status_lbl.pack(anchor="w")

        # 底部操作栏
        bottom_bar = ctk.CTkFrame(win, fg_color="transparent")
        bottom_bar.pack(fill="x", padx=18, pady=(6, 16))

        cancel_btn = ctk.CTkButton(
            bottom_bar, text="取消", width=90, height=36,
            fg_color="#363242", hover_color="#454054",
            corner_radius=10, command=win.destroy
        )
        cancel_btn.pack(side="left")

        confirm_btn = ctk.CTkButton(
            bottom_bar, 
            text=f"🔥 确认放回默认并删除所选 ({len(custom_folders)}个)",
            width=260, height=36,
            fg_color="#EF4444", hover_color="#DC2626", text_color="#FFFFFF",
            font=ctk.CTkFont(family="Microsoft YaHei", size=13, weight="bold"),
            corner_radius=10
        )
        confirm_btn.pack(side="right")

        def update_confirm_btn_text():
            s = get_selected_ids()
            confirm_btn.configure(text=f"🔥 确认放回默认并删除所选 ({len(s)}个)")

        def run_restore():
            selected = get_selected_ids()
            if not selected:
                messagebox.showwarning("提示", "请至少勾选一个需要处理的收藏夹！")
                return

            if not messagebox.askyesno(
                "安全二次确认",
                f"操作即将开始：\n\n1. 将选中的 {len(selected)} 个收藏夹内的所有视频完整合并/复制回【{default_folder['title']}】\n2. 从 B 站彻底删除这 {len(selected)} 个分类收藏夹\n\n（视频已在默认收藏夹保留，绝不丢失）\n\n是否立即开始？"
            ):
                return

            confirm_btn.configure(state="disabled")
            cancel_btn.configure(state="disabled")
            btn_select_all.configure(state="disabled")
            btn_deselect.configure(state="disabled")

            def do_work():
                try:
                    def log_cb(msg):
                        self.log(msg)
                        try:
                            win.after(0, lambda: modal_status_lbl.configure(text=msg))
                        except Exception:
                            pass

                    def prog_cb(pct):
                        try:
                            win.after(0, lambda: progress.set(pct))
                        except Exception:
                            pass

                    res = self.folder_manager.restore_and_delete_folders(
                        folder_ids=selected,
                        target_media_id=default_folder["id"],
                        log_callback=log_cb,
                        progress_callback=prog_cb
                    )

                    self.log(f"🎉 还原清理完成！共合并 {res['restored_videos']} 个视频回【{default_folder['title']}】，删除了 {res['deleted_folders']} 个分类收藏夹。")
                    self._reload_folders()

                    def show_done():
                        messagebox.showinfo(
                            "还原完成", 
                            f"🎉 恭喜！已成功将 {res['restored_videos']} 个视频安全放回【{default_folder['title']}】！\n\n已成功删除 {res['deleted_folders']} 个分类收藏夹，您的 B 站收藏夹已恢复清爽！"
                        )
                        win.destroy()

                    win.after(0, show_done)

                except Exception as e:
                    self.log(f"还原清理出错: {e}")
                    try:
                        win.after(0, lambda: modal_status_lbl.configure(text=f"出错: {e}", text_color="#EF4444"))
                        win.after(0, lambda: messagebox.showerror("错误", f"还原过程中发生异常: {e}"))
                        win.after(0, lambda: confirm_btn.configure(state="normal"))
                        win.after(0, lambda: cancel_btn.configure(state="normal"))
                    except Exception:
                        pass

            threading.Thread(target=do_work, daemon=True).start()

        confirm_btn.configure(command=run_restore)

    # ================= 核心分析与同步 =================
    def start_analyze(self):
        if not self.user_sync.mid:
            messagebox.showwarning("提示", "请先点击左侧【手机扫码登录 B 站】哦！")
            return

        if not self.folders_cache:
            messagebox.showwarning("提示", "未找到收藏夹，请重新登录")
            return

        user_inst = self.pref_entry.get().strip()
        cfg = ConfigManager.load_config()
        if cfg.get("user_instruction") != user_inst:
            cfg["user_instruction"] = user_inst
            ConfigManager.save_config(cfg)
            self.classifier.reload_config()

        is_all = self.all_vids_var.get()
        limit = 999999 if is_all else int(self.count_slider.get())
        selected_idx = self.folder_combo.cget("values").index(self.folder_combo.get())
        src_folder = self.folders_cache[selected_idx]

        self.analyze_btn.configure(state="disabled")
        self.sync_btn.configure(state="disabled")
        mode_text = f"🤖 DeepSeek 统筹归类中 ({self.classifier.model})..." if self.classifier.has_llm() else "⚡ 本地多维加权分析中..."
        self.status_tip.configure(text=mode_text, text_color=THEME_BLUE)
        self.progress_bar.set(0.1)

        for widget in self.result_scroll.winfo_children():
            widget.destroy()

        def run_thread():
            try:
                fetch_desc = "全部视频 (全量扫描)" if is_all else f"最近 {limit} 个待整理视频"
                self.log(f"开始拉取【{src_folder['title']}】{fetch_desc}...")
                videos_raw = []
                page = 1
                page_size = 20
                while True:
                    if not is_all and len(videos_raw) >= limit:
                        break
                    cur_ps = page_size if is_all else min(page_size, limit - len(videos_raw))
                    url = f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={src_folder['id']}&pn={page}&ps={cur_ps}"
                    resp = self.user_sync.session.get(url, timeout=12).json()
                    if resp.get("code") != 0:
                        self.log(f"⚠️ 拉取第 {page} 页提示: {resp.get('message')}")
                        break
                    data = resp.get("data") or {}
                    medias = data.get("medias") or []
                    if not medias:
                        break

                    has_more = data.get("has_more", False)
                    for m in medias:
                        # 过滤掉下架或失效的无效条目
                        if not m.get("id") or m.get("title") == "已失效视频":
                            continue
                        videos_raw.append({
                            "aid": m.get("id"),
                            "bvid": m.get("bvid"),
                            "title": m.get("title"),
                            "intro": m.get("intro", ""),
                            "owner": m.get("upper", {}).get("name", "")
                        })
                        if not is_all and len(videos_raw) >= limit:
                            break

                    if page % 5 == 0 or not has_more:
                        self.log(f"已扫描 {len(videos_raw)} 个有效视频 (已读取至第 {page} 页)...")

                    if not has_more:
                        break
                    page += 1
                    time.sleep(0.08)

                self.current_videos_raw = videos_raw
                total = len(videos_raw)
                if total == 0:
                    self.log("⚠️ 未获取到任何有效视频，请检查收藏夹或网络！")
                    self.status_tip.configure(text="⚠️ 收藏夹为空或无有效视频", text_color="#EF4444")
                    return

                self.log(f"成功获取 {total} 个视频元数据！正在提取特征与标签...")
                self.progress_bar.set(0.4)

                # 优化标签提取：若视频数量很多，进行并发提速并控制最大请求数，避免被B站风控
                if total <= 60:
                    for idx, v in enumerate(videos_raw, 1):
                        v["tags"] = self.folder_manager.get_video_tags(v["aid"])
                        time.sleep(0.02)
                else:
                    from concurrent.futures import ThreadPoolExecutor
                    self.log(f"视频量较大 ({total}条)，启动并发特征加速提取...")
                    # 优先为前 120 个视频并发提取详细标签，其余通过标题+简介+UP主多维特征分析
                    sample_vids = videos_raw[:120]
                    def fetch_tag(vid_item):
                        try:
                            vid_item["tags"] = self.folder_manager.get_video_tags(vid_item["aid"])
                        except Exception:
                            vid_item["tags"] = []
                    with ThreadPoolExecutor(max_workers=5) as executor:
                        list(executor.map(fetch_tag, sample_vids))
                    for v in videos_raw[120:]:
                        v["tags"] = []

                self.progress_bar.set(0.6)
                if self.classifier.has_llm():
                    topics_names = [t["name"] for t in self.classifier.selected_topics]
                    self.log(f"目标文件夹已载入 ({len(topics_names)}个): {', '.join(topics_names[:4])}...")
                    if user_inst:
                        self.log(f"用户偏好说明已载入: \"{user_inst}\"")
                
                # 统一执行智能归类
                self.categorized_results = self.classifier.classify_all(
                    videos_raw, 
                    log_callback=self.log
                )
                self.progress_bar.set(1.0)
                self.after(0, self._render_results)

            except Exception as e:
                self.log(f"分析异常: {e}")
                self.status_tip.configure(text=f"出错: {e}", text_color="#EF4444")
            finally:
                self.analyze_btn.configure(state="normal")

        threading.Thread(target=run_thread, daemon=True).start()

    def _render_results(self):
        total_vids = len(self.current_videos_raw)
        total_cats = len(self.categorized_results)
        self.result_scroll.configure(
            label_text=f"📊 分类看板：共 {total_vids} 个视频，已精准归入 {total_cats} 个文件夹"
        )
        self.status_tip.configure(text="✅ 分析完成！预览满意后点击【一键归类到 B 站】", text_color="#10B981")
        self.sync_btn.configure(state="normal")

        for cat, vids in self.categorized_results.items():
            card = ctk.CTkFrame(self.result_scroll, corner_radius=14, fg_color=CARD_DARK, border_width=1, border_color="#363242")
            card.pack(fill="x", padx=6, pady=8)

            header = ctk.CTkFrame(card, fg_color="transparent")
            header.pack(fill="x", padx=14, pady=(10, 6))

            cat_title = ctk.CTkLabel(
                header, text=f"📂 {cat}", 
                font=ctk.CTkFont(family="Microsoft YaHei", size=15, weight="bold"),
                text_color=THEME_BLUE
            )
            cat_title.pack(side="left")

            count_badge = ctk.CTkLabel(
                header, text=f"{len(vids)} 个视频", 
                font=ctk.CTkFont(family="Microsoft YaHei", size=12),
                text_color=THEME_YELLOW
            )
            count_badge.pack(side="right")

            list_box = ctk.CTkFrame(card, fg_color=CARD_INNER, corner_radius=10)
            list_box.pack(fill="x", padx=12, pady=(0, 10))

            for i, vid in enumerate(vids, 1):
                tags_str = ", ".join(vid.get("tags", [])[:3])
                tags_badge = f"  🏷️ {tags_str}" if tags_str else ""
                row_str = f"{i}. {vid['title']} (UP主: {vid['owner']}){tags_badge}"
                
                v_lbl = ctk.CTkLabel(
                    list_box, text=row_str, anchor="w", 
                    font=ctk.CTkFont(family="Microsoft YaHei", size=12),
                    text_color="#E0DDEB"
                )
                v_lbl.pack(fill="x", padx=10, pady=3)

    def start_sync(self):
        if not self.categorized_results:
            return

        if not messagebox.askyesno(
            "确认同步", 
            f"系统即将在您的 B 站账号中新建对应的 {len(self.categorized_results)} 个分类收藏夹，并将 {len(self.current_videos_raw)} 个视频归入其中。\n\n是否立即开始？"
        ):
            return

        self.sync_btn.configure(state="disabled")
        self.analyze_btn.configure(state="disabled")
        self.status_tip.configure(text="🚀 正在向 B 站同步创建文件夹并复制视频...", text_color=THEME_YELLOW)
        self.progress_bar.set(0)

        def run_sync_thread():
            try:
                selected_idx = self.folder_combo.cget("values").index(self.folder_combo.get())
                src_folder = self.folders_cache[selected_idx]
                all_folders = {f["title"]: f["id"] for f in self.user_sync.get_favorite_folders()}

                total_cats = len(self.categorized_results)
                for cur_idx, (cat, vids) in enumerate(self.categorized_results.items(), 1):
                    tar_id = all_folders.get(cat)
                    if not tar_id:
                        self.log(f"正在创建新收藏夹: 【{cat}】...")
                        tar_id = self.folder_manager.create_folder(title=cat, intro="BiliSort智能整理", privacy=1)
                        if tar_id:
                            all_folders[cat] = tar_id

                    if not tar_id:
                        self.log(f"[跳过] 无法获取【{cat}】ID")
                        continue

                    aids = [v["aid"] for v in vids if v.get("aid")]
                    self.log(f"正在将 {len(aids)} 个视频批量复制至【{cat}】...")
                    ok = self.folder_manager.batch_copy_to_folder(
                        src_media_id=src_folder["id"],
                        tar_media_id=tar_id,
                        aids=aids
                    )
                    if ok:
                        self.log(f"✅ 成功将 {len(aids)} 个视频批量归入【{cat}】！")
                    else:
                        self.log(f"⚠️ 分类【{cat}】部分视频复制失败或已在其中")

                    self.progress_bar.set(cur_idx / total_cats)
                    time.sleep(0.5)

                self.log("🎉 全部同步成功！手机 B 站 APP 我的收藏中已更新！")
                self.after(0, lambda: messagebox.showinfo(
                    "同步成功", 
                    "🎉 恭喜！全部视频已成功分类并同步至您的 B 站账号！\n\n您可以打开手机哔哩哔哩 APP【我的】->【我的收藏】刷新查看！"
                ))
                self.status_tip.configure(text="🎉 全部归类同步完成！", text_color="#10B981")

            except Exception as e:
                self.log(f"同步异常: {e}")
                self.status_tip.configure(text=f"同步出错: {e}", text_color="#EF4444")
            finally:
                self.sync_btn.configure(state="normal")
                self.analyze_btn.configure(state="normal")

        threading.Thread(target=run_sync_thread, daemon=True).start()

if __name__ == "__main__":
    app = CuteBiliSortApp()
    app.mainloop()
