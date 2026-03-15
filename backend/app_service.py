import os
import json
import asyncio
import threading
import queue
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, Response, stream_with_context, abort, \
    send_file
from pathlib import Path
import sys
from database import get_db
import base64
from PIL import Image as PILImage
import io
from openai import OpenAI
import requests

# CORS支持
from flask_cors import CORS

# 导入您的视频生成管道
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipelines.idea2video_pipeline import Idea2VideoPipeline
from tools.wuyinkeji_nanoBanana_api import ImageGeneratorNanobananaWuYinAPI
from tools.wuyinkeji_veo3_veo3_fast_api import VideoGeneratorVeoFastAPI
import yaml

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB 最大文件上传

# 配置CORS，允许跨域请求
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# Register API v1 Blueprint
try:
    from api_v1 import api_v1
    app.register_blueprint(api_v1)
    print("Registered API v1 blueprint")
except ImportError as e:
    print(f"Failed to import API v1: {e}")

from utils.log_handler import setup_logging

# 全局变量
current_task = None
task_queue = queue.Queue()
log_queue = queue.Queue()
ad_progress_queues = {}
# 在创建应用后设置日志
setup_logging(log_queue)
working_dir = None
task_running = False

# 存储所有工作目录的状态
work_dirs = {}


# 初始化数据库
def init_database():
    """初始化数据库"""
    db = get_db()
    print("数据库初始化完成")
    # 可选：清理无效记录
    deleted = db.cleanup_invalid_records()
    if deleted > 0:
        print(f"清理了 {deleted} 条无效记录")

# 在应用启动时初始化
init_database()

# 日志捕获类
class LogCapture:
    def __init__(self, queue):
        self.queue = queue

    def write(self, text):
        if text.strip():  # 只记录非空行
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"[{timestamp}] {text}"
            self.queue.put(log_entry)
        # 仍然输出到控制台
        sys.__stdout__.write(text)

    def flush(self):
        sys.__stdout__.flush()


# 重定向标准输出
sys.stdout = LogCapture(log_queue)


def run_async_task(idea, user_requirement, style, work_dir, config_path="configs/idea2video_deepseek_veo3.yaml"):
    """在后台线程中运行异步任务"""
    global current_task, task_running, working_dir

    try:
        async def async_main():
            global current_task, working_dir
            working_dir = work_dir

            # 确保工作目录存在
            os.makedirs(work_dir, exist_ok=True)

            # 更新工作目录状态
            work_dirs[work_dir] = {
                'status': 'running',
                'start_time': datetime.now().isoformat(),
                'idea': idea,
                'user_requirement': user_requirement,
                'style': style
            }

            pipeline = Idea2VideoPipeline.init_from_config(
                config_path=config_path,
                working_dir=work_dir
            )
            await pipeline(idea=idea, user_requirement=user_requirement, style=style)

            # 更新完成状态
            work_dirs[work_dir]['status'] = 'completed'
            work_dirs[work_dir]['end_time'] = datetime.now().isoformat()
            work_dirs[work_dir]['final_video'] = os.path.join(work_dir, 'final_video.mp4')

            log_queue.put(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SUCCESS] 视频生成完成！")

        # 在新的事件循环中运行
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(async_main())

    except Exception as e:
        error_msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] 生成过程中出现错误: {str(e)}"
        log_queue.put(error_msg)
        if work_dir in work_dirs:
            work_dirs[work_dir]['status'] = 'failed'
            work_dirs[work_dir]['error'] = str(e)
    finally:
        task_running = False


@app.route('/')
def index():
    """主页面"""
    return render_template('index.html')


@app.route('/api_test')
def api_test():
    """API测试页面"""
    return render_template('api_test.html')


# =====================================图像生成========================================================================
def load_image_api_key_from_config(config_path="configs/idea2video_deepseek_veo3_fast.yaml"):
    """从配置文件加载图像生成API密钥"""
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config["image_generator"]["init_args"]["api_key"]


