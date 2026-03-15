"""
API v1 for OpenShortVideo backend.
Supports both one-click generation and stepwise generation.
"""
import os
import json
import asyncio
import threading
import uuid
import enum
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
from dataclasses import dataclass, field, asdict
from flask import Blueprint, request, jsonify, current_app, abort, Response, make_response
from werkzeug.exceptions import BadRequest, NotFound, Conflict
import queue
import time
from flask import stream_with_context

from pipelines.idea2video_pipeline import Idea2VideoPipeline
from pipelines.script2video_pipeline import Script2VideoPipeline
from interfaces import CharacterInScene, ShotBriefDescription, ShotDescription, Camera
from services.generation_logger import gen_logger

def wait_for_file(file_path: str, max_retries: int = 10, retry_interval: float = 1.0) -> bool:
    """Wait for a file to exist with retries.
    
    Args:
        file_path: Path to the file
        max_retries: Maximum number of retries
        retry_interval: Seconds between retries
    
    Returns:
        True if file exists, False otherwise
    """
    for attempt in range(max_retries):
        if os.path.exists(file_path):
            return True
        if attempt < max_retries - 1:
            time.sleep(retry_interval)
    return False

def wait_for_file_and_load_json(file_path: str, max_retries: int = 10, retry_interval: float = 1.0) -> Optional[Any]:
    """Wait for a JSON file to exist and load it.
    
    Args:
        file_path: Path to the JSON file
        max_retries: Maximum number of retries
        retry_interval: Seconds between retries
    
    Returns:
        Loaded JSON data, or None if file doesn't exist after retries or JSON is invalid
    """
    if wait_for_file(file_path, max_retries, retry_interval):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Handle wrapped format: {"content": "...", "type": "text"}
            if isinstance(data, dict) and 'content' in data:
                content = data['content']
                if isinstance(content, str):
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        return content  # Return as string if not valid JSON
                else:
                    return content
            return data
        except (json.JSONDecodeError, IOError, OSError):
            return None
    return None


def load_characters_from_file(file_path: str) -> List[CharacterInScene]:
    """Load characters from a JSON file, handling both raw list format and wrapped format.
    
    Args:
        file_path: Path to characters.json file
    
    Returns:
        List of CharacterInScene objects
    
    Raises:
        ValueError: If file doesn't exist or format is invalid
    """
    if not os.path.exists(file_path):
        raise ValueError(f"Characters file not found: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Handle wrapped format: {"content": "...", "type": "text"}
    if isinstance(data, dict) and 'content' in data:
        content = data['content']
        if isinstance(content, str):
            # Content is a JSON string, parse it
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                raise ValueError(f"Invalid JSON string in content field: {content[:100]}...")
        else:
            data = content
    
    # At this point, data should be a list of character dicts
    if not isinstance(data, list):
        raise ValueError(f"Expected list of characters, got {type(data)}")
    
    return [CharacterInScene.model_validate(c) for c in data]

# Define steps for stepwise generation
class Step(str, enum.Enum):
    DEVELOP_STORY = "develop_story"
    EXTRACT_CHARACTERS = "extract_characters"
    GENERATE_CHARACTER_PORTRAITS = "generate_character_portraits"
    WRITE_SCRIPT = "write_script"
    DESIGN_STORYBOARD = "design_storyboard"
    DECOMPOSE_VISUAL_DESCRIPTIONS = "decompose_visual_descriptions"
    CONSTRUCT_CAMERA_TREE = "construct_camera_tree"
    GENERATE_FRAMES = "generate_frames"
    GENERATE_VIDEOS = "generate_videos"
    CONCATENATE_VIDEOS = "concatenate_videos"

# Task status
class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class Task:
    """Represents a video generation task."""
    task_id: str
    work_dir: str
    idea: str
    user_requirement: str
    style: str
    mode: str  # "full" or "stepwise"
    status: TaskStatus = TaskStatus.PENDING
    current_step: Optional[Step] = None
    progress: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    pipeline: Optional[Idea2VideoPipeline] = None
    script_pipeline: Optional[Script2VideoPipeline] = None
    scene_working_dir: Optional[str] = None  # Directory for scene-specific files
    artifacts: Dict[str, Any] = field(default_factory=dict)  # store intermediate results
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary for JSON serialization."""
        # Manually build dict to avoid deep copying non-serializable fields
        data = {
            'task_id': self.task_id,
            'work_dir': self.work_dir,
            'idea': self.idea,
            'user_requirement': self.user_requirement,
            'style': self.style,
            'mode': self.mode,
            'status': self.status.value if hasattr(self.status, 'value') else self.status,
            'current_step': self.current_step.value if self.current_step and hasattr(self.current_step, 'value') else self.current_step,
            'progress': self.progress,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error': self.error,
            'scene_working_dir': self.scene_working_dir,
            'artifacts': self.artifacts if self.artifacts else {}
        }
        return data

class TaskManager:
    """Manages video generation tasks with file-based persistence."""
    
    def __init__(self, storage_dir: str = ".task_storage"):
        self.tasks: Dict[str, Task] = {}
        self._lock = threading.Lock()
        self.storage_dir = storage_dir
        # Ensure storage directory exists
        os.makedirs(storage_dir, exist_ok=True)
        # Load existing tasks from disk
        self._load_all_tasks()
    
    def _get_task_file_path(self, task_id: str) -> str:
        """Get the file path for a task's persistent storage."""
        return os.path.join(self.storage_dir, f"{task_id}.json")
    
    def _save_task_to_disk(self, task: Task):
        """Save a task to disk for persistence using atomic write."""
        try:
            file_path = self._get_task_file_path(task.task_id)
            temp_path = file_path + '.tmp'
            
            # Write to temp file first
            data = task.to_dict()
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # Atomic rename
            os.replace(temp_path, file_path)
        except Exception as e:
            print(f"Warning: Failed to save task {task.task_id} to disk: {e}")
            import traceback
            traceback.print_exc()
    
    def _load_task_from_disk(self, task_id: str) -> Optional[Task]:
        """Load a task from disk."""
        try:
            file_path = self._get_task_file_path(task_id)
            if not os.path.exists(file_path):
                return None
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Convert string status back to enum
            if data.get('status'):
                data['status'] = TaskStatus(data['status'])
            else:
                data['status'] = TaskStatus.PENDING
                
            # Convert current_step back to enum
            if data.get('current_step'):
                try:
                    data['current_step'] = Step(data['current_step'])
                except ValueError:
                    data['current_step'] = None
            else:
                data['current_step'] = None
            
            # Convert ISO format strings back to datetime
            for key in ['created_at', 'started_at', 'completed_at']:
                if data.get(key):
                    try:
                        data[key] = datetime.fromisoformat(data[key])
                    except (ValueError, TypeError):
                        data[key] = None
            
            # Remove fields that shouldn't be loaded
            data.pop('pipeline', None)
            data.pop('script_pipeline', None)
            
            # Create task object
            task = Task(**data)
            return task
        except Exception as e:
            print(f"Warning: Failed to load task {task_id} from disk: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _load_all_tasks(self):
        """Load all tasks from disk on startup."""
        try:
            for filename in os.listdir(self.storage_dir):
                if filename.endswith('.json'):
                    task_id = filename[:-5]  # Remove .json extension
                    task = self._load_task_from_disk(task_id)
                    if task:
                        self.tasks[task_id] = task
                        print(f"Loaded task {task_id} from disk")
        except Exception as e:
            print(f"Warning: Failed to load tasks from disk: {e}")
    
    def create_task(
        self,
        idea: str,
        user_requirement: str,
        style: str,
        mode: str = "full",
        work_dir: Optional[str] = None
    ) -> Task:
        """Create a new task."""
        if mode not in ("full", "stepwise"):
            raise ValueError("mode must be 'full' or 'stepwise'")
        
        task_id = str(uuid.uuid4())
        if work_dir is None:
            work_dir = os.path.join("working_dir_idea2video", task_id)
        
        # Ensure work directory exists
        os.makedirs(work_dir, exist_ok=True)
        
        task = Task(
            task_id=task_id,
            work_dir=work_dir,
            idea=idea,
            user_requirement=user_requirement,
            style=style,
            mode=mode
        )
        
        with self._lock:
            self.tasks[task_id] = task
            self._save_task_to_disk(task)
        
        return task
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        with self._lock:
            # First check memory
            task = self.tasks.get(task_id)
            if task:
                return task
            
            # If not in memory, try to load from disk
            task = self._load_task_from_disk(task_id)
            if task:
                self.tasks[task_id] = task
                return task
            
            return None
    
    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        current_step: Optional[Step] = None,
        progress: Optional[float] = None,
        error: Optional[str] = None
    ) -> bool:
        """Update task status."""
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                # Try to load from disk
                task = self._load_task_from_disk(task_id)
                if not task:
                    return False
                self.tasks[task_id] = task
            
            print(f"[TASK MANAGER DEBUG] Updating task {task_id}:")
            print(f"[TASK MANAGER DEBUG]   Old status: {task.status}, progress: {task.progress}, current_step: {task.current_step}")
            print(f"[TASK MANAGER DEBUG]   New status: {status}, progress: {progress}, current_step: {current_step}")
            
            if status == TaskStatus.RUNNING and task.status == TaskStatus.PENDING:
                task.started_at = datetime.now()
            elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                task.completed_at = datetime.now()
            
            task.status = status
            if current_step is not None:
                task.current_step = current_step
            if progress is not None:
                task.progress = progress
            if error is not None:
                task.error = error
            
            print(f"[TASK MANAGER DEBUG]   After update: status={task.status}, progress={task.progress}, current_step={task.current_step}")
            
            # Persist changes to disk
            self._save_task_to_disk(task)
            
            return True
    
    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        with self._lock:
            # Remove from memory
            removed = self.tasks.pop(task_id, None) is not None
            
            # Remove from disk
            try:
                file_path = self._get_task_file_path(task_id)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    removed = True
            except Exception as e:
                print(f"Warning: Failed to delete task file for {task_id}: {e}")
            
            return removed

# Global task manager
task_manager = TaskManager()

# Create Blueprint
api_v1 = Blueprint('api_v1', __name__, url_prefix='/api/v1')

@api_v1.route('/tasks', methods=['POST'])
def create_task():
    """Create a new video generation task.
    
    Request body:
    {
        "idea": "story idea text",
        "user_requirement": "requirements text",
        "style": "style description",
        "mode": "full|stepwise",
        "work_dir": "optional custom work directory"
    }
    """
    data = request.get_json()
    if not data:
        raise BadRequest("JSON body required")
    
    idea = data.get('idea', '').strip()
    if not idea:
        raise BadRequest("idea is required")
    
    user_requirement = data.get('user_requirement', '').strip()
    style = data.get('style', '').strip()
    mode = data.get('mode', 'full')
    work_dir = data.get('work_dir')
    
    try:
        task = task_manager.create_task(
            idea=idea,
            user_requirement=user_requirement,
            style=style,
            mode=mode,
            work_dir=work_dir
        )
    except ValueError as e:
        raise BadRequest(str(e))
    
    # If mode is full, start the full pipeline in background
    if mode == "full":
        thread = threading.Thread(
            target=run_full_pipeline,
            args=(task.task_id,)
        )
        thread.daemon = True
        thread.start()
    
    return jsonify({
        'task_id': task.task_id,
        'work_dir': task.work_dir,
        'mode': task.mode,
        'status': task.status.value,
        'created_at': task.created_at.isoformat()
    }), 201

@api_v1.route('/tasks/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """Get task status and progress."""
    task = task_manager.get_task(task_id)
    if not task:
        raise NotFound(f"Task {task_id} not found")
    
    return jsonify(task.to_dict())

@api_v1.route('/tasks/<task_id>/steps/<step_name>', methods=['POST'])
def execute_step(task_id, step_name):
    """Execute a specific step for stepwise generation."""
    task = task_manager.get_task(task_id)
    if not task:
        raise NotFound(f"Task {task_id} not found")
    
    if task.mode != "stepwise":
        raise Conflict("Task is not in stepwise mode")
    
    if task.status != TaskStatus.PENDING and task.status != TaskStatus.RUNNING:
        raise Conflict(f"Task is {task.status}, cannot execute steps")
    
    try:
        step = Step(step_name)
    except ValueError:
        raise BadRequest(f"Invalid step name. Valid steps: {[s.value for s in Step]}")
    
    # Check step dependencies (simplified)
    # In a real implementation, we would validate step order
    
    # Update task status - don't reset progress, keep current progress
    task_manager.update_task_status(
        task_id,
        TaskStatus.RUNNING,
        current_step=step
        # Don't reset progress - will be updated when step completes
    )
    
    # Execute step in background
    thread = threading.Thread(
        target=run_single_step,
        args=(task_id, step)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'task_id': task_id,
        'step': step.value,
        'status': 'started'
    }), 202

@api_v1.route('/tasks/<task_id>/artifacts', methods=['GET'])
def list_artifacts(task_id):
    """List available artifacts for a task."""
    task = task_manager.get_task(task_id)
    if not task:
        raise NotFound(f"Task {task_id} not found")
    
    artifacts = {}
    work_dir = task.work_dir
    
    # Common artifact files
    artifact_files = [
        'story.txt',
        'characters.json',
        'character_portraits_registry.json',
        'script.json',
        'storyboard.json',
        'camera_tree.json',
        'final_video.mp4'
    ]
    
    for file_name in artifact_files:
        file_path = os.path.join(work_dir, file_name)
        if os.path.exists(file_path):
            artifacts[file_name] = {
                'path': file_path,
                'size': os.path.getsize(file_path),
                'modified': datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
            }
    
    # Also list all files in work directory
    all_files = []
    for root, dirs, files in os.walk(work_dir):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, work_dir)
            all_files.append({
                'name': file,
                'path': rel_path,
                'size': os.path.getsize(full_path),
                'type': 'file'
            })
    
    return jsonify({
        'artifacts': artifacts,
        'all_files': all_files
    })

