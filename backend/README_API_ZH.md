# OpenShortVideo API 文档

本文档描述了 OpenShortVideo 后端的 REST API，该 API 允许您使用 AI 从文本创意生成视频。

## 概述

API 提供两种操作模式：

1. **一键生成模式**：自动运行整个流水线。
2. **步骤化模式**：单独控制生成过程的每个步骤。

## 基础 URL

所有 API 端点都以 `/api/v1` 为前缀。默认服务器运行在 `http://localhost:5001`。

## 交互式文档

您可以通过以下地址访问交互式 Swagger UI：
- `http://localhost:5001/api/v1/docs`

OpenAPI 规范可在以下地址获取：
- `http://localhost:5001/api/v1/swagger.json`

## 认证

当前无需认证。所有端点均可公开访问。

## 任务管理

### 创建任务

```http
POST /api/v1/tasks
Content-Type: application/json

{
  "idea": "一只猫和一只狗在花园里玩耍。",
  "user_requirement": "面向全年龄段，场景不超过1个。",
  "style": "卡通风格",
  "mode": "stepwise",
  "work_dir": "可选/自定义/路径"
}
```

**参数：**

- `idea` (必需)：故事创意或概念文本。
- `user_requirement` (可选)：视频生成的具体要求。
- `style` (可选)：艺术风格描述。
- `mode` (可选)：`"full"` 或 `"stepwise"`。默认为 `"full"`。
- `work_dir` (可选)：自定义工作目录路径。如果未提供，将在 `working_dir_idea2video/` 下创建基于 UUID 的目录。

**响应：**

```json
{
  "task_id": "uuid-string",
  "work_dir": "path/to/work/dir",
  "mode": "stepwise",
  "status": "pending",
  "created_at": "2025-02-08T14:43:56.991251"
}
```

### 获取任务状态

```http
GET /api/v1/tasks/{task_id}
```

返回任务的当前状态、进度和元数据。

### 执行步骤（仅步骤化模式）

```http
POST /api/v1/tasks/{task_id}/steps/{step_name}
```

执行生成流水线中的特定步骤。可用步骤：

1. `develop_story` - 从创意生成故事
2. `extract_characters` - 从故事中提取角色
3. `generate_character_portraits` - 生成角色肖像
4. `write_script` - 基于故事编写剧本
5. `design_storyboard` - 设计分镜
6. `decompose_visual_descriptions` - 分解视觉描述
7. `construct_camera_tree` - 构建相机树
8. `generate_frames` - 生成帧
9. `generate_videos` - 从剧本生成视频（需要步骤 1-4）
10. `concatenate_videos` - 拼接视频

**注意：** 所有步骤现已实现，但某些步骤可能存在依赖关系，请按顺序执行。

### 列出生成文件

```http
GET /api/v1/tasks/{task_id}/artifacts
```

列出任务的所有生成文件。

### 获取文件内容

```http
GET /api/v1/tasks/{task_id}/artifacts/{file_path}
```

检索特定文件的元数据或内容。添加 `?content=true` 以获取文本文件的内容。

### 取消任务

```http
POST /api/v1/tasks/{task_id}/cancel
```

取消待处理或正在运行的任务。

## 生成流水线步骤

视频生成流水线包含以下步骤：

### 1. 故事开发 (`develop_story`)
- **输入**：创意、用户要求
- **输出**：故事文本 (`story.txt`)
- **描述**：从输入创意生成连贯的故事。

### 2. 角色提取 (`extract_characters`)
- **输入**：故事文本
- **输出**：角色列表 (`characters.json`)
- **描述**：从故事中提取角色及其描述。

### 3. 角色肖像生成 (`generate_character_portraits`)
- **输入**：角色、风格
- **输出**：角色肖像 (`character_portraits_registry.json`, PNG 图像)
- **描述**：生成每个角色的正面、侧面和背面视图。

### 4. 剧本编写 (`write_script`)
- **输入**：故事、用户要求
- **输出**：剧本 (`script.json`)
- **描述**：创建包含场景和镜头的详细剧本。

### 5. 分镜设计 (`design_storyboard`)
- **输入**：剧本、角色、用户要求
- **输出**：分镜 (`storyboard.json`)
- **描述**：设计视频的分镜，确定每个镜头的构图和内容。

### 6. 视觉描述分解 (`decompose_visual_descriptions`)
- **输入**：分镜、角色
- **输出**：镜头描述 (`shot_description.json`)
- **描述**：将分镜分解为详细的视觉描述，包括帧描述、运动描述等。

### 7. 相机树构建 (`construct_camera_tree`)
- **输入**：镜头描述
- **输出**：相机树 (`camera_tree.json`)
- **描述**：构建相机运动树，确定镜头之间的过渡关系。

### 8. 帧生成 (`generate_frames`)
- **输入**：相机树、镜头描述、角色、角色肖像
- **输出**：帧图像 (`first_frame.png`, `last_frame.png`)
- **描述**：生成每个镜头的关键帧图像。

### 9. 视频生成 (`generate_videos`)
- **输入**：镜头描述、帧图像
- **输出**：单个镜头视频 (`video.mp4`)
- **描述**：为每个镜头生成视频片段。

