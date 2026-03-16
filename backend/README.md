# ViMax: 智能多智能体视频生成框架

<p align="center">
  <img src="./assets/vimax.png" alt="ViMax Logo">
</p>

<p align="center">
  <a href="https://trendshift.io/repositories/15299" target="_blank"><img src="https://trendshift.io/api/badge/repositories/15299" alt="HKUDS%2FViMax | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/🐍Python-3.12-00d9ff?style=for-the-badge&logo=python&logoColor=white&labelColor=1a1a2e">
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/badge/⚡uv-Ready-ff6b6b?style=for-the-badge&logo=python&logoColor=white&labelColor=1a1a2e"></a>
  <img src="https://img.shields.io/badge/License-MIT-4ecdc4?style=for-the-badge&logo=opensourceinitiative&logoColor=white" alt="MIT License">
</p>

## 🚀 项目简介

ViMax 是一个创新的多智能体视频生成框架，能够将您的创意想法自动转化为完整的视频内容。它集成了**导演**、**编剧**、**制片人**和**视频生成器**的功能，实现从概念到成片的端到端自动化流程。

### 🔥 核心功能

| 功能模块 | 描述 |
|----------|------|
| **🌟 Idea2Video** | 从简单的创意想法生成完整视频故事，自动进行故事讲述、角色设计和制作 |
| **🎨 Novel2Video** | 将完整小说转换为分集视频内容，智能进行叙事压缩、角色跟踪和场景视觉适配 |
| **⚙️ Script2Video** | 基于特定剧本生成视频，支持从个人故事到史诗冒险的任何剧本创作 |
| **🤳 AutoCameo** | 从您的照片生成客串视频，将您或您的宠物变成无限创意剧本中的客串明星 |

## 📋 主要特性

- **🎬 全自动视频创作**: 只需输入创意，ViMax 自动处理脚本编写、故事板设计、角色创建和最终视频生成
- **🧠 多智能体协作**: 多个智能体协同工作，确保角色和场景的一致性
- **🎨 专业级质量**: 自动质量控制确保角色一致性、场景构图和专业的视觉标准
- **⚡ 高效并行处理**: 并行处理同一相机拍摄的连续镜头，实现高效视频制作
- **🔧 灵活的配置**: 支持多种AI模型和API配置，适应不同的创作需求

## 🚀 快速开始

### 环境要求
- Python ≥ 3.12
- 支持的操作系统: Linux, Windows

### 安装步骤

1. **克隆项目**
   ```bash
   git clone https://github.com/HKUDS/ViMax.git
   cd ViMax
   ```

2. **使用 uv 安装依赖**
   ```bash
   uv sync
   ```

   如果没有安装 uv，请参考 [uv 安装指南](https://docs.astral.sh/uv/getting-started/installation/)。

### 配置 API

在 `configs/` 目录下编辑相应的配置文件，设置您的 API 密钥：

1. **聊天模型** (如 DeepSeek、Gemini 等)
2. **图像生成器** (如 NanoBanana、Doubao 等)
3. **视频生成器** (如 Veo、Sora2 等)

示例配置 (`configs/idea2video.yaml`)：
```yaml
chat_model:
  init_args:
    model: google/gemini-2.5-flash-lite-preview-09-2025
    model_provider: openai
    api_key: <YOUR_API_KEY>
    base_url: https://openrouter.ai/api/v1

image_generator:
  class_path: tools.ImageGeneratorNanobananaGoogleAPI
  init_args:
    api_key: <YOUR_API_KEY>

video_generator:
  class_path: tools.VideoGeneratorVeoGoogleAPI
  init_args:
    api_key: <YOUR_API_KEY>

working_dir: .working_dir/idea2video
```

### 运行示例

1. **创意转视频** (Idea2Video)
   ```bash
   python main_idea2video.py
   ```

2. **剧本转视频** (Script2Video)
   ```bash
   python main_script2video.py
   ```

## 🎭 角色自定义功能

ViMax 支持完全自定义角色，您可以使用自己的角色替换项目中的默认角色。

### 角色自定义流程

1. **准备角色图像**
   - 为每个角色准备三个视角的图像：正面 (`front`)、侧面 (`side`)、背面 (`back`)
   - 图像格式建议：PNG 或 JPG
   - 图像尺寸建议：512x512 或更高分辨率

2. **上传图像并获取 URL**
   - 将角色图像上传到您的图床或存储服务
   - 获取每个图像的公开访问 URL

3. **编辑配置文件**
   - 打开 `insert_db.py` 文件
   - 在 `url_data` 字典中添加您的角色信息：
   ```python
   url_data = {
       "您的角色名称": {
           "front": {
               "path": "https://您的图床地址/正面图片.jpg",
               "description": "A front view portrait of 您的角色名称."
           },
           "side": {
               "path": "https://您的图床地址/侧面图片.jpg",
               "description": "A side view portrait of 您的角色名称."
           },
           "back": {
               "path": "https://您的图床地址/背面图片.jpg",
               "description": "A back view portrait of 您的角色名称."
           }
       }
   }
   ```

4. **生成角色注册文件**
   - 运行角色肖像生成器，或手动创建 `character_portraits_registry.json` 文件
   - 文件格式参考：
   ```json
   {
       "您的角色名称": {
           "front": {
               "path": "working_dir_idea2video/text_videov2/character_portraits/0_您的角色名称/front.png",
               "description": "A front view portrait of 您的角色名称."
           },
           "side": {
               "path": "working_dir_idea2video/text_videov2/character_portraits/0_您的角色名称/side.png",
               "description": "A side view portrait of 您的角色名称."
           },
           "back": {
               "path": "working_dir_idea2video/text_videov2/character_portraits/0_您的角色名称/back.png",
               "description": "A back view portrait of 您的角色名称."
           }
       }
   }
   ```

5. **插入角色到数据库**
   ```bash
   python insert_db.py
   ```
   该脚本会自动将角色信息插入到 `images.db` 数据库中。

6. **使用自定义角色**
   - 在您的创意或剧本中使用自定义的角色名称
   - ViMax 会自动使用您提供的角色图像生成视频

### 注意事项

- 确保角色图像 URL 可公开访问
- 角色名称在项目中保持唯一
- 如果更新了角色图像，需要重新运行 `insert_db.py`
- 数据库文件 `images.db` 会在首次运行时自动创建

## 🛠️ 项目结构

```
ViMax/
├── agents/              # 各种智能体（编剧、故事板艺术家等）
├── configs/             # 配置文件
├── interfaces/          # 接口定义
├── pipelines/           # 处理管道
├── tools/               # 工具类（API 调用等）
├── utils/               # 工具函数
├── main_idea2video.py   # 创意转视频主程序
├── main_script2video.py # 剧本转视频主程序
├── app.py               # Web UI
├── insert_db.py         # 角色数据库插入工具
└── database.py          # 数据库管理
```

## 📖 详细文档

- [English Documentation](readme.md)
- [中文文档](README_ZH.md)
- [交流群组](Communication.md)

## 🤝 贡献

欢迎提交 Issue 和 Pull Request 来帮助改进 ViMax！

## 📄 许可证

本项目基于 MIT 许可证开源 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

本项目基于 [HKUDS/ViMax](https://github.com/HKUDS/ViMax) 进行改进，采用了 DeepSeek、Qwen3-VL-32B-Instruct 和 Sora2 等模型对项目进行了扩展，并使用 Flask 框架搭建 Web UI。

---

**如果这个项目对您有帮助，请给我们一个 Star！⭐**

<p align="center">
  <em>感谢使用 ViMax，让创意无限可能！</em>
</p>