@api_v1.route('/tasks/<task_id>/artifacts/<path:file_path>', methods=['GET'])
def get_artifact(task_id, file_path):
    """Get artifact content or metadata."""
    task = task_manager.get_task(task_id)
    if not task:
        raise NotFound(f"Task {task_id} not found")
    
    full_path = os.path.join(task.work_dir, file_path)
    if not os.path.exists(full_path):
        raise NotFound(f"Artifact {file_path} not found")
    
    # Return file info or content based on query parameter
    if request.args.get('content', 'false').lower() == 'true':
        # For text files, return content
        if file_path.endswith(('.txt', '.json', '.yaml', '.yml', '.py', '.js', '.css', '.html')):
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return jsonify({
                    'content': content,
                    'type': 'text'
                })
            except:
                pass
        
        # For binary files, return metadata only
        return jsonify({
            'type': 'binary',
            'path': full_path,
            'size': os.path.getsize(full_path)
        })
    else:
        # Return metadata
        return jsonify({
            'path': full_path,
            'size': os.path.getsize(full_path),
            'modified': datetime.fromtimestamp(os.path.getmtime(full_path)).isoformat(),
            'type': 'file' if os.path.isfile(full_path) else 'directory'
        })

@api_v1.route('/tasks/<task_id>/cancel', methods=['POST'])
def cancel_task(task_id):
    """Cancel a running task."""
    task = task_manager.get_task(task_id)
    if not task:
        raise NotFound(f"Task {task_id} not found")
    
    if task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
        raise Conflict(f"Task is {task.status}, cannot cancel")
    
    task_manager.update_task_status(
        task_id,
        TaskStatus.CANCELLED,
        error="Cancelled by user"
    )
    
    # TODO: Implement actual cancellation of running pipeline
    
    return jsonify({
        'task_id': task_id,
        'status': 'cancelled'
    })

# Background task execution functions
def run_full_pipeline(task_id: str):
    """Run full pipeline in background thread."""
    task = task_manager.get_task(task_id)
    if not task:
        return
    
    task_manager.update_task_status(
        task_id,
        TaskStatus.RUNNING,
        progress=0.0
    )
    
    try:
        # Initialize pipeline
        pipeline = Idea2VideoPipeline.init_from_config(
            config_path="configs/idea2video_deepseek_veo3_fast.yaml",
            working_dir=task.work_dir
        )
        
        task.pipeline = pipeline
        
        # Run pipeline (async)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(pipeline(
            idea=task.idea,
            user_requirement=task.user_requirement,
            style=task.style
        ))

        task_manager.update_task_status(
            task_id,
            TaskStatus.COMPLETED,
            progress=100.0
        )
        
    except Exception as e:
        task_manager.update_task_status(
            task_id,
            TaskStatus.FAILED,
            error=str(e)
        )

def get_script2video_pipeline(task: Task, idea_pipeline: Idea2VideoPipeline) -> Script2VideoPipeline:
    """Get or create Script2VideoPipeline for the task."""
    if task.script_pipeline is None:
        # Initialize scene working directory if not set
        if task.scene_working_dir is None:
            task.scene_working_dir = os.path.join(task.work_dir, 'scene_0')
            os.makedirs(task.scene_working_dir, exist_ok=True)
            # Save task to persist scene_working_dir
            task_manager._save_task_to_disk(task)
        
        # Create Script2VideoPipeline
        task.script_pipeline = Script2VideoPipeline(
            mllm_model=idea_pipeline.mllm_model,
            chat_model=idea_pipeline.chat_model,
            image_generator=idea_pipeline.image_generator,
            video_generator=idea_pipeline.video_generator,
            working_dir=task.scene_working_dir
        )
    
    return task.script_pipeline

def load_shot_descriptions(task: Task):
    """Load shot descriptions from files with retry mechanism."""
    scene_dir = task.scene_working_dir or os.path.join(task.work_dir, 'scene_0')
    shot_descriptions = []
    
    # First try to load from consolidated shot_descriptions.json file
    consolidated_file = os.path.join(scene_dir, 'shot_descriptions.json')
    if os.path.exists(consolidated_file):
        try:
            with open(consolidated_file, 'r', encoding='utf-8') as f:
                shot_data_list = json.load(f)
            for shot_data in shot_data_list:
                shot_desc = ShotDescription.model_validate(shot_data)
                shot_descriptions.append(shot_desc)
            return shot_descriptions
        except Exception as e:
            # Fall back to per-shot files
            pass
    
    # Wait for shot description files with retry
    shots_dir = os.path.join(scene_dir, 'shots')
    if wait_for_file(shots_dir, max_retries=10, retry_interval=1.0):
        for shot_idx_str in os.listdir(shots_dir):
            shot_dir = os.path.join(shots_dir, shot_idx_str)
            desc_path = os.path.join(shot_dir, 'shot_description.json')
            if wait_for_file(desc_path, max_retries=5, retry_interval=0.5):
                try:
                    with open(desc_path, 'r', encoding='utf-8') as f:
                        shot_desc = ShotDescription.model_validate(json.load(f))
                        shot_descriptions.append(shot_desc)
                except Exception as e:
                    continue
    
    return shot_descriptions