### 10. 视频拼接 (`concatenate_videos`)
- **输入**：单个镜头视频
- **输出**：最终视频 (`final_video.mp4`)
- **描述**：将所有镜头视频拼接成完整的最终视频。

## 示例工作流

### 一键生成

```bash
curl -X POST http://localhost:5001/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "idea": "一只猫和一只狗在花园里玩耍。",
    "user_requirement": "面向全年龄段，场景不超过1个。",
    "style": "卡通风格",
    "mode": "full"
  }'
```

### 步骤化生成

```bash
# 1. 创建任务
curl -X POST http://localhost:5001/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "idea": "一只猫和一只狗在花园里玩耍。",
    "user_requirement": "面向全年龄段，场景不超过1个。",
    "style": "卡通风格",
    "mode": "stepwise"
  }'

# 2. 顺序执行步骤
TASK_ID="您的任务ID"
curl -X POST http://localhost:5001/api/v1/tasks/$TASK_ID/steps/develop_story
curl -X POST http://localhost:5001/api/v1/tasks/$TASK_ID/steps/extract_characters
curl -X POST http://localhost:5001/api/v1/tasks/$TASK_ID/steps/generate_character_portraits
curl -X POST http://localhost:5001/api/v1/tasks/$TASK_ID/steps/write_script
curl -X POST http://localhost:5001/api/v1/tasks/$TASK_ID/steps/design_storyboard
curl -X POST http://localhost:5001/api/v1/tasks/$TASK_ID/steps/decompose_visual_descriptions
curl -X POST http://localhost:5001/api/v1/tasks/$TASK_ID/steps/construct_camera_tree
curl -X POST http://localhost:5001/api/v1/tasks/$TASK_ID/steps/generate_frames
curl -X POST http://localhost:5001/api/v1/tasks/$TASK_ID/steps/generate_videos
curl -X POST http://localhost:5001/api/v1/tasks/$TASK_ID/steps/concatenate_videos

# 3. 监控进度
curl http://localhost:5001/api/v1/tasks/$TASK_ID

# 4. 下载最终视频
curl http://localhost:5001/api/v1/tasks/$TASK_ID/artifacts/final_video.mp4?content=true \
  --output final_video.mp4

# 5. 列出所有生成文件
curl http://localhost:5001/api/v1/tasks/$TASK_ID/artifacts

# 6. 下载其他生成文件（例如故事文件）
curl http://localhost:5001/api/v1/tasks/$TASK_ID/artifacts/story.txt?content=true \
  --output story.txt

# 7. 取消运行中的任务
curl -X POST http://localhost:5001/api/v1/tasks/$TASK_ID/cancel

# 8. 任务完成后获取生成文件列表
curl http://localhost:5001/api/v1/tasks/$TASK_ID/artifacts
```

### 完整 API 使用示例

以下是一个完整的示例，展示所有 API 端点的实际使用：

```bash
#!/bin/bash

# 设置基础 URL
BASE_URL="http://localhost:5001/api/v1"

# 1. 在步骤化模式下创建任务
echo "创建新的视频生成任务..."
RESPONSE=$(curl -s -X POST "$BASE_URL/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "idea": "一只猫和一只狗在花园里玩耍。",
    "user_requirement": "面向全年龄段，场景不超过1个。",
    "style": "卡通风格",
    "mode": "stepwise",
    "work_dir": "my_custom_directory"
  }')

# 从响应中提取任务 ID
TASK_ID=$(echo "$RESPONSE" | grep -o '"task_id":"[^"]*"' | cut -d'"' -f4)
echo "任务已创建，ID: $TASK_ID"

# 2. 获取初始任务状态
echo "检查任务状态..."
curl -s "$BASE_URL/tasks/$TASK_ID" | python -m json.tool

# 3. 逐个执行步骤（包含错误检查）
echo "开始步骤化生成..."

# 按顺序定义步骤
STEPS=(
  "develop_story"
  "extract_characters"
  "generate_character_portraits"
  "write_script"
  "design_storyboard"
  "decompose_visual_descriptions"
  "construct_camera_tree"
  "generate_frames"
  "generate_videos"
  "concatenate_videos"
)

for STEP in "${STEPS[@]}"; do
  echo "执行步骤: $STEP"
  curl -X POST "$BASE_URL/tasks/$TASK_ID/steps/$STEP"
  
  # 等待步骤完成（简化的轮询）
  sleep 5
  
  # 检查任务状态
  STATUS=$(curl -s "$BASE_URL/tasks/$TASK_ID" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
  echo "当前状态: $STATUS"
  
  if [ "$STATUS" = "failed" ]; then
    echo "步骤 $STEP 失败。请检查日志获取详细信息。"
    break
  fi
done

# 4. 监控最终状态
echo "等待完成..."
while true; do
  STATUS=$(curl -s "$BASE_URL/tasks/$TASK_ID" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
  PROGRESS=$(curl -s "$BASE_URL/tasks/$TASK_ID" | grep -o '"progress":[0-9.]*' | cut -d':' -f2)
  
  printf "状态: %s, 进度: %s%%\\r" "$STATUS" "${PROGRESS:-0}"
  
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] || [ "$STATUS" = "cancelled" ]; then
    echo ""
    echo "任务完成，状态: $STATUS"
    break
  fi
  
  sleep 2
done

# 5. 列出所有生成的文件
if [ "$STATUS" = "completed" ]; then
  echo "生成的文件:"
  curl -s "$BASE_URL/tasks/$TASK_ID/artifacts" | python -m json.tool
  
  # 6. 下载最终视频
  echo "下载最终视频..."
  curl -s "$BASE_URL/tasks/$TASK_ID/artifacts/final_video.mp4?content=true" \
    --output final_video.mp4
  echo "视频已下载到: final_video.mp4"
  
  # 7. 下载其他重要文件
  echo "下载其他文件..."
  curl -s "$BASE_URL/tasks/$TASK_ID/artifacts/story.txt?content=true" --output story.txt
  curl -s "$BASE_URL/tasks/$TASK_ID/artifacts/script.json?content=true" --output script.json
  curl -s "$BASE_URL/tasks/$TASK_ID/artifacts/storyboard.json?content=true" --output storyboard.json
fi

# 8. 清理：如果需要，取消任务（示例）
if [ "$STATUS" = "running" ]; then
  echo "取消任务..."
  curl -X POST "$BASE_URL/tasks/$TASK_ID/cancel"
fi
```