def load_video_api_key_from_config(config_path="configs/idea2video_deepseek_veo3_fast.yaml"):
    """从配置文件加载视频生成API密钥"""
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config["video_generator"]["init_args"]["api_key"]

def load_deepseek_api_key_from_config(config_path="configs/idea2video_deepseek_veo3_fast.yaml"):
    """从配置文件加载视频生成API密钥"""
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config["chat_model"]["init_args"]["api_key"]


async def generate_image_async(prompt, aspect_ratio="1:1"):
    """异步生成图像"""
    api_key = load_image_api_key_from_config()
    image_generator = ImageGeneratorNanobananaWuYinAPI(
        api_key=api_key,
        poll_interval=10,
        max_poll_attempts=60,
    )
    result = await image_generator.generate_single_image(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
    )
    return result.data


@app.route('/api/generate-image', methods=['POST'])
def generate_image():
    try:
        data = request.json
        prompt = data.get('prompt', '').replace('#图片生成', '').strip()
        aspect_ratio = data.get('aspect_ratio', '1:1')
        message_id = data.get('messageId', str(uuid.uuid4()))

        if not prompt:
            return jsonify({
                "success": False,
                "error": "请提供prompt提示词"
            }), 400

        filename = f"{uuid.uuid4().hex}.png"
        save_path =f'generation_shortvideo/generated_images/{filename}'
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        pil_image = loop.run_until_complete(generate_image_async(prompt, aspect_ratio))
        pil_image.save(save_path)

        return jsonify({
            "success": True,
            "filePath": save_path,
            "messageId": message_id
        })

    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"生成超时: {str(e)}"
        }), 500
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": f"生成失败: {str(e)}"
        }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# =====================================视频生成========================================================================
async def generate_video_async(prompt, ratio="16:9"):
    """异步生成视频（仅支持文生视频）"""
    api_key = load_video_api_key_from_config()
    video_generator = VideoGeneratorVeoFastAPI(
        api_key=api_key,
        poll_interval=10,
        max_poll_attempts=60,
    )
    result = await video_generator.generate_single_video(
        prompt=prompt,
        model="veo3.1-fast",
        video_type="text2video",
        ratio=ratio
    )
    return result


def download_video(url, save_path):
    """下载视频到本地"""
    response = requests.get(url, stream=True)
    response.raise_for_status()
    with open(save_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    return save_path



@app.route('/api/generate-video', methods=['POST'])
def generate_video_beta():
    try:
        data = request.json
        prompt = data.get('prompt', '').replace('#视频生成', '').strip()
        ratio = data.get('ratio', '16:9')
        message_id = data.get('messageId', str(uuid.uuid4()))

        if not prompt:
            return jsonify({
                "success": False,
                "error": "请提供prompt提示词"
            }), 400

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        video_output = loop.run_until_complete(generate_video_async(prompt, ratio))
        video_url = video_output.data if hasattr(video_output, 'data') else video_output

        filename = f"{uuid.uuid4().hex}.mp4"
        save_path = f'generation_shortvideo/generated_videos/{filename}'
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        download_video(video_url, save_path)

        return jsonify({
            "success": True,
            "filePath": save_path,
            "messageId": message_id
        })

    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": f"生成超时: {str(e)}"
        }), 500
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": f"生成失败: {str(e)}"
        }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# =====================================广告生成========================================================================