def run_single_step(task_id: str, step: Step):
    """Execute a single step in background thread."""
    import traceback
    import time
    
    step_start_time = time.time()
    
    # 记录步骤开始
    gen_logger.step_started(task_id, step.value)
    print(f"[STEP EXECUTION] Starting step '{step.value}' for task {task_id}")
    
    task = task_manager.get_task(task_id)
    if not task:
        gen_logger.step_failed(task_id, step.value, "Task not found")
        print(f"[STEP EXECUTION] ERROR: Task {task_id} not found!")
        return
    
    gen_logger.debug(task_id, step.value, f"Task found: {task.idea[:50]}...", 
                    artifacts=list(task.artifacts.keys()))
    print(f"[STEP EXECUTION] Task found: {task.idea[:50]}...")
    print(f"[STEP EXECUTION] Current artifacts: {list(task.artifacts.keys())}")
    
    try:
        # Initialize pipeline if not already done
        gen_logger.debug(task_id, step.value, "Initializing pipeline...")
        print(f"[STEP EXECUTION] Initializing pipeline...")
        
        if task.pipeline is None:
            gen_logger.info(task_id, step.value, "Creating new Idea2VideoPipeline instance",
                          config="configs/idea2video_deepseek_veo3_fast.yaml")
            print(f"[STEP EXECUTION] Creating new Idea2VideoPipeline instance...")
            task.pipeline = Idea2VideoPipeline.init_from_config(
                config_path="configs/idea2video_deepseek_veo3_fast.yaml",
                working_dir=task.work_dir
            )
            gen_logger.step_completed(task_id, step.value + "_pipeline_init")
            print(f"[STEP EXECUTION] Pipeline initialized successfully")
        else:
            gen_logger.debug(task_id, step.value, "Using existing pipeline instance")
            print(f"[STEP EXECUTION] Using existing pipeline instance")
        
        pipeline = task.pipeline
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        gen_logger.debug(task_id, step.value, "Async event loop created")
        print(f"[STEP EXECUTION] Async event loop created")
        
        # Map step to pipeline method
        gen_logger.info(task_id, step.value, "Executing step...")
        print(f"[STEP EXECUTION] Executing step: {step.value}")
        
        if step == Step.DEVELOP_STORY:
            gen_logger.info(task_id, step.value, "Calling develop_story pipeline method")
            print(f"[STEP EXECUTION] Calling develop_story...")
            story = loop.run_until_complete(asyncio.wait_for(pipeline.develop_story(
                idea=task.idea,
                user_requirement=task.user_requirement
            ), timeout=120))
            gen_logger.debug(task_id, step.value, f"Story returned, type: {type(story)}, length: {len(story) if story else 0}")
            print(f"[STEP EXECUTION] Story returned, type: {type(story)}, length: {len(story) if story else 0}")
            task.artifacts['story'] = story
            
            # 保存到文件
            story_file = os.path.join(task.work_dir, 'story.txt')
            with open(story_file, 'w', encoding='utf-8') as f:
                f.write(story)
            gen_logger.log_file_saved(task_id, step.value, story_file)
            gen_logger.log_artifact_updated(task_id, step.value, 'story')
            print(f"[STEP EXECUTION] Story saved to artifacts, keys: {list(task.artifacts.keys())}")
        
        elif step == Step.EXTRACT_CHARACTERS:
            gen_logger.info(task_id, step.value, "Extracting characters from story")
            print(f"[STEP EXECUTION] Extracting characters...")
            print(f"[STEP EXECUTION] Task artifacts keys: {list(task.artifacts.keys())}")
            print(f"[STEP EXECUTION] Task work_dir: {task.work_dir}")
            if 'story' not in task.artifacts:
                # Load story from file
                story_path = os.path.join(task.work_dir, 'story.txt')
                gen_logger.debug(task_id, step.value, f"Looking for story at: {story_path}")
                print(f"[STEP EXECUTION] Looking for story at: {story_path}")
                if os.path.exists(story_path):
                    with open(story_path, 'r', encoding='utf-8') as f:
                        story = f.read()
                    gen_logger.log_file_loaded(task_id, step.value, story_path, story_length=len(story))
                    print(f"[STEP EXECUTION] Story loaded from file, length: {len(story)}")
                else:
                    gen_logger.step_failed(task_id, step.value, "Story not found. Run develop_story first.")
                    raise ValueError("Story not found. Run develop_story first.")
            else:
                story = task.artifacts['story']
                gen_logger.debug(task_id, step.value, f"Using story from artifacts, length: {len(story) if story else 0}")
                print(f"[STEP EXECUTION] Using story from artifacts, length: {len(story) if story else 0}")
            
            gen_logger.info(task_id, step.value, "Calling extract_characters pipeline method")
            print(f"[STEP EXECUTION] Calling extract_characters...")
            characters = loop.run_until_complete(pipeline.extract_characters(story))
            # Convert Pydantic models to dictionaries for serialization
            task.artifacts['characters'] = [c.model_dump() for c in characters]
            
            # 保存到文件
            chars_file = os.path.join(task.work_dir, 'characters.json')
            with open(chars_file, 'w', encoding='utf-8') as f:
                json.dump([c.model_dump() for c in characters], f, ensure_ascii=False, indent=2)
            gen_logger.log_file_saved(task_id, step.value, chars_file)
            gen_logger.log_artifact_updated(task_id, step.value, 'characters', count=len(characters))
            gen_logger.step_completed(task_id, step.value, characters_count=len(characters))
            print(f"[STEP EXECUTION] Characters extracted: {len(characters) if characters else 0} characters")
        
        elif step == Step.GENERATE_CHARACTER_PORTRAITS:
            gen_logger.info(task_id, step.value, "Generating character portraits", style=task.style)
            print(f"[STEP EXECUTION] Generating character portraits...")
            if 'characters' not in task.artifacts:
                # Load characters from file using helper function
                chars_path = os.path.join(task.work_dir, 'characters.json')
                gen_logger.debug(task_id, step.value, f"Looking for characters at: {chars_path}")
                print(f"[STEP EXECUTION] Looking for characters at: {chars_path}")
                try:
                    characters = load_characters_from_file(chars_path)
                    gen_logger.log_file_loaded(task_id, step.value, chars_path, count=len(characters))
                    print(f"[STEP EXECUTION] Characters loaded from file: {len(characters)} characters")
                except Exception as e:
                    gen_logger.step_failed(task_id, step.value, f"Failed to load characters: {e}")
                    raise ValueError(f"Failed to load characters: {e}")
            else:
                chars_data = task.artifacts['characters']
                # Convert dictionaries back to CharacterInScene objects if needed
                if chars_data and isinstance(chars_data[0], dict):
                    characters = [CharacterInScene.model_validate(c) for c in chars_data]
                else:
                    characters = chars_data  # already objects
                gen_logger.debug(task_id, step.value, f"Using characters from artifacts: {len(characters)} characters")
                print(f"[STEP EXECUTION] Using characters from artifacts: {len(characters)} characters")
            
            gen_logger.info(task_id, step.value, "Calling generate_character_portraits pipeline method", style=task.style)
            print(f"[STEP EXECUTION] Calling generate_character_portraits with style: {task.style}")
            registry = loop.run_until_complete(pipeline.generate_character_portraits(
                characters=characters,
                character_portraits_registry=None,
                style=task.style
            ))
            task.artifacts['character_portraits_registry'] = registry
            
            # 保存到文件
            registry_file = os.path.join(task.work_dir, 'character_portraits_registry.json')
            with open(registry_file, 'w', encoding='utf-8') as f:
                json.dump(registry, f, ensure_ascii=False, indent=2)
            gen_logger.log_file_saved(task_id, step.value, registry_file)
            gen_logger.log_artifact_updated(task_id, step.value, 'character_portraits_registry')
            gen_logger.step_completed(task_id, step.value)
            print(f"[STEP EXECUTION] Character portraits generated successfully")
        
        elif step == Step.WRITE_SCRIPT:
            gen_logger.info(task_id, step.value, "Writing script based on story")
            if 'story' not in task.artifacts:
                # Load story from file
                story_path = os.path.join(task.work_dir, 'story.txt')
                gen_logger.debug(task_id, step.value, f"Looking for story at: {story_path}")
                if os.path.exists(story_path):
                    with open(story_path, 'r', encoding='utf-8') as f:
                        story = f.read()
                    gen_logger.log_file_loaded(task_id, step.value, story_path, story_length=len(story))
                else:
                    gen_logger.step_failed(task_id, step.value, "Story not found. Run develop_story first.")
                    raise ValueError("Story not found. Run develop_story first.")
            else:
                story = task.artifacts['story']
                gen_logger.debug(task_id, step.value, f"Using story from artifacts, length: {len(story) if story else 0}")
            
            gen_logger.info(task_id, step.value, "Calling write_script_based_on_story pipeline method")
            script = loop.run_until_complete(pipeline.write_script_based_on_story(
                story=story,
                user_requirement=task.user_requirement
            ))
            task.artifacts['script'] = script
            
            # 保存到文件 - 确保是JSON格式
            script_file = os.path.join(task.work_dir, 'script.json')
            if isinstance(script, dict):
                with open(script_file, 'w', encoding='utf-8') as f:
                    json.dump(script, f, ensure_ascii=False, indent=2)
            elif isinstance(script, list):
                with open(script_file, 'w', encoding='utf-8') as f:
                    json.dump(script, f, ensure_ascii=False, indent=2)
            else:
                # 如果是字符串，保存为纯文本
                with open(script_file, 'w', encoding='utf-8') as f:
                    f.write(str(script))
            gen_logger.log_file_saved(task_id, step.value, script_file)
            gen_logger.log_artifact_updated(task_id, step.value, 'script')
            gen_logger.step_completed(task_id, step.value)
            print(f"[STEP EXECUTION] Script saved successfully")
        
        elif step == Step.DESIGN_STORYBOARD:
            gen_logger.info(task_id, step.value, "Designing storyboard")
            gen_logger.info(task_id, step.value, f"task.scene_working_dir: {task.scene_working_dir}")
            gen_logger.info(task_id, step.value, f"task.work_dir: {task.work_dir}")
            # Design storyboard - requires script and characters
            if 'script' not in task.artifacts:
                # Load script from file
                script_path = os.path.join(task.work_dir, 'script.json')
                gen_logger.debug(task_id, step.value, f"Looking for script at: {script_path}")
                if os.path.exists(script_path):
                    with open(script_path, 'r', encoding='utf-8') as f:
                        script = json.load(f)
                    task.artifacts['script'] = script
                    gen_logger.log_file_loaded(task_id, step.value, script_path)
                else:
                    gen_logger.step_failed(task_id, step.value, "Script not found. Run write_script first.")
                    raise ValueError("Script not found. Run write_script first.")
            else:
                script = task.artifacts['script']
                gen_logger.debug(task_id, step.value, f"Using script from artifacts")
            
            # Load characters
            chars_path = os.path.join(task.work_dir, 'characters.json')
            gen_logger.debug(task_id, step.value, f"Looking for characters at: {chars_path}")
            try:
                characters = load_characters_from_file(chars_path)
                # Store as dicts for JSON serialization, keep objects for use
                task.artifacts['characters'] = [c.model_dump() for c in characters]
                gen_logger.log_file_loaded(task_id, step.value, chars_path, count=len(characters))
            except Exception as e:
                gen_logger.step_failed(task_id, step.value, f"Failed to load characters: {e}")
                raise ValueError(f"Failed to load characters: {e}")
            
            # Get or create Script2VideoPipeline
            gen_logger.debug(task_id, step.value, "Getting Script2VideoPipeline")
            gen_logger.info(task_id, step.value, f"Before get_script2video_pipeline: task.scene_working_dir={task.scene_working_dir}")
            script2video = get_script2video_pipeline(task, pipeline)
            gen_logger.info(task_id, step.value, f"After get_script2video_pipeline: task.scene_working_dir={task.scene_working_dir}")
            
            # Design storyboard
            gen_logger.info(task_id, step.value, "Calling design_storyboard pipeline method")
            gen_logger.info(task_id, step.value, f"Script2VideoPipeline working_dir: {script2video.working_dir}")
            storyboard = loop.run_until_complete(script2video.design_storyboard(
                script=script,
                characters=characters,
                user_requirement=task.user_requirement
            ))
            gen_logger.info(task_id, step.value, f"Storyboard generated, {len(storyboard)} shots")
            # Convert storyboard to dicts for JSON serialization
            task.artifacts['storyboard'] = [s.model_dump() for s in storyboard]
            
            # 保存到文件
            storyboard_file = os.path.join(task.scene_working_dir or task.work_dir, 'storyboard.json')
            gen_logger.info(task_id, step.value, f"Saving storyboard to: {storyboard_file}")
            with open(storyboard_file, 'w', encoding='utf-8') as f:
                json.dump([s.model_dump() for s in storyboard], f, ensure_ascii=False, indent=2)
            gen_logger.info(task_id, step.value, f"Storyboard saved, file exists: {os.path.exists(storyboard_file)}")
            gen_logger.log_file_saved(task_id, step.value, storyboard_file)
            gen_logger.log_artifact_updated(task_id, step.value, 'storyboard', count=len(storyboard))
            gen_logger.step_completed(task_id, step.value, shots_count=len(storyboard))
            print(f"[STEP EXECUTION] Storyboard designed: {len(storyboard)} shots")
            
        elif step == Step.DECOMPOSE_VISUAL_DESCRIPTIONS:
            gen_logger.info(task_id, step.value, "Decomposing visual descriptions")
            # Decompose visual descriptions - requires storyboard
            # Ensure scene_working_dir is initialized
            if task.scene_working_dir is None:
                task.scene_working_dir = os.path.join(task.work_dir, 'scene_0')
                os.makedirs(task.scene_working_dir, exist_ok=True)
                # Save task to persist scene_working_dir
                task_manager._save_task_to_disk(task)
            
            if 'storyboard' not in task.artifacts:
                # Load storyboard from file with retry mechanism
                storyboard_path = os.path.join(task.scene_working_dir, 'storyboard.json')
                gen_logger.debug(task_id, step.value, f"Looking for storyboard at: {storyboard_path}")
                gen_logger.info(task_id, step.value, f"Waiting for storyboard file (max 30 seconds)...")
                storyboard_data = wait_for_file_and_load_json(storyboard_path, max_retries=30, retry_interval=1.0)
                if storyboard_data:
                    task.artifacts['storyboard'] = storyboard_data
                    gen_logger.log_file_loaded(task_id, step.value, storyboard_path, count=len(storyboard_data))
                else:
                    gen_logger.step_failed(task_id, step.value, "Storyboard not found. Run design_storyboard first.")
                    raise ValueError("Storyboard not found. Run design_storyboard first.")
            
            # Convert storyboard data to objects for use
            storyboard_data = task.artifacts['storyboard']
            if storyboard_data and isinstance(storyboard_data[0], dict):
                storyboard = [ShotBriefDescription.model_validate(s) for s in storyboard_data]
            else:
                storyboard = storyboard_data
            
            # Load characters
            if 'characters' not in task.artifacts:
                chars_path = os.path.join(task.work_dir, 'characters.json')
                gen_logger.info(task_id, step.value, f"Waiting for characters file (max 30 seconds)...")
                # Wait for file and load characters
                if wait_for_file(chars_path, max_retries=30, retry_interval=1.0):
                    try:
                        characters = load_characters_from_file(chars_path)
                        task.artifacts['characters'] = [c.model_dump() for c in characters]
                    except Exception as e:
                        raise ValueError(f"Failed to load characters: {e}")
                else:
                    raise ValueError("Characters not found. Run extract_characters first.")
            else:
                chars_data = task.artifacts['characters']
                if chars_data and isinstance(chars_data[0], dict):
                    characters = [CharacterInScene.model_validate(c) for c in chars_data]
                else:
                    characters = chars_data
            
            # Get or create Script2VideoPipeline
            script2video = get_script2video_pipeline(task, pipeline)
            
            # Decompose visual descriptions
            gen_logger.info(task_id, step.value, "Calling decompose_visual_descriptions pipeline method")
            shot_descriptions = loop.run_until_complete(script2video.decompose_visual_descriptions(
                shot_brief_descriptions=storyboard,
                characters=characters
            ))
            # Convert to dicts for JSON serialization
            task.artifacts['shot_descriptions'] = [s.model_dump() for s in shot_descriptions]
            
            # 保存到文件
            shots_file = os.path.join(task.scene_working_dir or task.work_dir, 'shot_descriptions.json')
            with open(shots_file, 'w', encoding='utf-8') as f:
                json.dump([s.model_dump() for s in shot_descriptions], f, ensure_ascii=False, indent=2)
            gen_logger.log_file_saved(task_id, step.value, shots_file)
            gen_logger.log_artifact_updated(task_id, step.value, 'shot_descriptions', count=len(shot_descriptions))
            gen_logger.step_completed(task_id, step.value, shots_count=len(shot_descriptions))
            
        elif step == Step.CONSTRUCT_CAMERA_TREE:
            gen_logger.info(task_id, step.value, "Constructing camera tree")
            # Construct camera tree - requires shot_descriptions
            if 'shot_descriptions' not in task.artifacts:
                # Try to load from files
                shot_descriptions = load_shot_descriptions(task)
                if not shot_descriptions:
                    gen_logger.step_failed(task_id, step.value, "Shot descriptions not found")
                    raise ValueError("Shot descriptions not found. Run decompose_visual_descriptions first.")
            else:
                # Convert from dicts if needed
                shot_descriptions_data = task.artifacts['shot_descriptions']
                if shot_descriptions_data and isinstance(shot_descriptions_data[0], dict):
                    shot_descriptions = [ShotDescription.model_validate(s) for s in shot_descriptions_data]
                else:
                    shot_descriptions = shot_descriptions_data
            
            # Get or create Script2VideoPipeline
            script2video = get_script2video_pipeline(task, pipeline)
            
            # Construct camera tree
            gen_logger.info(task_id, step.value, "Calling construct_camera_tree pipeline method")
            camera_tree = loop.run_until_complete(script2video.construct_camera_tree(
                shot_descriptions=shot_descriptions
            ))
            # Convert to dicts for JSON serialization
            task.artifacts['camera_tree'] = [c.model_dump() for c in camera_tree]
            
            # 保存到文件
            camera_file = os.path.join(task.scene_working_dir or task.work_dir, 'camera_tree.json')
            with open(camera_file, 'w', encoding='utf-8') as f:
                json.dump([c.model_dump() for c in camera_tree], f, ensure_ascii=False, indent=2)
            gen_logger.log_file_saved(task_id, step.value, camera_file)
            gen_logger.log_artifact_updated(task_id, step.value, 'camera_tree', count=len(camera_tree))
            gen_logger.step_completed(task_id, step.value, cameras_count=len(camera_tree))
            
        elif step == Step.GENERATE_FRAMES:
            gen_logger.info(task_id, step.value, "========== STARTING GENERATE_FRAMES STEP ==========")
            # Generate frames - requires camera_tree, shot_descriptions, characters, character portraits
            if 'camera_tree' not in task.artifacts:
                # Try to load from file
                camera_file = os.path.join(task.scene_working_dir or task.work_dir, 'camera_tree.json')
                gen_logger.info(task_id, step.value, f"Loading camera_tree from file: {camera_file}")
                if os.path.exists(camera_file):
                    with open(camera_file, 'r', encoding='utf-8') as f:
                        camera_tree_data = json.load(f)
                        task.artifacts['camera_tree'] = camera_tree_data
                        gen_logger.info(task_id, step.value, f"Loaded camera_tree from file, count: {len(camera_tree_data)}")
                else:
                    gen_logger.step_failed(task_id, step.value, "Camera tree not found")
                    raise ValueError("Camera tree not found. Run construct_camera_tree first.")
            
            # Convert camera_tree from dicts if needed
            camera_tree_data = task.artifacts['camera_tree']
            if camera_tree_data and isinstance(camera_tree_data[0], dict):
                camera_tree = [Camera.model_validate(c) for c in camera_tree_data]
            else:
                camera_tree = camera_tree_data
            
            if 'shot_descriptions' not in task.artifacts:
                shot_descriptions = load_shot_descriptions(task)
                if not shot_descriptions:
                    raise ValueError("Shot descriptions not found. Run decompose_visual_descriptions first.")
                # Save to artifacts for later use
                task.artifacts['shot_descriptions'] = [s.model_dump() for s in shot_descriptions]
            else:
                # Convert from dicts if needed
                shot_descriptions_data = task.artifacts['shot_descriptions']
                if shot_descriptions_data and isinstance(shot_descriptions_data[0], dict):
                    shot_descriptions = [ShotDescription.model_validate(s) for s in shot_descriptions_data]
                else:
                    shot_descriptions = shot_descriptions_data
            
            # Load characters
            if 'characters' not in task.artifacts:
                chars_path = os.path.join(task.work_dir, 'characters.json')
                gen_logger.info(task_id, step.value, f"Waiting for characters file (max 30 seconds)...")
                # Wait for file and load characters
                if wait_for_file(chars_path, max_retries=30, retry_interval=1.0):
                    try:
                        characters = load_characters_from_file(chars_path)
                        task.artifacts['characters'] = [c.model_dump() for c in characters]
                    except Exception as e:
                        raise ValueError(f"Failed to load characters: {e}")
                else:
                    raise ValueError("Characters not found. Run extract_characters first.")
            else:
                chars_data = task.artifacts['characters']
                if chars_data and isinstance(chars_data[0], dict):
                    characters = [CharacterInScene.model_validate(c) for c in chars_data]
                else:
                    characters = chars_data
            
            gen_logger.info(task_id, step.value, f"Characters loaded: {[(c.identifier_in_scene, c.idx) for c in characters]}")
            
            # Load character portraits registry
            registry_path = os.path.join(task.work_dir, 'character_portraits_registry.json')
            gen_logger.info(task_id, step.value, f"Waiting for character portraits registry file (max 30 seconds)...")
            character_portraits_registry = wait_for_file_and_load_json(registry_path, max_retries=30, retry_interval=1.0)
            if character_portraits_registry:
                task.artifacts['character_portraits_registry'] = character_portraits_registry
            else:
                raise ValueError("Character portraits not found. Run generate_character_portraits first.")
            
            # Get or create Script2VideoPipeline
            script2video = get_script2video_pipeline(task, pipeline)
            
            # Generate frames for each camera
            camera_tree_data = task.artifacts['camera_tree']
            camera_tree = [Camera.model_validate(c) for c in camera_tree_data]
            shot_descriptions_data = task.artifacts['shot_descriptions']
            shot_descriptions = [ShotDescription.model_validate(s) for s in shot_descriptions_data]
            character_portraits_registry = task.artifacts['character_portraits_registry']
            
            gen_logger.info(task_id, step.value, f"Camera tree: {len(camera_tree)} cameras")
            gen_logger.info(task_id, step.value, f"Shot descriptions: {len(shot_descriptions)} shots")
            gen_logger.info(task_id, step.value, f"Characters: {len(characters)} characters")
            gen_logger.info(task_id, step.value, f"Character portraits registry keys: {list(character_portraits_registry.keys())}")
            
            # Log shot details
            for sd in shot_descriptions[:3]:
                ff_vis = getattr(sd, 'ff_vis_char_idxs', None)
                gen_logger.info(task_id, step.value, f"  Shot {sd.idx}: ff_vis_char_idxs={ff_vis}, ff_desc={getattr(sd, 'ff_desc', None)[:50] if getattr(sd, 'ff_desc', None) else None}...")
            
            # Check if frames already exist
            shots_dir = os.path.join(script2video.working_dir, 'shots')
            gen_logger.info(task_id, step.value, f"Checking shots directory: {shots_dir}")
            
            existing_frames = 0
            for shot_desc in shot_descriptions:
                shot_dir = os.path.join(shots_dir, str(shot_desc.idx))
                first_frame = os.path.join(shot_dir, 'first_frame.png')
                last_frame = os.path.join(shot_dir, 'last_frame.png')
                if os.path.exists(first_frame):
                    existing_frames += 1
                    gen_logger.info(task_id, step.value, f"Shot {shot_desc.idx}: first_frame already exists")
                if os.path.exists(last_frame):
                    gen_logger.info(task_id, step.value, f"Shot {shot_desc.idx}: last_frame already exists")
            
            gen_logger.info(task_id, step.value, f"Found {existing_frames} existing frames")
            
            # This step is complex and may need to be implemented differently
            # For now, we'll run the frame generation for all cameras
            gen_logger.info(task_id, step.value, f"Generating frames for all cameras", cameras=len(camera_tree))
            for i, camera in enumerate(camera_tree):
                gen_logger.info(task_id, step.value, f"[Camera {i+1}/{len(camera_tree)}] Starting frame generation for camera {camera.idx}")
                try:
                    # Add timeout to prevent hanging (300 seconds = 5 minutes per camera)
                    print(f"[api_v1] Calling generate_frames_for_single_camera for camera {camera.idx}")
                    awaitable = script2video.generate_frames_for_single_camera(
                        camera=camera,
                        shot_descriptions=shot_descriptions,
                        characters=characters,
                        character_portraits_registry=character_portraits_registry,
                        priority_shot_idxs=[c.parent_cam_idx for c in camera_tree if c.parent_cam_idx is not None]
                    )
                    loop.run_until_complete(asyncio.wait_for(awaitable, timeout=300))
                except asyncio.TimeoutError:
                    error_msg = f"Frame generation for camera {camera.idx} timed out after 300 seconds"
                    gen_logger.step_failed(task_id, step.value, error_msg)
                    raise TimeoutError(error_msg)
                except Exception as e:
                    import traceback
                    error_msg = f"Frame generation for camera {camera.idx} failed: {str(e)}"
                    gen_logger.error(task_id, step.value, error_msg)
                    gen_logger.error(task_id, step.value, f"Traceback: {traceback.format_exc()}")
                    raise
                gen_logger.info(task_id, step.value, f"[Camera {i+1}/{len(camera_tree)}] Frame generation completed")
            
            # Verify frames were generated
            gen_logger.info(task_id, step.value, "Verifying generated frames...")
            for shot_desc in shot_descriptions:
                shot_dir = os.path.join(shots_dir, str(shot_desc.idx))
                first_frame = os.path.join(shot_dir, 'first_frame.png')
                last_frame = os.path.join(shot_dir, 'last_frame.png')
                gen_logger.info(task_id, step.value, 
                    f"Shot {shot_desc.idx}: first_frame={os.path.exists(first_frame)}, last_frame={os.path.exists(last_frame)}")
            
            gen_logger.step_completed(task_id, step.value, cameras_count=len(camera_tree))
            gen_logger.info(task_id, step.value, "========== GENERATE_FRAMES STEP COMPLETED ==========")
            
        elif step == Step.GENERATE_VIDEOS:
            gen_logger.info(task_id, step.value, "========== STARTING GENERATE_VIDEOS STEP ==========")
            # Generate individual shot videos - requires frames
            if 'shot_descriptions' not in task.artifacts:
                shot_descriptions = load_shot_descriptions(task)
                if not shot_descriptions:
                    gen_logger.step_failed(task_id, step.value, "Shot descriptions not found")
                    raise ValueError("Shot descriptions not found. Run decompose_visual_descriptions first.")
            else:
                # Convert from dicts if needed
                shot_descriptions_data = task.artifacts['shot_descriptions']
                if shot_descriptions_data and isinstance(shot_descriptions_data[0], dict):
                    shot_descriptions = [ShotDescription.model_validate(s) for s in shot_descriptions_data]
                else:
                    shot_descriptions = shot_descriptions_data
            
            gen_logger.info(task_id, step.value, f"Loaded {len(shot_descriptions)} shot descriptions")
            
            # Get or create Script2VideoPipeline
            gen_logger.info(task_id, step.value, "Getting Script2VideoPipeline")
            script2video = get_script2video_pipeline(task, pipeline)
            gen_logger.info(task_id, step.value, f"Script2VideoPipeline working_dir: {script2video.working_dir}")
            
            video_paths = []
            
            # Generate video for each shot
            gen_logger.info(task_id, step.value, f"Starting video generation for {len(shot_descriptions)} shots")
            
            # Check if frame files exist first
            shots_dir = os.path.join(script2video.working_dir, 'shots')
            gen_logger.info(task_id, step.value, f"Checking shots directory: {shots_dir}")
            
            # Check if shots directory exists
            if not os.path.exists(shots_dir):
                gen_logger.error(task_id, step.value, f"Shots directory does not exist: {shots_dir}")
                raise ValueError(f"Shots directory does not exist: {shots_dir}")
            
            for i, shot_description in enumerate(shot_descriptions):
                shot_dir = os.path.join(shots_dir, str(shot_description.idx))
                first_frame = os.path.join(shot_dir, 'first_frame.png')
                last_frame = os.path.join(shot_dir, 'last_frame.png')
                video_path = os.path.join(shot_dir, 'video.mp4')
                
                gen_logger.info(task_id, step.value, 
                    f"[Shot {i+1}/{len(shot_descriptions)}] idx={shot_description.idx}, "
                    f"shot_dir={shot_dir}, exists={os.path.exists(shot_dir)}, "
                    f"first_frame exists={os.path.exists(first_frame)}, "
                    f"last_frame exists={os.path.exists(last_frame)}, "
                    f"video exists={os.path.exists(video_path)}")
                
                gen_logger.info(task_id, step.value, f"[Shot {i+1}] Calling generate_video_for_single_shot...")
                try:
                    video_path = loop.run_until_complete(script2video.generate_video_for_single_shot(shot_description))
                    if video_path is None:
                        raise ValueError(f"Failed to generate video for shot {shot_description.idx}")
                    gen_logger.info(task_id, step.value, f"[Shot {i+1}] Generated video: {video_path}")
                    video_paths.append(video_path)
                except Exception as video_err:
                    import traceback
                    gen_logger.error(task_id, step.value, f"[Shot {i+1}] Video generation failed: {str(video_err)}")
                    gen_logger.error(task_id, step.value, f"Traceback: {traceback.format_exc()}")
                    raise
            
            gen_logger.info(task_id, step.value, f"All videos generated: {video_paths}")
            
            task.artifacts['video_paths'] = video_paths
            gen_logger.log_artifact_updated(task_id, step.value, 'video_paths', count=len(video_paths))
            gen_logger.step_completed(task_id, step.value, videos_count=len(video_paths))
            gen_logger.info(task_id, step.value, "========== GENERATE_VIDEOS STEP COMPLETED ==========")
            
        elif step == Step.CONCATENATE_VIDEOS:
            gen_logger.info(task_id, step.value, "Concatenating videos")
            # Concatenate videos - requires individual shot videos
            if 'video_paths' not in task.artifacts:
                # Try to find video files in multiple possible locations
                possible_shots_dirs = [
                    os.path.join(task.work_dir, 'shots'),
                    task.scene_working_dir,
                    os.path.join(task.work_dir, 'scene_0', 'shots'),
                ]
                
                video_paths = []
                found_shots_dir = None
                
                for shots_dir in possible_shots_dirs:
                    if shots_dir and os.path.exists(shots_dir):
                        gen_logger.info(task_id, step.value, f"Checking shots directory: {shots_dir}")
                        found_shots_dir = shots_dir
                        # List all shot directories - handle both "shot_X" and just "X" formats
                        try:
                            all_entries = os.listdir(shots_dir)
                            shot_dirs = []
                            for d in all_entries:
                                shot_path = os.path.join(shots_dir, d)
                                if os.path.isdir(shot_path):
                                    # Accept directories named "shot_X" or just "X" (numeric)
                                    if d.startswith('shot_') or d.isdigit():
                                        shot_dirs.append(d)
                            
                            shot_dirs.sort(key=lambda x: int(x.replace('shot_', '')) if x.isdigit() else int(x.replace('shot_', '')))
                            gen_logger.info(task_id, step.value, f"Found shot directories: {shot_dirs}")
                            
                            for shot_idx_str in shot_dirs:
                                video_path = os.path.join(shots_dir, shot_idx_str, 'video.mp4')
                                if os.path.exists(video_path):
                                    video_paths.append(video_path)
                                    gen_logger.info(task_id, step.value, f"Found video: {video_path}")
                        except Exception as e:
                            gen_logger.error(task_id, step.value, f"Error listing shots dir: {e}")
                        break
                
                if not video_paths:
                    gen_logger.error(task_id, step.value, f"No video files found in any of: {possible_shots_dirs}")
                    raise ValueError("Video files not found. Run generate_videos first.")
                
                gen_logger.info(task_id, step.value, f"Found {len(video_paths)} video files")
                task.artifacts['video_paths'] = video_paths
            
            # Get or create Script2VideoPipeline
            script2video = get_script2video_pipeline(task, pipeline)
            
            # Concatenate videos
            video_paths = task.artifacts['video_paths']
            final_video_path = os.path.join(task.work_dir, 'final_video.mp4')
            
            # Validate video files
            for vpath in video_paths:
                if vpath is None:
                    raise ValueError(f"Video path is None")
                if not os.path.exists(vpath):
                    raise ValueError(f"Video file not found: {vpath}")
                if os.path.getsize(vpath) == 0:
                    raise ValueError(f"Video file is empty: {vpath}")
            
            # Import moviepy here to avoid dependency issues
            from moviepy import VideoFileClip, concatenate_videoclips
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
            
            video_clips = [VideoFileClip(video_path) for video_path in video_paths]
            final_video = concatenate_videoclips(video_clips)
            
            # Write video with timeout (60 seconds)
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(final_video.write_videofile, final_video_path, codec="libx264", preset="medium")
                try:
                    future.result(timeout=60)
                except FuturesTimeoutError:
                    raise TimeoutError(f"Video writing timed out after 60 seconds for {final_video_path}")
            
            task.artifacts['final_video'] = final_video_path
            
            # # 保存封面图片 - 从第一个镜头的 first_frame.png 复制
            # try:
            #     # 找到第一个镜头的 first_frame.png
            #     first_shot_dir = os.path.join(os.path.dirname(video_paths[0]), '0')
            #     first_frame_path = os.path.join(first_shot_dir, 'first_frame.png')
            #     cover_path = final_video_path.replace('.mp4', '_cover.png')
            #
            #     if os.path.exists(first_frame_path):
            #         import shutil
            #         shutil.copy(first_frame_path, cover_path)
            #         print(f"[STEP EXECUTION] Cover image saved: {cover_path}")
            #     else:
            #         print(f"[STEP EXECUTION] Warning: First frame not found at {first_frame_path}")
            # except Exception as cover_e:
            #     print(f"[STEP EXECUTION] Warning: Failed to save cover image: {cover_e}")

            # 从视频中提取第一帧作为封面
            if final_video_path.endswith('.mp4'):
                cover_path = final_video_path.replace('.mp4', '_cover.png')
                try:
                    from moviepy import VideoFileClip
                    clip = VideoFileClip(final_video_path)
                    clip.save_frame(cover_path, t=0)
                    clip.close()
                    print(f"Cover extracted successfully to {cover_path}")
                except Exception as cover_e:
                    print(f"Failed to extract cover: {cover_e}")
            
            # 记录最终视频信息
            gen_logger.log_file_saved(task_id, step.value, final_video_path)
            gen_logger.log_artifact_updated(task_id, step.value, 'final_video')
            gen_logger.task_completed(task_id, final_video=final_video_path)
            print(f"[STEP EXECUTION] Final video created: {final_video_path}")
            
        else:
            # Steps that require Script2VideoPipeline
            # For now, we'll implement these later
            raise NotImplementedError(f"Step {step.value} not implemented yet")
        
        # Update progress based on step completion
        step_progress = {
            Step.DEVELOP_STORY: 10,
            Step.EXTRACT_CHARACTERS: 20,
            Step.GENERATE_CHARACTER_PORTRAITS: 30,
            Step.WRITE_SCRIPT: 40,
            Step.DESIGN_STORYBOARD: 50,
            Step.DECOMPOSE_VISUAL_DESCRIPTIONS: 60,
            Step.CONSTRUCT_CAMERA_TREE: 70,
            Step.GENERATE_FRAMES: 80,
            Step.GENERATE_VIDEOS: 90,
            Step.CONCATENATE_VIDEOS: 100
        }
        
        # Update task status: if this is the final step, mark as COMPLETED, otherwise keep as RUNNING
        if step == Step.CONCATENATE_VIDEOS:
            new_status = TaskStatus.COMPLETED
        else:
            new_status = TaskStatus.RUNNING
        
        progress_value = step_progress.get(step, 0)
        print(f"[STEP EXECUTION DEBUG] Updating task status for step '{step.value}': status={new_status}, progress={progress_value}")
        print(f"[STEP EXECUTION DEBUG] Step enum: {step}, type: {type(step)}")
        print(f"[STEP EXECUTION DEBUG] Step progress dict keys: {list(step_progress.keys())}")
        print(f"[STEP EXECUTION DEBUG] Step in dict: {step in step_progress}")
        
        task_manager.update_task_status(
            task_id,
            new_status,
            current_step=step,
            progress=progress_value
        )
        
        # 计算步骤耗时
        step_duration = int((time.time() - step_start_time) * 1000)
        gen_logger.step_completed(task_id, step.value, duration_ms=step_duration, progress=progress_value)
        gen_logger.info(task_id, step.value, f"步骤完成，耗时: {step_duration}ms", duration_ms=step_duration)
        print(f"[STEP EXECUTION] Step '{step.value}' completed successfully! Progress: {progress_value}%")
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        # 记录错误日志
        gen_logger.step_failed(task_id, step.value, error_msg)
        gen_logger.error(task_id, step.value, f"步骤执行失败: {error_msg}")
        
        print(f"[STEP EXECUTION] ERROR in step '{step.value}': {error_msg}")
        print(f"[STEP EXECUTION] Traceback:\n{error_traceback}")
        
        # Update task status to FAILED
        update_success = task_manager.update_task_status(
            task_id,
            TaskStatus.FAILED,
            current_step=step,
            error=error_msg
        )
        print(f"[STEP EXECUTION] Task status update to FAILED: {'success' if update_success else 'FAILED'}")
        if not update_success:
            # Emergency fallback: try to directly write to task file
            try:
                task = task_manager.get_task(task_id)
                if task:
                    task.status = TaskStatus.FAILED
                    task.error = error_msg
                    task_manager._save_task_to_disk(task)
                    print(f"[STEP EXECUTION] Emergency save succeeded")
            except Exception as fallback_e:
                print(f"[STEP EXECUTION] Emergency save failed: {fallback_e}")
        
        # 记录任务失败
        gen_logger.task_failed(task_id, error_msg)

