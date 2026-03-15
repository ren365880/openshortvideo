# OpenShortVideo API Documentation

This document describes the REST API for the OpenShortVideo backend, which allows you to generate videos from textual ideas using AI.

## Overview

The API provides two modes of operation:

1. **Full Mode**: One-click generation that runs the entire pipeline automatically.
2. **Stepwise Mode**: Control each step of the generation process individually.

## Base URL

All API endpoints are prefixed with `/api/v1`. The default server runs at `http://localhost:5001`.

## Interactive Documentation

You can access the interactive Swagger UI at:
- `http://localhost:5001/api/v1/docs`

The OpenAPI specification is available at:
- `http://localhost:5001/api/v1/swagger.json`

## Authentication

Currently, no authentication is required. All endpoints are publicly accessible.

## Task Management

### Create a Task

```http
POST /api/v1/tasks
Content-Type: application/json

{
  "idea": "A cat and a dog playing in the garden.",
  "user_requirement": "For all ages, no more than 1 scene.",
  "style": "cartoon style",
  "mode": "stepwise",
  "work_dir": "optional/custom/path"
}
```

**Parameters:**

- `idea` (required): The story idea or concept text.
- `user_requirement` (optional): Specific requirements for the video generation.
- `style` (optional): Artistic style description.
- `mode` (optional): Either `"full"` or `"stepwise"`. Default is `"full"`.
- `work_dir` (optional): Custom working directory path. If not provided, a UUID-based directory will be created under `working_dir_idea2video/`.

**Response:**

```json
{
  "task_id": "uuid-string",
  "work_dir": "path/to/work/dir",
  "mode": "stepwise",
  "status": "pending",
  "created_at": "2025-02-08T14:43:56.991251"
}
```

### Get Task Status

```http
GET /api/v1/tasks/{task_id}
```

Returns the current status, progress, and metadata of a task.

### Execute a Step (Stepwise Mode Only)

```http
POST /api/v1/tasks/{task_id}/steps/{step_name}
```

Executes a specific step in the generation pipeline. Available steps:

1. `develop_story` - Develop story from idea
2. `extract_characters` - Extract characters from story
3. `generate_character_portraits` - Generate character portraits
4. `write_script` - Write script based on story
5. `design_storyboard` - Design storyboard
6. `decompose_visual_descriptions` - Decompose visual descriptions
7. `construct_camera_tree` - Construct camera tree
8. `generate_frames` - Generate frames
9. `generate_videos` - Generate individual shot videos
10. `concatenate_videos` - Concatenate videos into final video

**Note:** All steps are now implemented. Steps have dependencies, so execute them in order.

### List Artifacts

```http
GET /api/v1/tasks/{task_id}/artifacts
```

Lists all generated artifacts (files) for a task.

### Get Artifact Content

```http
GET /api/v1/tasks/{task_id}/artifacts/{file_path}
```

Retrieves metadata or content of a specific artifact. Add `?content=true` to get the file content for text files.

### Cancel a Task

```http
POST /api/v1/tasks/{task_id}/cancel
```

Cancels a pending or running task.

## Generation Pipeline Steps

The video generation pipeline consists of the following steps:

### 1. Story Development (`develop_story`)
- **Input**: Idea, user requirements
- **Output**: Story text (`story.txt`)
- **Description**: Generates a coherent story from the input idea.

### 2. Character Extraction (`extract_characters`)
- **Input**: Story text
- **Output**: Character list (`characters.json`)
- **Description**: Extracts characters from the story with their descriptions.

### 3. Character Portrait Generation (`generate_character_portraits`)
- **Input**: Characters, style
- **Output**: Character portraits (`character_portraits_registry.json`, PNG images)
- **Description**: Generates front, side, and back views of each character.

### 4. Script Writing (`write_script`)
- **Input**: Story, user requirements
- **Output**: Script (`script.json`)
- **Description**: Creates a detailed script with scenes and shots.

### 5. Storyboard Design (`design_storyboard`)
- **Input**: Script, characters, user requirements
- **Output**: Storyboard (`storyboard.json`)
- **Description**: Designs the video storyboard, determining composition and content for each shot.

### 6. Visual Description Decomposition (`decompose_visual_descriptions`)
- **Input**: Storyboard, characters
- **Output**: Shot descriptions (`shot_description.json`)
- **Description**: Decomposes storyboard into detailed visual descriptions including frame descriptions, motion descriptions, etc.