async def generate_ad_async(prompt, progress_callback=None):
    """异步生成广告视频：先生成图片，再根据图片生成视频"""
    def send_progress(stage, message, data=None):
        if progress_callback:
            progress_callback(stage, message, data)
    
    try:
        deepseekapi_key = load_deepseek_api_key_from_config()
        client = OpenAI(
            api_key=deepseekapi_key,
            base_url="https://api.deepseek.com/v1"
        )
        
        send_progress('analyzing', '正在进行创意分析...')
        
        system_prompt = f"""你是一个导演。能根据用户输入的额外提示词生成至少9个与主题相关的分镜高清画面（要求画面是高清特写）的详细的可用于文本生成图像的提示词，所有分镜要有关联并形成完整广告内容。要求直接中文输出不要有特殊符号。中文，高清，视频彩色，朗读文本为：50字以内的精简文本。用户输入：{prompt}"""
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000
        )
        
        image_prompts = response.choices[0].message.content
        send_progress('storyboard', '创意分析完成，正在生成图片...', {'prompts': image_prompts})
        
        api_key = load_image_api_key_from_config()
        image_generator = ImageGeneratorNanobananaWuYinAPI(
            api_key=api_key,
            poll_interval=10,
            max_poll_attempts=60,
        )
        
        result = await image_generator.generate_single_image(
            prompt=image_prompts,
            aspect_ratio="16:9",
        )

        pil_image = result.data
        img_path = f'generation_shortvideo/generated_images/ad_{uuid.uuid4().hex}.png'
        os.makedirs(os.path.dirname(img_path), exist_ok=True)
        pil_image.save(img_path)
        
        send_progress('image_generated', '图片生成完成，正在生成视频...', {'image_path': img_path})

        video_api_key = load_video_api_key_from_config()
        video_generator = VideoGeneratorVeoFastAPI(
            api_key=video_api_key,
            poll_interval=10,
            max_poll_attempts=60,
        )
        
        video_result = await video_generator.generate_single_video(
            prompt=prompt,
            model="veo3.1-fast",
            video_type="text2video",
            reference_images=[result.image_url],
            ratio="16:9"
        )
        
        video_url = video_result.data if hasattr(video_result, 'data') else video_result
        
        video_filename = f"ad_{uuid.uuid4().hex}.mp4"
        video_save_path = f'generation_shortvideo/generated_videos/{video_filename}'
        os.makedirs(os.path.dirname(video_save_path), exist_ok=True)
        download_video(video_url, video_save_path)
        
        send_progress('completed', '生成完成！', {
            'image_path': img_path,
            'video_path': video_save_path
        })
        
        return {
            'image_path': img_path,
            'video_path': video_save_path,
            'image_prompts': image_prompts
        }
    except Exception as e:
        send_progress('error', f'生成失败: {str(e)}')
        raise


def run_ad_generation_task(task_id, prompt):
    """后台运行广告生成任务"""
    progress_queue = ad_progress_queues.get(task_id)
    if not progress_queue:
        return
    
    def progress_callback(stage, message, data=None):
        progress_queue.put({
            'stage': stage,
            'message': message,
            'data': data
        })
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(generate_ad_async(prompt, progress_callback))
    except Exception as e:
        progress_queue.put({
            'stage': 'error',
            'message': str(e)
        })
    finally:
        progress_queue.put({'stage': 'done'})