# Swagger/OpenAPI documentation
@api_v1.route('/swagger.json')
def swagger_json():
    """Return OpenAPI specification."""
    swagger_spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "OpenShortVideo API",
            "description": "API for video generation from ideas. Supports both one-click and stepwise generation.",
            "version": "1.0.0"
        },
        "servers": [
            {
                "url": "http://localhost:5001/api/v1",
                "description": "Local development server"
            }
        ],
        "paths": {
            "/tasks": {
                "post": {
                    "summary": "Create a new video generation task",
                    "description": "Create a new task for video generation. Returns task ID and work directory.",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "idea": {"type": "string", "description": "Story idea text"},
                                        "user_requirement": {"type": "string", "description": "Requirements text"},
                                        "style": {"type": "string", "description": "Style description"},
                                        "mode": {"type": "string", "enum": ["full", "stepwise"], "default": "full"},
                                        "work_dir": {"type": "string", "description": "Optional custom work directory"}
                                    },
                                    "required": ["idea"]
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "description": "Task created successfully",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "task_id": {"type": "string"},
                                            "work_dir": {"type": "string"},
                                            "mode": {"type": "string"},
                                            "status": {"type": "string"},
                                            "created_at": {"type": "string", "format": "date-time"}
                                        }
                                    }
                                }
                            }
                        },
                        "400": {"description": "Invalid request"}
                    }
                }
            },
            "/tasks/{task_id}": {
                "get": {
                    "summary": "Get task status and progress",
                    "description": "Retrieve the current status and progress of a task.",
                    "parameters": [
                        {
                            "name": "task_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Task details",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "task_id": {"type": "string"},
                                            "work_dir": {"type": "string"},
                                            "status": {"type": "string"},
                                            "current_step": {"type": "string"},
                                            "progress": {"type": "number"},
                                            "created_at": {"type": "string", "format": "date-time"}
                                        }
                                    }
                                }
                            }
                        },
                        "404": {"description": "Task not found"}
                    }
                }
            },
            "/tasks/{task_id}/steps/{step_name}": {
                "post": {
                    "summary": "Execute a specific step",
                    "description": "Execute a specific step for stepwise generation.",
                    "parameters": [
                        {
                            "name": "task_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"}
                        },
                        {
                            "name": "step_name",
                            "in": "path",
                            "required": True,
                            "schema": {
                                "type": "string",
                                "enum": ["develop_story", "extract_characters", "generate_character_portraits", "write_script", "design_storyboard", "decompose_visual_descriptions", "construct_camera_tree", "generate_frames", "generate_videos", "concatenate_videos"]
                            }
                        }
                    ],
                    "responses": {
                        "202": {
                            "description": "Step execution started",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "task_id": {"type": "string"},
                                            "step": {"type": "string"},
                                            "status": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        },
                        "404": {"description": "Task not found"},
                        "409": {"description": "Task not in stepwise mode or invalid state"}
                    }
                }
            },
            "/tasks/{task_id}/artifacts": {
                "get": {
                    "summary": "List available artifacts",
                    "description": "List all generated artifacts for a task.",
                    "parameters": [
                        {
                            "name": "task_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "List of artifacts",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "artifacts": {
                                                "type": "object",
                                                "additionalProperties": {
                                                    "type": "object",
                                                    "properties": {
                                                        "path": {"type": "string"},
                                                        "size": {"type": "integer"},
                                                        "modified": {"type": "string", "format": "date-time"}
                                                    }
                                                }
                                            },
                                            "all_files": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "name": {"type": "string"},
                                                        "path": {"type": "string"},
                                                        "size": {"type": "integer"},
                                                        "type": {"type": "string"}
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "404": {"description": "Task not found"}
                    }
                }
            },
            "/tasks/{task_id}/cancel": {
                "post": {
                    "summary": "Cancel a running task",
                    "description": "Cancel a task that is pending or running.",
                    "parameters": [
                        {
                            "name": "task_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Task cancelled",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "task_id": {"type": "string"},
                                            "status": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        },
                        "404": {"description": "Task not found"},
                        "409": {"description": "Task cannot be cancelled"}
                    }
                }
            },
            "/tasks/{task_id}/artifacts/{file_path}": {
                "get": {
                    "summary": "Get artifact content or metadata",
                    "description": "Retrieve the content or metadata of a specific artifact. Use ?content=true to get file content for text files.",
                    "parameters": [
                        {
                            "name": "task_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"}
                        },
                        {
                            "name": "file_path",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"}
                        },
                        {
                            "name": "content",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "string",
                                "enum": ["true", "false"],
                                "default": "false"
                            },
                            "description": "Set to 'true' to return file content instead of metadata"
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Artifact metadata or content",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "oneOf": [
                                            {
                                                "type": "object",
                                                "properties": {
                                                    "path": {"type": "string"},
                                                    "size": {"type": "integer"},
                                                    "modified": {"type": "string", "format": "date-time"},
                                                    "type": {"type": "string"}
                                                }
                                            },
                                            {
                                                "type": "object",
                                                "properties": {
                                                    "content": {"type": "string"},
                                                    "type": {"type": "string"}
                                                }
                                            },
                                            {
                                                "type": "object",
                                                "properties": {
                                                    "type": {"type": "string"},
                                                    "path": {"type": "string"},
                                                    "size": {"type": "integer"}
                                                }
                                            }
                                        ]
                                    }
                                }
                            }
                        },
                        "404": {"description": "Task or artifact not found"}
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "Task": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "work_dir": {"type": "string"},
                        "idea": {"type": "string"},
                        "user_requirement": {"type": "string"},
                        "style": {"type": "string"},
                        "mode": {"type": "string"},
                        "status": {"type": "string"},
                        "current_step": {"type": "string"},
                        "progress": {"type": "number"},
                        "created_at": {"type": "string", "format": "date-time"},
                        "started_at": {"type": "string", "format": "date-time"},
                        "completed_at": {"type": "string", "format": "date-time"},
                        "error": {"type": "string"}
                    }
                }
            }
        }
    }
    return jsonify(swagger_spec)

