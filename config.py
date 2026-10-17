import os
import json
from typing import Dict, Any, List

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_config.json")

# 海量精选常见文件夹主题库 (提供给用户随时点选添加)
SUGGESTED_TOPICS_POOL = [
    # 科技与开发
    {"name": "AI与大模型实战", "keywords": "ai, 人工智能, 大模型, n8n, agent, 智能体, deepseek, prompt, 算力, 自动化, 机器学习"},
    {"name": "编程开发与架构", "keywords": "编程, 全栈, 前端, 后端, python, java, 算法, github, 代码, 架构, 高并发, 数据库"},
    {"name": "硬件开发与单片机", "keywords": "stm32, 单片机, 物联网, 硬件, 嵌入式, 树莓派, 毕设, 电路, 机械, 电子制作"},
    {"name": "生产力与知识管理", "keywords": "obsidian, 笔记, 知识管理, 效率工具, 同步, 工作流, 插件, 备忘, 任务管理, 自动化"},
    {"name": "数码产品与科技杂谈", "keywords": "数码, 手机, 电脑, 评测, 科技, 硬件, 外设, 体验, 行业动态"},

    # 学习与认知
    {"name": "考研考公与专业课", "keywords": "考研, 考公, 申论, 行测, 期末, 课程, 政治, 英语, 刷题, 提分, 笔记, 院校"},
    {"name": "深度读书与思维认知", "keywords": "读书, 乔布斯, 传记, 认知, 博弈论, 哲学, 社会学, 心理学, 书籍拆解, 个人成长"},
    {"name": "英语学习与语言技能", "keywords": "英语, 听力, 口语, 词汇, 语法, 托福, 雅思, 翻译, 外语, 表达"},
    {"name": "硬核科学与科普", "keywords": "科普, 物理, 数学, 天文, 宇宙, 历史, 信息论, 地理, 自然, 原理"},

    # 商业与职场
    {"name": "商业模式与创业搞钱", "keywords": "商业, 搞钱, 副业, 创业, 赚钱, 商业模式, 变现, 运营, 营销, 案例拆解"},
    {"name": "宏观经济与政策观察", "keywords": "宏观经济, 经济学, 政策, 化债, 地方债, 货币, 金融, 产业, 大国大城, 市场"},
    {"name": "个人理财与资产配置", "keywords": "理财, 投资, 资产配置, 基金, 股票, 房产, 存款, 利率, 风险控制, 交易"},
    {"name": "职场沟通与组织管理", "keywords": "沟通, 谈判, 组织, 管理, 领导力, 职场认知, 团队协作, 晋升, 求职面试"},

    # 创意与视听
    {"name": "视频剪辑与后期视效", "keywords": "视频剪辑, pr, ae, 调色, 运镜, 转场, 蒙版, 特效, 帧率, 导出, 剪映"},
    {"name": "平面设计与排版审美", "keywords": "设计, ui, 排版, 字体, 构图, ps, 审美, 配色, 视觉语言, 品牌, 海报"},
    {"name": "影视解析与视听语言", "keywords": "影视解析, 视听语言, 拉片, 导演风格, 剧作, 电影镜头, 叙事, 影评"},
    {"name": "摄影摄像与布光构图", "keywords": "摄影, 构图, 相机, 镜头, 布光, 人像, 街拍, 风光, 参数"},

    # 运动与生活
    {"name": "健身增肌与力量训练", "keywords": "力量训练, 卧推, 深蹲, 硬拉, 动作规范, 增肌, 渐进负荷, 肌肉, 健身房"},
    {"name": "减脂有氧与体态康复", "keywords": "减脂, 有氧, 跑步, 骑行, hiit, 心率, 拉伸, 骨盆前倾, 体态, 疼痛改善"},
    {"name": "营养膳食与健康生活", "keywords": "热量, 蛋白质, 碳水, 补剂, 饮食搭配, 睡眠, 昼夜节律, 健康科普, 养生"},
    {"name": "烹饪料理与探店美食", "keywords": "料理, 烹饪, 美食, 食谱, 探店, 烘焙, 咖啡, 厨房, 调味, 家常菜"},
    {"name": "音乐现场与吉他乐理", "keywords": "音乐, 现场, live, 乐理, 吉他, 和弦, 钢琴, 乐器, 翻唱, 编曲"},
    {"name": "游戏评测与电竞赛事", "keywords": "游戏, 评测, 电竞, 赛事, 攻略, 单机, 主机, steam, 体验, 通关"},
    {"name": "搞笑幽默与日常解压", "keywords": "搞笑, 整蛊, 幽默, 鬼畜, 治愈, 解压, vlog, 动漫, 趣味"}
]

# 默认初始选用的通用文件夹 (用户可随意增删)
DEFAULT_SELECTED_TOPICS = [
    {"name": "AI与大模型实战", "keywords": "ai, 人工智能, 大模型, n8n, 智能体, deepseek, 自动化"},
    {"name": "编程开发与架构", "keywords": "编程, 全栈, python, 代码, 算法, 架构, github"},
    {"name": "深度读书与思维认知", "keywords": "读书, 乔布斯, 传记, 认知, 博弈论, 哲学, 书籍"},
    {"name": "宏观经济与商业模式", "keywords": "宏观经济, 经济学, 商业, 化债, 投资, 搞钱, 创业"},
    {"name": "生活休闲与日常解压", "keywords": "搞笑, 电影, 音乐, 美食, 游戏, vlog, 治愈"}
]

DEFAULT_CONFIG = {
    "api_key": "",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-flash",
    "user_instruction": "",                 # 用户的个性化需求/自由指令
    "selected_topics": DEFAULT_SELECTED_TOPICS # 用户挑选的当前文件夹列表
}

class ConfigManager:
    @staticmethod
    def load_config() -> Dict[str, Any]:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    for k, v in DEFAULT_CONFIG.items():
                        if k not in cfg:
                            cfg[k] = v
                    return cfg
            except Exception:
                pass
        return DEFAULT_CONFIG.copy()

    @staticmethod
    def save_config(cfg: Dict[str, Any]):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