### 7. Camera Tree Construction (`construct_camera_tree`)
- **Input**: Shot descriptions
- **Output**: Camera tree (`camera_tree.json`)
- **Description**: Builds camera movement tree, determining transitions between shots.

### 8. Frame Generation (`generate_frames`)
- **Input**: Camera tree, shot descriptions, characters, character portraits
- **Output**: Frame images (`first_frame.png`, `last_frame.png`)
- **Description**: Generates keyframe images for each shot.

### 9. Video Generation (`generate_videos`)
- **Input**: Shot descriptions, frame images
- **Output**: Individual shot videos (`video.mp4`)
- **Description**: Generates video segments for each shot.

### 10. Video Concatenation (`concatenate_videos`)
- **Input**: Individual shot videos
- **Output**: Final video (`final_video.mp4`)
- **Description**: Concatenates all shot videos into the final complete video.

## Example Workflows

### One-Click Generation

```bash
curl -X POST http://localhost:5001/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "idea": "A cat and a dog playing in the garden.",
    "user_requirement": "For all ages, no more than 1 scene.",
    "style": "cartoon style",
    "mode": "full"
  }'
```

### Stepwise Generation

```bash
# 1. Create task
curl -X POST http://localhost:5001/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "idea": "A cat and a dog playing in the garden.",
    "user_requirement": "For all ages, no more than 1 scene.",
    "style": "cartoon style",
    "mode": "stepwise"
  }'

# 2. Execute steps sequentially
TASK_ID="your-task-id-here"
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

# 3. Monitor progress
curl http://localhost:5001/api/v1/tasks/$TASK_ID

# 4. Download final video
curl http://localhost:5001/api/v1/tasks/$TASK_ID/artifacts/final_video.mp4?content=true \
  --output final_video.mp4

# 5. List all generated artifacts
curl http://localhost:5001/api/v1/tasks/$TASK_ID/artifacts

# 6. Download other generated files (e.g., story.txt)
curl http://localhost:5001/api/v1/tasks/$TASK_ID/artifacts/story.txt?content=true \
  --output story.txt

# 7. Cancel a running task
curl -X POST http://localhost:5001/api/v1/tasks/$TASK_ID/cancel

# 8. Get task artifacts after completion
curl http://localhost:5001/api/v1/tasks/$TASK_ID/artifacts
```

### Complete API Usage Example

Here's a complete example showing all API endpoints in action:

```bash
#!/bin/bash

# Set the base URL
BASE_URL="http://localhost:5001/api/v1"

# 1. Create a task in stepwise mode
echo "Creating a new video generation task..."
RESPONSE=$(curl -s -X POST "$BASE_URL/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "idea": "A cat and a dog playing in the garden.",
    "user_requirement": "For all ages, no more than 1 scene.",
    "style": "cartoon style",
    "mode": "stepwise",
    "work_dir": "my_custom_directory"
  }')

# Extract task ID from response
TASK_ID=$(echo "$RESPONSE" | grep -o '"task_id":"[^"]*"' | cut -d'"' -f4)
echo "Task created with ID: $TASK_ID"

# 2. Get initial task status
echo "Checking task status..."
curl -s "$BASE_URL/tasks/$TASK_ID" | python -m json.tool

# 3. Execute steps one by one (with error checking)
echo "Starting stepwise generation..."

# Define steps in order
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
  echo "Executing step: $STEP"
  curl -X POST "$BASE_URL/tasks/$TASK_ID/steps/$STEP"
  
  # Wait for step to complete (simplified polling)
  sleep 5
  
  # Check task status
  STATUS=$(curl -s "$BASE_URL/tasks/$TASK_ID" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
  echo "Current status: $STATUS"
  
  if [ "$STATUS" = "failed" ]; then
    echo "Step $STEP failed. Check logs for details."
    break
  fi
done

# 4. Monitor final status
echo "Waiting for completion..."
while true; do
  STATUS=$(curl -s "$BASE_URL/tasks/$TASK_ID" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
  PROGRESS=$(curl -s "$BASE_URL/tasks/$TASK_ID" | grep -o '"progress":[0-9.]*' | cut -d':' -f2)
  
  printf "Status: %s, Progress: %s%%\\r" "$STATUS" "${PROGRESS:-0}"
  
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] || [ "$STATUS" = "cancelled" ]; then
    echo ""
    echo "Task finished with status: $STATUS"
    break
  fi
  
  sleep 2
done

# 5. List all generated artifacts
if [ "$STATUS" = "completed" ]; then
  echo "Generated artifacts:"
  curl -s "$BASE_URL/tasks/$TASK_ID/artifacts" | python -m json.tool
  
  # 6. Download the final video
  echo "Downloading final video..."
  curl -s "$BASE_URL/tasks/$TASK_ID/artifacts/final_video.mp4?content=true" \
    --output final_video.mp4
  echo "Video downloaded to: final_video.mp4"
  
  # 7. Download other important files
  echo "Downloading additional files..."
  curl -s "$BASE_URL/tasks/$TASK_ID/artifacts/story.txt?content=true" --output story.txt
  curl -s "$BASE_URL/tasks/$TASK_ID/artifacts/script.json?content=true" --output script.json
  curl -s "$BASE_URL/tasks/$TASK_ID/artifacts/storyboard.json?content=true" --output storyboard.json
fi

# 8. Cleanup: Cancel task if needed (example)
if [ "$STATUS" = "running" ]; then
  echo "Cancelling task..."
  curl -X POST "$BASE_URL/tasks/$TASK_ID/cancel"
fi
```