此示例演示了：
- 使用自定义参数创建任务
- 从响应中提取任务 ID
- 按顺序执行步骤并检查错误
- 实时进度监控
- 下载生成的文件
- 任务取消

## 遗留 API

原始 API 端点仍然可用：

- `POST /api/generate` - 开始生成（一键式）
- `GET /api/logs` - 通过 Server-Sent Events (SSE) 流式传输日志
- `GET /api/task_status` - 获取当前任务状态
- `GET /api/files` - 列出生成的文件
- `GET /api/work_dirs` - 列出所有工作目录

## 配置

API 使用配置文件 `configs/idea2video_deepseek_veo3.yaml`。确保此文件存在并包含所需服务的有效 API 密钥。

## 错误处理

API 返回标准 HTTP 状态码：

- `200` OK：请求成功
- `201` Created：资源创建成功
- `202` Accepted：步骤执行已开始
- `400` Bad Request：无效输入
- `404` Not Found：资源未找到
- `409` Conflict：无效操作（例如，在完整模式下执行步骤）
- `500` Internal Server Error：服务器错误

错误响应包含一个带有 `error` 字段的 JSON 对象，描述问题。

## 限制

- API 目前对于步骤执行是同步的（每个步骤在后台运行）。
- 某些步骤可能仍在完善中。
- 大型视频生成任务可能需要几分钟才能完成。
- 未实现速率限制。

## Web 界面

应用程序包含一个现代化的 Web 界面，全面支持 API v1 功能。

### 访问界面

在 Web 浏览器中导航到 `http://localhost:5001/` 以访问主界面。

### 主要功能

1. **双生成模式**：
   - **一键生成模式**：全自动流水线执行
   - **步骤化生成模式**：手动控制生成过程的每个步骤

2. **步骤控制面板**：
   - 所有 10 个生成步骤的可视化表示
   - 实时状态更新（待执行、运行中、已完成、错误）
   - 单个步骤执行按钮
   - 进度跟踪和可视化

3. **任务管理**：
   - 使用自定义参数创建新任务
   - 暂停、继续和取消运行中的任务
   - 实时监控任务进度
   - 查看生成的文件和成果

4. **项目浏览器**：
   - 浏览历史项目和工作目录
   - 生成内容的文件树资源管理器
   - 视频预览和播放

### 使用步骤化模式

1. **选择步骤化模式**：在"高级设置"部分的生成模式下拉菜单中选择"步骤化模式"。
2. **输入您的创意**：提供您的创意想法、要求和风格偏好。
3. **创建任务**：点击"开始步骤化生成"创建步骤化任务。
4. **控制步骤**：导航到"步骤控制"标签页查看所有可用步骤。
5. **执行步骤**：按顺序点击单个步骤按钮执行它们。
6. **监控进度**：查看实时状态更新和进度指示器。

### 用户界面元素

- **生成模式选择器**：下拉菜单可在"一键生成模式"和"步骤化模式"之间选择
- **步骤控制标签页**：包含步骤卡片和控制按钮的专用标签页
- **实时日志**：在"生成日志"标签页中实时流式传输日志
- **视频预览**：在右侧边栏中播放生成的视频
- **项目统计**：文件数量、大小和生成指标

Web 界面提供了一种用户友好的方式来与 API v1 端点交互，同时保持与程序化访问的完全兼容性。

## 故障排除

1. **任务无进展**：检查服务器日志中的错误。
2. **缺少生成文件**：确保之前的步骤已成功完成。
3. **API 密钥过期**：使用有效的 API 密钥更新配置文件。
4. **磁盘空间不足**：清理旧的工作目录。

## 支持

如有问题和功能请求，请在项目仓库中提交问题。