@app.route('/api/ad-generate-video', methods=['POST'])
def ad_generate_video_beta():
    try:
        data = request.json
        prompt = data.get('prompt', '').replace('#广告生成', '').strip()
        message_id = data.get('messageId', str(uuid.uuid4()))

        if not prompt:
            return jsonify({'success': False, 'error': '请输入广告描述'}), 400

        task_id = str(uuid.uuid4())
        progress_queue = queue.Queue()
        ad_progress_queues[task_id] = progress_queue

        thread = threading.Thread(
            target=run_ad_generation_task,
            args=(task_id, prompt)
        )
        thread.daemon = True
        thread.start()

        return jsonify({
            "success": True,
            "taskId": task_id,
            "messageId": message_id
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/ad-generate-progress/<task_id>')
def ad_generate_progress(task_id):
    """SSE接口：获取广告生成进度"""
    progress_queue = ad_progress_queues.get(task_id)
    
    if not progress_queue:
        return jsonify({'error': 'Task not found'}), 404

    def generate():
        while True:
            try:
                progress = progress_queue.get(timeout=60)
                yield f"data: {json.dumps(progress)}\n\n"
                
                if progress.get('stage') in ['completed', 'error', 'done']:
                    ad_progress_queues.pop(task_id, None)
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'stage': 'timeout'})}\n\n"
                break

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route('/chat', methods=['GET'])
def chatThink():
    print(request)

    think_active = request.args.get('thinkActive')
    search_active = request.args.get('searchActive')
    user = request.args.get('user', 'anonymous')
    print(f"search={search_active},think= {think_active}")
    query = request.args.get('message', '')
    deepseekapi_key = load_deepseek_api_key_from_config()
    client = OpenAI(
        api_key=deepseekapi_key,
        base_url="https://api.deepseek.com/v1"
    )

    def generate():
        try:
            stream = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": query}],
                stream=True,
                temperature=0.7,
                max_tokens=2048
            )
            answer_content = ""  # 定义完整回复
            for chunk in stream:
                content = chunk.choices[0].delta.content or ""
                if len(content) == 0:
                    continue
                # yield f"data: {process_markdown(content)}\n\n"
                # processed = process_markdown(content)
                # 临时替换换行符避免分块问题
                answer_content += content
                yield f"data: {content.replace('\n', '<!--n-->')}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"data: **服务请求失败**: {str(e)}\n\n"
            yield "data: [DONE]\n\n"

    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/generate', methods=['POST'])
def generate_video():
    """开始生成视频"""
    global current_task, task_running

    if task_running:
        return jsonify({'status': 'error', 'message': '已有任务正在运行'}), 400

    data = request.json
    idea = data.get('idea', '')
    user_requirement = data.get('user_requirement', '')
    style = data.get('style', '')
    work_dir = data.get('work_dir', '')

    if not idea:
        return jsonify({'status': 'error', 'message': '请输入创意描述'}), 400

    # 处理工作目录
    if work_dir:
        # 如果指定了工作目录，使用该目录
        if not work_dir.startswith('working_dir_idea2video'):
            work_dir = os.path.join('working_dir_idea2video', work_dir)
    else:
        # 否则生成新的UUID目录
        work_dir = os.path.join('working_dir_idea2video', str(uuid.uuid4()))

    # 确保工作目录存在
    os.makedirs(work_dir, exist_ok=True)

    # 清空日志队列
    while not log_queue.empty():
        log_queue.get()

    # 在后台线程中运行任务
    task_running = True
    thread = threading.Thread(
        target=run_async_task,
        args=(idea, user_requirement, style, work_dir)
    )
    thread.daemon = True
    thread.start()

    return jsonify({
        'status': 'success',
        'message': '开始生成视频...',
        'work_dir': work_dir
    })


@app.route('/api/logs')
def get_logs():
    """SSE流式传输日志"""

    def generate():
        while True:
            try:
                if not log_queue.empty():
                    log = log_queue.get(timeout=1)
                    yield f"data: {json.dumps({'log': log})}\n\n"
                else:
                    yield f"data: {json.dumps({'log': ''})}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'log': ''})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route('/api/task_status')
def task_status():
    """获取任务状态"""
    return jsonify({
        'running': task_running,
        'working_dir': working_dir
    })


@app.route('/api/files')
def list_files():
    """列出生成的文件"""
    work_dir = request.args.get('work_dir', '')

    if not work_dir or not os.path.exists(work_dir):
        return jsonify({'files': [], 'directories': []})

    base_path = Path(work_dir)
    files = []
    directories = []

    # 列出根目录文件
    for item in base_path.iterdir():
        if item.is_file():
            files.append({
                'name': item.name,
                'path': str(item.relative_to(base_path)),
                'size': item.stat().st_size,
                'type': 'file'
            })
        elif item.is_dir():
            directories.append({
                'name': item.name,
                'path': str(item.relative_to(base_path)),
                'type': 'directory'
            })

    # 递归获取所有文件
    all_files = []
    for root, dirs, files_in_dir in os.walk(work_dir):
        for file in files_in_dir:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, work_dir)
            all_files.append({
                'name': file,
                'path': rel_path,
                'size': os.path.getsize(file_path),
                'type': 'file'
            })

    return jsonify({
        'work_dir': work_dir,
        'root_files': files,
        'directories': directories,
        'all_files': all_files
    })