This example demonstrates:
- Creating a task with custom parameters
- Extracting the task ID from response
- Executing steps sequentially with error checking
- Real-time progress monitoring
- Downloading generated artifacts
- Task cancellation

## Legacy API

The original API endpoints are still available:

- `POST /api/generate` - Start generation (one-click)
- `GET /api/logs` - Stream logs via Server-Sent Events (SSE)
- `GET /api/task_status` - Get current task status
- `GET /api/files` - List generated files
- `GET /api/work_dirs` - List all working directories

## Configuration

The API uses the configuration file `configs/idea2video_deepseek_veo3.yaml`. Ensure this file exists and contains valid API keys for the required services.

## Error Handling

The API returns standard HTTP status codes:

- `200` OK: Request succeeded
- `201` Created: Resource created successfully
- `202` Accepted: Step execution started
- `400` Bad Request: Invalid input
- `404` Not Found: Resource not found
- `409` Conflict: Invalid operation (e.g., executing step in full mode)
- `500` Internal Server Error: Server error

Error responses include a JSON object with an `error` field describing the issue.

## Limitations

- The API is currently synchronous for step execution (each step runs in the background).
- Large video generation tasks may take several minutes to complete.
- No rate limiting is implemented.
- Some steps may still be under refinement and testing.

## Web Interface

The application includes a modern web interface with full support for API v1 features.

### Accessing the Interface

Navigate to `http://localhost:5001/` in your web browser to access the main interface.

### Key Features

1. **Dual Generation Modes**:
   - **One-click Generation**: Full automated pipeline execution
   - **Stepwise Generation**: Manual control over each step of the process

2. **Step Control Panel**:
   - Visual representation of all 10 generation steps
   - Real-time status updates (pending, running, completed, error)
   - Individual step execution buttons
   - Progress tracking and visualization

3. **Task Management**:
   - Create new tasks with custom parameters
   - Pause, resume, and cancel running tasks
   - Monitor task progress in real-time
   - View generated artifacts and files

4. **Project Browser**:
   - Browse historical projects and working directories
   - File tree explorer for generated content
   - Video preview and playback

### Using Stepwise Mode

1. **Select Stepwise Mode**: Choose "步骤化模式" from the generation mode dropdown in the Advanced Settings section.
2. **Enter Your Idea**: Provide your creative idea, requirements, and style preferences.
3. **Create Task**: Click "开始步骤化生成" to create a stepwise task.
4. **Control Steps**: Navigate to the "步骤控制" tab to see all available steps.
5. **Execute Steps**: Click individual step buttons to execute them in sequence.
6. **Monitor Progress**: Watch real-time status updates and progress indicators.

### User Interface Elements

- **Generation Mode Selector**: Dropdown to choose between "一键生成模式" and "步骤化模式"
- **Step Control Tab**: Dedicated tab with step cards and control buttons
- **Real-time Logs**: Live log streaming in the "生成日志" tab
- **Video Preview**: Generated video playback in the right sidebar
- **Project Statistics**: File counts, sizes, and generation metrics

The web interface provides a user-friendly way to interact with the API v1 endpoints while maintaining full compatibility with programmatic access.

## Troubleshooting

1. **Task not progressing**: Check the server logs for errors.
2. **Missing artifacts**: Ensure previous steps completed successfully.
3. **API keys expired**: Update the configuration file with valid API keys.
4. **Out of disk space**: Clean up old working directories.

## Support

For issues and feature requests, please open an issue in the project repository.