@api_v1.route('/docs')
def swagger_ui():
    """Swagger UI documentation."""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>OpenShortVideo API Documentation</title>
        <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@3/swagger-ui.css">
        <style>
            body { margin: 0; padding: 0; }
            #swagger-ui { padding: 20px; }
        </style>
    </head>
    <body>
        <div id="swagger-ui"></div>
        <script src="https://unpkg.com/swagger-ui-dist@3/swagger-ui-bundle.js"></script>
        <script>
            window.onload = function() {
                const ui = SwaggerUIBundle({
                    url: '/api/v1/swagger.json',
                    dom_id: '#swagger-ui',
                    presets: [
                        SwaggerUIBundle.presets.apis,
                        SwaggerUIBundle.SwaggerUIStandalonePreset
                    ],
                    layout: "BaseLayout"
                });
            };
        </script>
    </body>
    </html>
    '''

# Error handlers
@api_v1.errorhandler(BadRequest)
def handle_bad_request(error):
    return jsonify({'error': str(error.description)}), 400

@api_v1.errorhandler(NotFound)
def handle_not_found(error):
    return jsonify({'error': str(error.description)}), 404

@api_v1.errorhandler(Conflict)
def handle_conflict(error):
    return jsonify({'error': str(error.description)}), 409

@api_v1.errorhandler(Exception)
def handle_generic_error(error):
    return jsonify({'error': 'Internal server error'}), 500


# 一键生成实时推送接口
@api_v1.route('/generate/stream', methods=['POST'])
def generate_video_stream():
    """
    一键生成视频接口 (SSE实时推送版本)
    
    Request body:
    {
        "idea": "故事创意",
        "user_requirement": "用户需求",
        "style": "风格描述",
        "work_dir": "可选的工作目录"
    }
    
    返回: Server-Sent Events 流
    - log: 实时日志
    - progress: 任务进度
    - files: 文件变化
    - status: 任务状态
    """


    
    data = request.get_json()
    if not data:
        raise BadRequest("JSON body required")
    
    idea = data.get('idea', '').strip()
    if not idea:
        raise BadRequest("idea is required")
    
    user_requirement = data.get('user_requirement', '').strip()
    style = data.get('style', '').strip()
    work_dir = data.get('work_dir')
    episode_id = data.get('episode_id')  # 添加 episode_id 参数
    
    # 在启动线程前保存 request.host_url
    api_host = request.host_url.rstrip('/') if request.host_url else 'http://192.168.2.15:5001'

    # 添加详细日志
    import logging
    logger = logging.getLogger(__name__)
    logger.info("========== 一键生成请求 ==========")
    logger.info(f"Request JSON data: {data}")
    logger.info(f"idea: {idea}")
    logger.info(f"user_requirement: {user_requirement}")
    logger.info(f"style: {style}")
    logger.info(f"work_dir: {work_dir}")
    logger.info(f"episode_id: {episode_id}")
    logger.info("===================================")

    # 创建工作目录 - 使用generation_shortvideo作为基础目录
    if work_dir is None:
        work_dir = os.path.join("generation_shortvideo", str(uuid.uuid4()))
    else:
        if not work_dir.startswith('generation_shortvideo'):
            work_dir = os.path.join('generation_shortvideo', work_dir)
    
    logger.info(f"最终工作目录: {work_dir}")
    
    os.makedirs(work_dir, exist_ok=True)
    
    # 创建任务
    task = task_manager.create_task(
        idea=idea,
        user_requirement=user_requirement,
        style=style,
        mode="full",
        work_dir=work_dir
    )
    
    logger.info(f"任务创建成功! task_id: {task.task_id}")
    
    # 初始化日志队列
    log_queue = queue.Queue()
    
    # 记录初始文件状态
    initial_files = _get_directory_tree(work_dir)
    logger.info(f"初始文件列表: {initial_files}")
    
    def generate():
        import threading
        
        # 用于跟踪已推送的文件
        last_file_state = initial_files.copy()
        start_time = time.time()
        step_timestamps = {
            'start': start_time,
        }
        
        # 推送初始信息
        yield f"data: {json.dumps({'type': 'init', 'task_id': task.task_id, 'work_dir': work_dir})}\n\n"
        yield f"data: {json.dumps({'type': 'status', 'status': 'starting', 'progress': 0})}\n\n"
        
        # 在后台线程中运行管道
        def run_pipeline():
            try:
                task_manager.update_task_status(task.task_id, TaskStatus.RUNNING, progress=0.0)
                
                # 记录开始时间
                step_timestamps['pipeline_start'] = time.time()
                
                # 初始化管道
                pipeline = Idea2VideoPipeline.init_from_config(
                    config_path="configs/idea2video_deepseek_veo3_fast.yaml",
                    working_dir=work_dir
                )
                
                # 记录日志函数
                def log_callback(message):
                    log_queue.put({'type': 'log', 'message': message, 'timestamp': time.time()})
                
                # 更新进度回调
                def progress_callback(step, progress):
                    log_queue.put({'type': 'progress', 'step': step, 'progress': progress})
                
                # 运行管道 (简化的同步调用)
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    # 发送初始日志
                    log_callback(f"[VIDEO] 开始生成视频...")
                    log_callback(f"[IDEA] 创意: {idea[:50]}...")
                    log_callback(f"[DIR] 工作目录: {work_dir}")
                    
                    # 运行管道
                    loop.run_until_complete(pipeline(
                        idea=idea,
                        user_requirement=user_requirement,
                        style=style
                    ))
                    
                    log_callback("[SUCCESS] 视频生成完成!")
                    task_manager.update_task_status(task.task_id, TaskStatus.COMPLETED, progress=100.0)
                    
                    # 更新前端数据库中的 video_url
                    log_callback(f"[DATABASE] episode_id received: {episode_id}")
                    log_callback(f"[DATABASE] work_dir: {work_dir}")
                    
                    if episode_id:
                        try:
                            import sqlite3
                            
                            # 直接使用 sqlite3
                            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend', 'instance', 'short_video.db')
                            log_callback(f"[DATABASE] Connecting to: {db_path}")
                            
                            conn = sqlite3.connect(db_path)
                            cursor = conn.cursor()
                            
                            # 查询 episode
                            cursor.execute("SELECT id, title, video_url FROM episodes WHERE id = ?", (episode_id,))
                            episode_row = cursor.fetchone()
                            log_callback(f"[DATABASE] Query result: {episode_row}")
                            
                            if episode_row:
                                # 使用已保存的 api_host
                                log_callback(f"[DATABASE] Using api_host: {api_host}")
                                # 解析 work_dir
                                work_dir_relative = work_dir.replace('generation_shortvideo/', '').replace('generation_shortvideo\\', '').replace('generation_shortvideo', '')
                                video_url = f'{api_host}/api/v1/generate/file?work_dir={work_dir_relative}&path=final_video.mp4'
                                
                                log_callback(f"[DATABASE] Setting video_url: {video_url}")
                                
                                # 更新数据库
                                from datetime import datetime
                                now = datetime.utcnow().isoformat()
                                cursor.execute("""
                                    UPDATE episodes 
                                    SET video_url = ?, generation_status = 'completed', status = 'ready', 
                                        generation_completed_at = ?, updated_at = ?
                                    WHERE id = ?
                                """, (video_url, now, now, episode_id))
                                conn.commit()
                                log_callback(f"[DATABASE] SUCCESS: Updated episode {episode_id}")
                            else:
                                log_callback(f"[DATABASE] Episode {episode_id} not found!")
                            
                            conn.close()
                        except Exception as db_error:
                            import traceback
                            log_callback(f"[DATABASE] ERROR: {db_error}")
                            log_callback(f"[DATABASE] Traceback: {traceback.format_exc()}")
                    
                finally:
                    loop.close()
                    
            except Exception as e:
                import traceback
                error_msg = f"[ERROR] 错误: {str(e)}"
                log_callback(error_msg)
                log_callback(f"详情: {traceback.format_exc()}")
                task_manager.update_task_status(
                    task.task_id, 
                    TaskStatus.FAILED, 
                    error=str(e)
                )
        
        # 启动后台线程
        thread = threading.Thread(target=run_pipeline)
        thread.daemon = True
        thread.start()
        
        # 轮询队列并推送更新
        current_progress = 0
        consecutive_empty = 0
        max_empty_iterations = 30  # 30次空队列后检查线程状态
        
        while True:
            try:
                # 检查是否有新日志/进度
                found_update = False
                
                while not log_queue.empty():
                    found_update = True
                    item = log_queue.get_nowait()
                    
                    if item['type'] == 'log':
                        yield f"data: {json.dumps({'type': 'log', 'message': item['message'], 'timestamp': item['timestamp']})}\n\n"
                        logger.info(f"[SSE LOG] {item['message']}")
                    elif item['type'] == 'progress':
                        current_progress = item['progress']
                        progress_msg = {'type': 'progress', 'step': item.get('step', ''), 'progress': item['progress']}
                        yield f"data: {json.dumps(progress_msg)}\n\n"
                        logger.info(f"[SSE PROGRESS] step={item.get('step', '')}, progress={item['progress']}")
                
                # 检查文件变化
                current_files = _get_directory_tree(work_dir)
                if current_files != last_file_state:
                    found_update = True
                    new_files = _find_new_files(last_file_state, current_files)
                    last_file_state = current_files
                    yield f"data: {json.dumps({'type': 'files', 'files': new_files, 'all_files': current_files})}\n\n"
                
                # 获取任务状态
                task_obj = task_manager.get_task(task.task_id)
                if task_obj:
                    status = task_obj.status.value if hasattr(task_obj.status, 'value') else task_obj.status
                    if status in ['completed', 'failed', 'cancelled']:
                        yield f"data: {json.dumps({'type': 'status', 'status': status, 'progress': task_obj.progress})}\n\n"
                        break
                    
                    # 更新进度
                    if task_obj.progress > current_progress:
                        current_progress = task_obj.progress
                        yield f"data: {json.dumps({'type': 'progress', 'step': task_obj.current_step, 'progress': task_obj.progress})}\n\n"
                
                if not found_update:
                    consecutive_empty += 1
                else:
                    consecutive_empty = 0
                
                # 如果连续多次空队列且线程已结束，退出
                if consecutive_empty >= max_empty_iterations and not thread.is_alive():
                    task_obj = task_manager.get_task(task.task_id)
                    if task_obj:
                        status = task_obj.status.value if hasattr(task_obj.status, 'value') else task_obj.status
                        if status == 'running':
                            # 线程可能异常退出
                            task_manager.update_task_status(task.task_id, TaskStatus.FAILED, error="Pipeline thread ended unexpectedly")
                            yield f"data: {json.dumps({'type': 'status', 'status': 'failed', 'error': 'Pipeline thread ended unexpectedly'})}\n\n"
                            break
                
                time.sleep(0.5)
                
            except GeneratorExit:
                break
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                break
        
        # 发送最终文件列表
        final_files = _get_directory_tree(work_dir)
        logger.info(f"[SSE FINAL] 最终文件列表: {final_files}")
        yield f"data: {json.dumps({'type': 'final', 'work_dir': work_dir, 'files': final_files})}\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Access-Control-Allow-Origin': '*'
        }
    )


def _get_directory_tree(directory, max_depth=3, current_depth=0):
    """获取目录树结构"""
    result = {}
    
    if current_depth >= max_depth:
        return result
    
    try:
        path = Path(directory)
        if not path.exists():
            return result
        
        for item in path.iterdir():
            if item.is_file():
                try:
                    result[item.name] = {
                        'path': str(item.relative_to(path.parent)),
                        'size': item.stat().st_size,
                        'modified': item.stat().st_mtime
                    }
                except:
                    pass
            elif item.is_dir():
                # 跳过一些系统目录
                if item.name.startswith('.') or item.name in ['__pycache__', 'node_modules']:
                    continue
                result[item.name] = {
                    'type': 'directory',
                    'children': _get_directory_tree(str(item), max_depth, current_depth + 1)
                }
    except:
        pass
    
    return result


def _find_new_files(old_state, new_state):
    """找出新增的文件"""
    new_files = []
    
    for name, info in new_state.items():
        if name not in old_state:
            new_files.append({'name': name, 'info': info})
        elif info.get('type') == 'directory' and 'children' in info:
            # 检查子目录中的新文件
            if name in old_state and 'children' in old_state[name]:
                children_new = _find_new_files(old_state[name].get('children', {}), info.get('children', {}))
                for child in children_new:
                    new_files.append({'name': f"{name}/{child['name']}", 'info': child['info']})
    
    return new_files


@api_v1.route('/generate/status/<task_id>', methods=['GET'])
def get_generate_status(task_id):
    """获取一键生成任务状态"""
    task = task_manager.get_task(task_id)
    if not task:
        raise NotFound(f"Task {task_id} not found")
    
    # 获取文件列表
    files = _get_directory_tree(task.work_dir)
    
    return jsonify({
        'task_id': task.task_id,
        'status': task.status.value if hasattr(task.status, 'value') else task.status,
        'progress': task.progress,
        'current_step': task.current_step.value if task.current_step and hasattr(task.current_step, 'value') else task.current_step,
        'work_dir': task.work_dir,
        'files': files,
        'error': task.error
    })


@api_v1.route('/generate/files', methods=['GET'])
def get_generate_files():
    """通过work_dir获取生成的文件列表和内容"""
    work_dir = request.args.get('work_dir', '')
    path = request.args.get('path', '')
    content = request.args.get('content', 'false').lower() == 'true'
    
    if not work_dir:
        return jsonify({'error': 'work_dir is required'}), 400
    
    # 处理路径
    if work_dir.startswith('generation_shortvideo/'):
        # 已经是完整路径
        full_dir = work_dir
    else:
        full_dir = f"generation_shortvideo/{work_dir}"
    
    # 如果指定了具体文件路径
    if path:
        full_path = os.path.join(full_dir, path)
        if not os.path.exists(full_path):
            raise NotFound(f"File {path} not found")
        
        if content:
            # 返回文本内容
            if path.endswith(('.txt', '.json', '.yaml', '.yml', '.py', '.js', '.css', '.html')):
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                    return jsonify({
                        'path': path,
                        'content': file_content,
                        'type': 'text'
                    })
                except Exception as e:
                    return jsonify({'error': f'Failed to read file: {str(e)}'}), 500
        
        # 返回文件信息
        file_size = os.path.getsize(full_path)
        return jsonify({
            'path': path,
            'size': file_size,
            'type': 'file'
        })
    
    # 返回目录文件树
    if not os.path.exists(full_dir):
        return jsonify({'error': f'Directory {full_dir} not found'}), 404
    
    files = _get_directory_tree(full_dir)
    return jsonify({
        'work_dir': work_dir,
        'full_path': full_dir,
        'files': files
    })


@api_v1.route('/generate/file', methods=['GET'])
def get_generate_file():
    """直接获取生成的文件内容（用于图片、视频等二进制文件）"""
    work_dir = request.args.get('work_dir', '')
    path = request.args.get('path', '')
    
    if not work_dir or not path:
        return jsonify({'error': 'work_dir and path are required'}), 400
    
    # 处理路径 - 统一使用正斜杠
    if work_dir.startswith('generation_shortvideo/'):
        full_dir = work_dir.replace('\\', '/')
    else:
        full_dir = f"generation_shortvideo/{work_dir}".replace('\\', '/')
    
    # 统一路径分隔符
    full_path = os.path.join(full_dir, path.replace('/', os.sep))
    # 标准化路径
    full_path = os.path.normpath(full_path)
    
    print(f"get_generate_file: work_dir={work_dir}, path={path}, full_path={full_path}")
    
    # 如果文件不存在，尝试搜索可能的目录
    if not os.path.exists(full_path):
        # 尝试在没有完整路径的情况下搜索
        base_dir = "generation_shortvideo"
        search_path = os.path.join(base_dir, path.replace('/', os.sep))
        search_path = os.path.normpath(search_path)
        
        # 列出目录内容帮助调试
        if os.path.exists(base_dir):
            print(f"get_generate_file: Searching in {base_dir}, looking for {path}")
            for root, dirs, files in os.walk(base_dir):
                if path.replace('/', os.sep).replace(os.sep, '/') in root.replace(os.sep, '/'):
                    potential_path = os.path.join(root, os.path.basename(path))
                    if os.path.exists(potential_path):
                        full_path = potential_path
                        print(f"get_generate_file: Found file at {full_path}")
                        break
    
    if not os.path.exists(full_path):
        return jsonify({'error': f'File not found: {full_path}'}), 404
    
    # 根据文件类型返回适当的Content-Type
    import mimetypes
    content_type, _ = mimetypes.guess_type(full_path)
    if not content_type:
        content_type = 'application/octet-stream'
    
    # 使用流式响应，避免大文件导致内存问题
    try:
        file_size = os.path.getsize(full_path)
        
        def generate():
            with open(full_path, 'rb') as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    yield chunk
        
        response = Response(generate(), content_type=content_type)
        response.headers['Content-Length'] = file_size
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Cache-Control'] = 'max-age=3600'
        response.headers['Accept-Ranges'] = 'bytes'
        response.headers['Content-Disposition'] = 'inline'
        return response
    except Exception as e:
        return jsonify({'error': f'Failed to read file: {str(e)}'}), 500