@app.route('/api/work_dirs')
def list_work_dirs():
    """列出所有工作目录"""
    base_dir = 'working_dir_idea2video'
    dirs = []

    if os.path.exists(base_dir):
        for item in os.listdir(base_dir):
            dir_path = os.path.join(base_dir, item)
            if os.path.isdir(dir_path):
                # 检查是否有final_video.mp4
                final_video = os.path.join(dir_path, 'final_video.mp4')
                has_video = os.path.exists(final_video)

                dirs.append({
                    'name': item,
                    'path': dir_path,
                    'has_video': has_video,
                    'created': datetime.fromtimestamp(os.path.getctime(dir_path)).isoformat() if os.path.exists(
                        dir_path) else None
                })

    # 按创建时间倒序排列
    dirs.sort(key=lambda x: x['created'] or '', reverse=True)

    return jsonify({'work_dirs': dirs})


@app.route('/api/file/<path:filepath>')
def get_file(filepath):
    """获取文件内容"""
    work_dir = request.args.get('work_dir', '')

    if not work_dir:
        return jsonify({'error': '工作目录不存在'}), 404

    file_path = os.path.join(work_dir, filepath)

    if not os.path.exists(file_path):
        return jsonify({'error': '文件不存在'}), 404

    # 如果是文本文件，读取内容
    if filepath.endswith(('.txt', '.json', '.yaml', '.yml', '.py', '.js', '.css', '.html')):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return jsonify({'content': content, 'type': 'text'})
        except:
            return jsonify({'type': 'binary'})
    else:
        return jsonify({'type': 'binary'})


@app.route('/download/<path:filepath>')
def download_file(filepath):
    """下载文件"""
    work_dir = request.args.get('work_dir', '')

    if not work_dir:
        return "工作目录不存在", 404

    file_path = os.path.join(work_dir, filepath)
    directory = os.path.dirname(file_path)
    filename = os.path.basename(file_path)

    if not os.path.exists(file_path):
        return "文件不存在", 404

    return send_from_directory(directory, filename, as_attachment=True)


@app.route('/api/preview/<path:filepath>')
def preview_file(filepath):
    """预览文件（图片/视频）"""
    work_dir = request.args.get('work_dir', '')

    if not work_dir:
        return "工作目录不存在", 404

    file_path = os.path.join(work_dir, filepath)

    if not os.path.exists(file_path):
        return "文件不存在", 404

    # 根据文件类型返回不同响应
    if filepath.endswith(('.png', '.jpg', '.jpeg', '.gif')):
        return send_from_directory(os.path.dirname(file_path), os.path.basename(file_path))
    elif filepath.endswith('.mp4'):
        # 视频预览 - 返回HTML页面
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>视频预览</title>
            <style>
                body {{ margin: 0; padding: 20px; background: #f5f5f5; }}
                .video-container {{ max-width: 800px; margin: 0 auto; }}
                video {{ width: 100%; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
            </style>
        </head>
        <body>
            <div class="video-container">
                <video controls autoplay>
                    <source src="/download/{filepath}?work_dir={work_dir}" type="video/mp4">
                    您的浏览器不支持视频标签。
                </video>
            </div>
        </body>
        </html>
        '''
    else:
        return "不支持的文件类型", 400


@app.route('/api/stats')
def get_stats():
    """获取生成统计信息"""
    work_dir = request.args.get('work_dir', '')

    if not work_dir or not os.path.exists(work_dir):
        return jsonify({'total_files': 0, 'total_size': 0})

    total_files = 0
    total_size = 0

    for root, dirs, files in os.walk(work_dir):
        total_files += len(files)
        for file in files:
            file_path = os.path.join(root, file)
            total_size += os.path.getsize(file_path)

    # 获取主要文件信息
    main_files = {}
    for file in ['story.txt', 'characters.json', 'script.json', 'final_video.mp4']:
        file_path = os.path.join(work_dir, file)
        if os.path.exists(file_path):
            main_files[file] = {
                'size': os.path.getsize(file_path),
                'modified': datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
            }

    return jsonify({
        'total_files': total_files,
        'total_size': total_size,
        'main_files': main_files
    })


# 自定义模板过滤器
@app.template_filter('basename')
def basename_filter(path):
    """获取文件路径的基名"""
    return os.path.basename(path) if path else ""


@app.template_filter('truncate_path')
def truncate_path_filter(path, length=50):
    """截断路径显示"""
    if len(path) <= length:
        return path
    return f"...{path[-length:]}"


# 图片浏览器路由
@app.route('/images')
def images_viewer():
    """图片浏览器主页面"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    keyword = request.args.get('keyword', '')

    db = get_db()

    if keyword:
        # 搜索模式
        images = db.search_images(keyword)
        # 为每个图片添加文件存在信息
        for image in images:
            image['file_exists'] = os.path.exists(image['local_path'])
        total = len(images)
        return render_template('images.html',
                               images=images,
                               total=total,
                               page=page,
                               per_page=per_page,
                               pages=1,
                               keyword=keyword)
    else:
        # 分页模式
        result = db.get_paginated_images(page, per_page)
        # 为每个图片添加文件存在信息
        for image in result['images']:
            image['file_exists'] = os.path.exists(image['local_path'])
        return render_template('images.html',
                               images=result['images'],
                               total=result['total'],
                               page=result['page'],
                               per_page=result['per_page'],
                               pages=result['pages'],
                               keyword=keyword)


@app.route('/api/images')
def api_get_images():
    """API接口：获取图片数据"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    db = get_db()
    result = db.get_paginated_images(page, per_page)

    # 为每张图片添加预览数据
    for image in result['images']:
        # 添加文件是否存在信息
        image['file_exists'] = os.path.exists(image['local_path'])

        # 如果文件存在，获取文件大小
        if image['file_exists']:
            try:
                image['file_size'] = os.path.getsize(image['local_path'])
                image['file_size_fmt'] = _format_file_size(image['file_size'])
            except:
                image['file_size'] = 0
                image['file_size_fmt'] = '未知'
        else:
            image['file_size'] = 0
            image['file_size_fmt'] = '文件不存在'

    return jsonify({
        'success': True,
        'data': result
    })


@app.route('/api/images/<int:image_id>')
def api_get_image_detail(image_id):
    """API接口：获取单张图片详情"""
    db = get_db()
    image = db.get_image_by_id(image_id)

    if not image:
        return jsonify({
            'success': False,
            'message': '图片不存在'
        }), 404

    # 添加详细信息
    image['file_exists'] = os.path.exists(image['local_path'])
    if image['file_exists']:
        try:
            # 尝试获取图片尺寸
            img = PILImage.open(image['local_path'])
            image['dimensions'] = f"{img.width} × {img.height}"
            image['format'] = img.format
            img.close()

            # 文件大小
            image['file_size'] = os.path.getsize(image['local_path'])
            image['file_size_fmt'] = _format_file_size(image['file_size'])
        except Exception as e:
            image['dimensions'] = '未知'
            image['format'] = '未知'
            image['file_size'] = 0
            image['file_size_fmt'] = '未知'

    return jsonify({
        'success': True,
        'data': image
    })


@app.route('/api/images/<int:image_id>/preview')
def api_get_image_preview(image_id):
    """API接口：获取图片预览（缩略图）"""
    db = get_db()
    image = db.get_image_by_id(image_id)

    if not image:
        abort(404, description="图片不存在")

    # 检查文件是否存在
    if not os.path.exists(image['local_path']):
        # 返回一个占位图片
        return _generate_placeholder_image("文件不存在", 300)

    # 生成缩略图
    try:
        size = request.args.get('size', 300, type=int)

        # 打开图片
        img = PILImage.open(image['local_path'])

        # 计算缩略图尺寸
        img.thumbnail((size, size), PILImage.Resampling.LANCZOS)

        # 转换为base64
        buffered = io.BytesIO()

        # 保持原始格式或转换为JPEG
        if img.mode in ('RGBA', 'LA', 'P'):
            # 如果有透明度，转换为RGBA PNG
            if img.mode == 'P':
                img = img.convert('RGBA')
            elif img.mode == 'LA':
                img = img.convert('RGBA')
            img.save(buffered, format='PNG')
            mime_type = 'image/png'
        else:
            # 无透明度，转换为JPEG节省空间
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(buffered, format='JPEG', quality=85)
            mime_type = 'image/jpeg'

        img.close()

        img_str = base64.b64encode(buffered.getvalue()).decode()

        return jsonify({
            'success': True,
            'data': f"data:{mime_type};base64,{img_str}"
        })
    except Exception as e:
        print(f"生成预览失败: {str(e)}")
        # 返回错误占位图
        return _generate_placeholder_image("预览生成失败", 300)


@app.route('/api/images/<int:image_id>/open')
def api_open_image(image_id):
    """API接口：在浏览器中打开图片"""
    db = get_db()
    image = db.get_image_by_id(image_id)

    if not image:
        abort(404)

    if not os.path.exists(image['local_path']):
        # 返回404错误页面
        return _generate_placeholder_image("文件不存在", 800, as_response=True)

    # 直接返回图片文件
    try:
        # 获取文件扩展名
        ext = os.path.splitext(image['local_path'])[1].lower()
        mimetype = 'image/jpeg' if ext in ['.jpg',
                                           '.jpeg'] else 'image/png' if ext == '.png' else 'image/gif' if ext == '.gif' else 'image/webp' if ext == '.webp' else 'application/octet-stream'

        return send_file(
            image['local_path'],
            mimetype=mimetype
        )
    except Exception as e:
        return _generate_placeholder_image(f"打开图片失败: {str(e)}", 800, as_response=True)


@app.route('/api/images/delete/<int:image_id>', methods=['DELETE'])
def api_delete_image(image_id):
    """API接口：删除图片记录"""
    db = get_db()
    image = db.get_image_by_id(image_id)

    if not image:
        return jsonify({
            'success': False,
            'message': '图片不存在'
        }), 404

    try:
        success = db.delete_image_record(image['local_path'])

        return jsonify({
            'success': success,
            'message': '删除成功' if success else '删除失败'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'删除失败: {str(e)}'
        }), 500


@app.route('/api/images/batch/delete', methods=['POST'])
def api_batch_delete_images():
    """API接口：批量删除图片记录"""
    data = request.json
    image_ids = data.get('image_ids', [])

    if not image_ids:
        return jsonify({
            'success': False,
            'message': '未提供图片ID'
        }), 400

    db = get_db()
    deleted_count = 0

    for image_id in image_ids:
        image = db.get_image_by_id(image_id)
        if image:
            if db.delete_image_record(image['local_path']):
                deleted_count += 1

    return jsonify({
        'success': True,
        'message': f'成功删除 {deleted_count} 张图片',
        'deleted_count': deleted_count
    })


@app.route('/api/images/stats')
def api_get_stats():
    """API接口：获取统计信息"""
    db = get_db()

    with db._get_connection() as conn:
        cursor = conn.cursor()

        # 获取总数
        cursor.execute('SELECT COUNT(*) as total FROM images WHERE status = "active"')
        total = cursor.fetchone()['total']

        # 获取文件存在的数量
        cursor.execute('SELECT local_path FROM images WHERE status = "active"')
        rows = cursor.fetchall()

        existing_count = 0
        total_size = 0

        for row in rows:
            if os.path.exists(row['local_path']):
                existing_count += 1
                try:
                    total_size += os.path.getsize(row['local_path'])
                except:
                    pass

        # 获取最近添加的图片
        cursor.execute('''
            SELECT COUNT(*) as today_count 
            FROM images 
            WHERE status = "active" AND 
                  DATE(created_at) = DATE('now')
        ''')
        today_count = cursor.fetchone()['today_count']

    return jsonify({
        'success': True,
        'data': {
            'total_images': total,
            'existing_images': existing_count,
            'missing_images': total - existing_count,
            'today_added': today_count,
            'total_size': total_size,
            'total_size_fmt': _format_file_size(total_size)
        }
    })


@app.route('/preview/<int:image_id>')
def preview_image_direct(image_id):
    """直接预览图片（用于HTML img标签的src属性）"""
    db = get_db()
    image = db.get_image_by_id(image_id)

    if not image:
        # 返回404占位图
        return _generate_placeholder_image("图片不存在", 300, as_response=True)

    if not os.path.exists(image['local_path']):
        # 返回文件不存在占位图
        return _generate_placeholder_image("文件不存在", 300, as_response=True)

    try:
        size = request.args.get('size', 300, type=int)

        # 打开图片
        img = PILImage.open(image['local_path'])

        # 计算缩略图尺寸
        img.thumbnail((size, size), PILImage.Resampling.LANCZOS)

        # 保存到字节流
        buffered = io.BytesIO()

        # 根据图片模式选择格式
        if img.mode in ('RGBA', 'LA', 'P'):
            if img.mode == 'P':
                img = img.convert('RGBA')
            elif img.mode == 'LA':
                img = img.convert('RGBA')
            img.save(buffered, format='PNG')
            mimetype = 'image/png'
        else:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(buffered, format='JPEG', quality=85)
            mimetype = 'image/jpeg'

        img.close()

        buffered.seek(0)
        return send_file(buffered, mimetype=mimetype)

    except Exception as e:
        print(f"直接预览失败: {str(e)}")
        return _generate_placeholder_image("预览失败", 300, as_response=True)


def _format_file_size(size_bytes):
    """格式化文件大小"""
    if size_bytes == 0:
        return "0 B"

    size_names = ("B", "KB", "MB", "GB", "TB")
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1

    return f"{size_bytes:.2f} {size_names[i]}"


def _generate_placeholder_image(text, size=300, as_response=False):
    """生成占位图片"""
    from PIL import Image, ImageDraw, ImageFont
    import io

    # 创建新图片
    img = Image.new('RGB', (size, size), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)

    try:
        # 尝试使用系统字体
        font = ImageFont.truetype("arial.ttf", 20)
    except:
        # 使用默认字体
        font = ImageFont.load_default()

    # 绘制文字
    text_width = draw.textlength(text, font=font)
    text_height = 20
    x = (size - text_width) / 2
    y = (size - text_height) / 2

    draw.text((x, y), text, fill=(100, 100, 100), font=font)

    # 保存到字节流
    buffered = io.BytesIO()
    img.save(buffered, format='PNG')
    buffered.seek(0)

    if as_response:
        return send_file(buffered, mimetype='image/png')
    else:
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return jsonify({
            'success': True,
            'data': f"data:image/png;base64,{img_str}"
        })


if __name__ == '__main__':
    # 确保工作目录存在
    os.makedirs("working_dir_idea2video", exist_ok=True)
    app.run(debug=True, host="0.0.0.0", port=5001, threaded=True)