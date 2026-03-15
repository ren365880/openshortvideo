# routes/generation.py - 生成流程路由
from flask import Blueprint, request, jsonify, render_template,send_file,current_app
from flask_login import login_required, current_user
from __init__ import db
from models import Project, Episode, Character
from datetime import datetime
import os
import json
import uuid
import shutil
import time
import requests
import traceback
from threading import Thread

# 导入模型配置服务
from services.model_config_service import (
    get_model_options,
    get_default_model_config,
    get_episode_model_config,
    save_episode_model_config,
    generate_config_for_episode
)

bp = Blueprint('generation', __name__)

# 生成文件存储路径 - 使用后端目录
def get_generation_dir():
    """获取生成目录的绝对路径 - 后端目录"""
    # 保存到后端目录 backend/generation_shortvideo/
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(os.path.dirname(base_dir), 'backend', 'generation_shortvideo')

GENERATION_DIR = get_generation_dir()

def get_episode_dir(username, project_id, episode_number):
    """获取分集的工作目录: generation_shortvideo/{username}/{project_id}/{episode_number}"""
    return os.path.join(GENERATION_DIR, str(username), str(project_id), str(episode_number))

# 确保生成目录存在
os.makedirs(GENERATION_DIR, exist_ok=True)
print(f"[Generation] Generation directory: {GENERATION_DIR}")


# 添加的配置项
@bp.route('/api/episodes/<int:episode_id>/generation/config', methods=['POST'])
@login_required
def save_generation_config(episode_id):
    """保存生成配置"""
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403

    data = request.get_json()

    # 保存配置到分集
    episode.idea = data.get('idea', '')
    episode.user_requirement = data.get('user_requirement', '')
    episode.style = data.get('style', 'anime')
    episode.generation_mode = data.get('generation_mode', 'step_by_step')  # 新增：生成方式
    episode.generation_config = json.dumps({
        'scene_count': data.get('scene_count', 1),
        'shots_per_scene': data.get('shots_per_scene', 1),
        'resolution': data.get('resolution', '1080p'),
        'duration': data.get('duration', 30),
        'generation_mode': data.get('generation_mode', 'step_by_step')  # 新增
    })
    print(1111,episode.generation_config)
    episode.updated_at = datetime.utcnow()

    db.session.commit()

    return jsonify({
        'message': '配置保存成功',
        'episode': episode.to_dict()
    })


# 新增：一键生成接口
@bp.route('/api/episodes/<int:episode_id>/generate/oneclick', methods=['POST'])
@login_required
def generate_oneclick(episode_id):
    """一键生成"""
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403

    try:
        # 更新分集状态
        episode.generation_status = 'processing'
        episode.generation_mode = 'oneclick'
        episode.updated_at = datetime.utcnow()
        db.session.commit()

        # 获取配置
        config = json.loads(episode.generation_config) if episode.generation_config else {}

        # 启动后台生成任务
        thread = Thread(target=oneclick_generation_task, args=(episode_id, config))
        thread.daemon = True
        thread.start()

        return jsonify({
            'message': '一键生成已启动，请查看生成日志',
            'task_id': f'oneclick_{episode_id}'
        })

    except Exception as e:
        print(f"启动一键生成失败: {e}")
        return jsonify({'error': f'启动一键生成失败: {str(e)}'}), 500


# 新增：继续生成接口（预留）
@bp.route('/api/episodes/<int:episode_id>/generate/resume', methods=['POST'])
@login_required
def resume_oneclick_generation(episode_id):
    """继续一键生成（从上次停止的步骤继续）"""
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403

    try:
        # 检查当前生成状态
        if episode.generation_status != 'stopped':
            return jsonify({
                'message': '当前生成状态不是停止状态，无需继续',
                'status': episode.generation_status
            })

        # 更新分集状态为进行中
        episode.generation_status = 'processing'
        episode.updated_at = datetime.utcnow()
        db.session.commit()

        # 获取配置
        config = json.loads(episode.generation_config) if episode.generation_config else {}

        # 启动后台继续生成任务
        thread = Thread(target=resume_generation_task, args=(episode_id, config))
        thread.daemon = True
        thread.start()

        return jsonify({
            'message': '继续生成已启动',
            'task_id': f'resume_{episode_id}'
        })

    except Exception as e:
        print(f"启动继续生成失败: {e}")
        return jsonify({'error': f'启动继续生成失败: {str(e)}'}), 500


def resume_generation_task(episode_id, config):
    """后台继续生成任务（从上次停止的步骤继续）"""
    try:
        from flask import Flask
        app = Flask(__name__)

        with app.app_context():
            from __init__ import create_app, db
            app = create_app()

            with app.app_context():
                # 先获取episode信息
                episode = Episode.query.get(episode_id)
                if not episode:
                    return
                
                project = Project.query.get(episode.project_id)
                username = project.creator.username if project and project.creator else 'unknown'
                
                # 检查当前各步骤的完成状态
                episode_dir = get_episode_dir(username, episode.project_id, episode.episode_number)

                # 检查哪些步骤已完成
                story_exists = os.path.exists(os.path.join(episode_dir, 'story.txt'))
                characters_exists = os.path.exists(os.path.join(episode_dir, 'characters.json'))
                scene_exists = os.path.exists(os.path.join(episode_dir, 'scene_0'))
                shots_exist = os.path.exists(os.path.join(episode_dir, 'scene_0', 'shots'))
                final_exists = os.path.exists(os.path.join(episode_dir, 'final_video.mp4'))

                if episode:
                    # 根据已有文件判断从哪一步继续
                    if not story_exists:
                        # 从故事生成开始
                        print(f"继续生成: 从故事生成开始 (episode {episode_id})")
                        # 这里调用故事生成逻辑
                    elif not characters_exists:
                        # 从角色生成开始
                        print(f"继续生成: 从角色生成开始 (episode {episode_id})")
                        # 这里调用角色生成逻辑
                    elif not scene_exists:
                        # 从场景生成开始
                        print(f"继续生成: 从场景生成开始 (episode {episode_id})")
                        # 这里调用场景生成逻辑
                    elif not shots_exist:
                        # 从镜头生成开始
                        print(f"继续生成: 从镜头生成开始 (episode {episode_id})")
                        # 这里调用镜头生成逻辑
                    elif not final_exists:
                        # 从最终视频合成开始
                        print(f"继续生成: 从视频合成开始 (episode {episode_id})")
                        # 这里调用最终视频合成逻辑
                    else:
                        # 所有步骤都已完成
                        episode.generation_status = 'completed'
                        db.session.commit()
                        print(f"继续生成: 所有步骤已完成 (episode {episode_id})")

                    # 更新状态为完成
                    if final_exists:
                        episode.generation_status = 'completed'
                        db.session.commit()

    except Exception as e:
        print(f"继续生成任务失败: {e}")
        try:
            from __init__ import db
            episode = Episode.query.get(episode_id)
            if episode:
                episode.generation_status = 'failed'
                db.session.commit()
        except:
            pass


def oneclick_generation_task(episode_id, config):
    """后台一键生成任务"""
    print(f"[OneClick] === START oneclick_generation_task for episode {episode_id} ===")
    print(f"[OneClick] Config: {config}")
    try:
        from flask import Flask
        app = Flask(__name__)

        with app.app_context():
            from __init__ import create_app, db
            app = create_app()

            with app.app_context():
                # 获取episode信息
                episode = Episode.query.get(episode_id)
                if not episode:
                    print(f"[OneClick] ERROR: Episode {episode_id} not found")
                    return
                
                project_id = episode.project_id
                episode_number = episode.episode_number
                
                # 获取API主机地址 - 硬编码为localhost:5001
                api_host = "http://localhost:5001"
                print(f"[OneClick] Project ID: {project_id}, Episode Number: {episode_number}")
                print(f"[OneClick] Current episode status: generation_status={episode.generation_status}, status={episode.status}, video_url={episode.video_url}")
                
                # 创建工作目录：generation_shortvideo/{username}/{project_id}/{episode_number}
                episode_dir = get_episode_dir(current_user.username, project_id, episode_number)
                os.makedirs(episode_dir, exist_ok=True)
                print(f"[OneClick] Working directory: {episode_dir}, API Host: {api_host}")

                # 生成模型配置文件
                try:
                    from services.model_config_service import generate_config_for_episode
                    generate_config_for_episode(episode_id, episode_dir)
                except Exception as e:
                    print(f"[OneClick] 生成配置文件失败: {e}")

                # 生成故事
                story_content = f"一键生成的故事内容 - {datetime.utcnow()}"
                story_file = os.path.join(episode_dir, 'story.txt')
                with open(story_file, 'w', encoding='utf-8') as f:
                    f.write(story_content)

                # 生成角色信息
                characters = [
                    {
                        'id': 0,
                        'name': '一键生成角色1',
                        'role': '主角',
                        'gender': '男',
                        'age': 25,
                        'description': '一键生成的角色描述',
                        'color': '#4F46E5',
                        'personality': '一键生成的角色性格'
                    }
                ]
                characters_file = os.path.join(episode_dir, 'characters.json')
                with open(characters_file, 'w', encoding='utf-8') as f:
                    json.dump(characters, f, ensure_ascii=False, indent=2)
                
                # 保存角色到数据库（角色管理）
                try:
                    project = Project.query.get(project_id)
                    if project:
                        existing_chars = Character.query.filter_by(
                            project_id=project_id,
                            episode_number=episode_number
                        ).all()
                        
                        if existing_chars:
                            print(f"[OneClick] 该集角色已存在，无需重复保存，共{len(existing_chars)}个角色")
                        else:
                            for i, char in enumerate(characters):
                                char_name = char.get('name', f'角色{i+1}')
                                new_char = Character(
                                    name=char_name,
                                    role=char.get('role', '主角' if i == 0 else '配角'),
                                    gender=char.get('gender'),
                                    age=char.get('age'),
                                    description=char.get('description', ''),
                                    personality=char.get('personality', ''),
                                    color=char.get('color', '#4F46E5'),
                                    project_id=project_id,
                                    episode_number=episode_number
                                )
                                db.session.add(new_char)
                            
                            db.session.commit()
                            print(f"[OneClick] 已保存{len(characters)}个角色到数据库")
                except Exception as char_err:
                    print(f"[OneClick] 保存角色到数据库失败: {char_err}")
                    db.session.rollback()

                # 生成场景
                scene_dir = os.path.join(episode_dir, 'scene_0')
                os.makedirs(scene_dir, exist_ok=True)

                storyboard = {
                    'scene_index': 0,
                    'scene_name': '一键生成场景',
                    'description': '一键生成的场景描述',
                    'duration': config.get('duration', 30)
                }
                storyboard_file = os.path.join(scene_dir, 'storyboard.json')
                with open(storyboard_file, 'w', encoding='utf-8') as f:
                    json.dump(storyboard, f, ensure_ascii=False, indent=2)

                # 生成镜头
                shots_dir = os.path.join(scene_dir, 'shots')
                os.makedirs(shots_dir, exist_ok=True)

                shots_per_scene = int(config.get('shots_per_scene', 1))
                for i in range(shots_per_scene):
                    shot_dir = os.path.join(shots_dir, str(i))
                    os.makedirs(shot_dir, exist_ok=True)

                    shot_description = {
                        'shot_index': i,
                        'description': f'一键生成镜头{i}',
                        'duration': int(config.get('duration', 30)) / shots_per_scene
                    }
                    description_file = os.path.join(shot_dir, 'shot_description.json')
                    with open(description_file, 'w', encoding='utf-8') as f:
                        json.dump(shot_description, f, ensure_ascii=False, indent=2)

                # 生成最终视频占位
                final_video_file = os.path.join(episode_dir, 'final_video.mp4')
                with open(final_video_file, 'w') as f:
                    f.write("Placeholder for one-click generated video")

                # 更新数据库状态
                episode = Episode.query.get(episode_id)
                if episode:
                    # 使用正确的路径格式: username/project_id/episode_number
                    video_url = f'{api_host}/api/v1/generate/file?work_dir={current_user.username}/{project_id}/{episode_number}&path=final_video.mp4'
                    print(f"[OneClick] Setting video_url for episode {episode_id}: {video_url}")
                    print(f"[OneClick] Before update - generation_status: {episode.generation_status}, status: {episode.status}, video_url: {episode.video_url}")
                    episode.generation_status = 'completed'
                    episode.status = 'ready'
                    episode.video_url = video_url
                    episode.generation_completed_at = datetime.utcnow()
                    episode.updated_at = datetime.utcnow()
                    try:
                        db.session.commit()
                        print(f"[OneClick] SUCCESS: Episode {episode_id} updated with video_url: {episode.video_url}")
                        print(f"[OneClick] After commit - generation_status: {episode.generation_status}, status: {episode.status}, video_url: {episode.video_url}")
                    except Exception as commit_error:
                        print(f"[OneClick] ERROR: Failed to commit changes: {commit_error}")
                        db.session.rollback()
                else:
                    print(f"[OneClick] ERROR: Episode {episode_id} not found after generation")

    except Exception as e:
        print(f"[OneClick] ERROR: 一键生成任务失败: {e}")
        import traceback
        traceback.print_exc()
        try:
            from __init__ import db
            episode = Episode.query.get(episode_id)
            if episode:
                print(f"[OneClick] Setting generation_status to 'failed' for episode {episode_id}")
                episode.generation_status = 'failed'
                episode.updated_at = datetime.utcnow()
                db.session.commit()
                print(f"[OneClick] Episode {episode_id} marked as failed")
        except Exception as inner_e:
            print(f"[OneClick] ERROR: Failed to update episode status after error: {inner_e}")
    finally:
        print(f"[OneClick] === END oneclick_generation_task for episode {episode_id} ===")


# 新增：检查文件是否存在接口
@bp.route('/api/episodes/<int:episode_id>/generation/checkfiles', methods=['GET'])
@login_required
def check_generation_files(episode_id):
    """检查生成文件是否存在"""
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403

    # 新的目录结构：generation_shortvideo/{username}/{project_id}/{episode_number}
    episode_dir = get_episode_dir(current_user.username, episode.project_id, episode.episode_number)
    
    files_to_check = {
        'story': 'story.txt',
        'characters': 'characters.json',
        'portraits': 'character_portraits_registry.json',
        'scene_0_storyboard': 'scene_0/storyboard.json',
        'scene_0_camera_tree': 'scene_0/camera_tree.json',
        'shot_0_description': 'scene_0/shots/0/shot_description.json',
        'shot_0_first_frame': 'scene_0/shots/0/first_frame.png',
        'shot_0_first_frame_selector': 'scene_0/shots/0/first_frame_selector_output.json',
        'shot_0_last_frame': 'scene_0/shots/0/last_frame.png',
        'shot_0_video': 'scene_0/shots/0/video.mp4',
        'final_video': 'final_video.mp4'
    }

    results = {}
    for key, filename in files_to_check.items():
        file_path = os.path.join(episode_dir, filename)
        results[key] = {
            'exists': os.path.exists(file_path),
            'path': filename,
            'full_path': file_path,
            'size': os.path.getsize(file_path) if os.path.exists(file_path) else 0
        }

    # 检查所有shots
    shots_dir = os.path.join(episode_dir, 'scene_0', 'shots')
    shots_count = 0
    if os.path.exists(shots_dir):
        shots_count = len([d for d in os.listdir(shots_dir) if os.path.isdir(os.path.join(shots_dir, d))])

    results['shots_count'] = shots_count

    # 计算整体进度
    completed = sum(1 for r in results.values() if isinstance(r, dict) and r.get('exists', False))
    total = len([r for r in results.values() if isinstance(r, dict)])
    progress = (completed / total * 100) if total > 0 else 0

    return jsonify({
        'files': results,
        'progress': round(progress, 2),
        'completed': completed,
        'total': total,
        'episode_dir': episode_dir,
        'generation_mode': episode.generation_mode or 'step_by_step'
    })


# 新增：轮询生成状态接口
@bp.route('/api/episodes/<int:episode_id>/generation/poll', methods=['GET'])
@login_required
def poll_generation_status(episode_id):
    """轮询生成状态"""
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403

    # 检查文件状态
    files_response = check_generation_files(episode_id)
    files_data = files_response.get_json()

    # 检查数据库状态
    status = {
        'generation_status': episode.generation_status or 'pending',
        'generation_mode': episode.generation_mode or 'step_by_step',
        'status': episode.status or 'draft',
        'files': files_data.get('files', {}),
        'progress': files_data.get('progress', 0),
        'completed': files_data.get('completed', 0),
        'total': files_data.get('total', 0),
        'is_complete': episode.generation_status == 'completed'
    }

    return jsonify(status)


# 新增：获取生成配置
@bp.route('/api/episodes/<int:episode_id>/generation/config', methods=['GET'])
@login_required
def get_generation_config(episode_id):
    """获取生成配置"""
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403

    config = json.loads(episode.generation_config) if episode.generation_config else {}

    return jsonify({
        'idea': episode.idea,
        'user_requirement': episode.user_requirement,
        'style': episode.style,
        'generation_mode': episode.generation_mode,
        'config': config
    })


# 获取可用的模型选项
@bp.route('/api/episodes/<int:episode_id>/generation/models/options', methods=['GET'])
@login_required
def get_model_options_api(episode_id):
    """获取可用的模型选项"""
    episode = Episode.query.get_or_404(episode_id)
    
    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403
    
    return jsonify(get_model_options())


# 获取分集的模型配置
@bp.route('/api/episodes/<int:episode_id>/generation/models/config', methods=['GET'])
@login_required
def get_episode_model_config_api(episode_id):
    """获取分集的模型配置"""
    episode = Episode.query.get_or_404(episode_id)
    
    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403
    
    # 获取默认配置和分集配置
    default_config = get_default_model_config()
    episode_config = get_episode_model_config(episode_id)
    
    return jsonify({
        'default': default_config,
        'episode': episode_config
    })


# 保存分集的模型配置
@bp.route('/api/episodes/<int:episode_id>/generation/models/config', methods=['POST'])
@login_required
def save_episode_model_config_api(episode_id):
    """保存分集的模型配置"""
    episode = Episode.query.get_or_404(episode_id)
    
    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403
    
    data = request.get_json()
    
    try:
        save_episode_model_config(episode_id, data)
        return jsonify({
            'message': '模型配置保存成功'
        })
    except Exception as e:
        return jsonify({'error': f'保存模型配置失败: {str(e)}'}), 500


# 生成配置文件到指定目录
@bp.route('/api/episodes/<int:episode_id>/generation/models/config/file', methods=['POST'])
@login_required
def generate_model_config_file(episode_id):
    """生成模型配置文件到指定目录"""
    episode = Episode.query.get_or_404(episode_id)
    
    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403
    
    data = request.get_json()
    output_dir = data.get('output_dir')
    
    if not output_dir:
        return jsonify({'error': '请指定输出目录'}), 400
    
    try:
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 先生保存配置
        if 'model_config' in data:
            save_episode_model_config(episode_id, data['model_config'])
        
        # 生成配置文件
        config_path = generate_config_for_episode(episode_id, output_dir)
        
        return jsonify({
            'message': '配置文件生成成功',
            'config_path': config_path
        })
    except Exception as e:
        return jsonify({'error': f'生成配置文件失败: {str(e)}'}), 500


@bp.route('/api/episodes/<int:episode_id>/generate/story/save', methods=['POST'])
@login_required
def save_story(episode_id):
    """保存用户编辑的故事"""
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403

    try:
        data = request.get_json()
        story_content = data.get('story_content', '')

        if not story_content:
            return jsonify({'error': '故事内容不能为空'}), 400

        # 保存到文件
        story_file = os.path.join(get_episode_dir(current_user.username, episode.project_id, episode.episode_number), 'story.txt')
        os.makedirs(os.path.dirname(story_file), exist_ok=True)

        with open(story_file, 'w', encoding='utf-8') as f:
            f.write(story_content)

        # 更新数据库
        episode.generation_story = story_content
        episode.updated_at = datetime.utcnow()
        db.session.commit()

        print(f"[Save Story] Story saved for episode {episode_id}")

        return jsonify({
            'success': True,
            'message': '故事保存成功',
            'file': '/generation/' + str(episode_id) + '/story.txt'
        })

    except Exception as e:
        print(f"[Save Story] 保存故事失败: {e}")
        traceback.print_exc()
        return jsonify({'error': f'保存故事失败: {str(e)}'}), 500


@bp.route('/api/episodes/<int:episode_id>/generate/story', methods=['POST'])
@login_required
def generate_story(episode_id):
    """生成故事（调用后端API）"""
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403

    print(f"[Generate Story] Starting story generation for episode {episode_id}")

    try:
        # 获取后端API主机
        api_host = get_backend_api_host()
        
        # 获取或创建生成任务
        task_id = get_or_create_generation_task(episode_id, episode, api_host)
        if not task_id:
            raise Exception("Failed to get or create generation task")
        
        print(f"[Generate Story] Using task ID: {task_id}")
        
        # 执行develop_story步骤
        step_name = "develop_story"
        success, error_msg = execute_backend_step(task_id, step_name, api_host)
        
        if not success:
            # 更新分集状态为失败
            episode.generation_story_status = 'failed'
            episode.updated_at = datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'error': f'故事生成失败: {error_msg}'
            }), 500
        
        # 下载生成的故事文件
        download_success = download_backend_artifact(episode_id, task_id, 'story.txt', api_host, current_user.username, episode.project_id, episode.episode_number)
        
        if download_success:
            # 读取故事内容
            story_file = os.path.join(get_episode_dir(current_user.username, episode.project_id, episode.episode_number), 'story.txt')
            if os.path.exists(story_file):
                with open(story_file, 'r', encoding='utf-8') as f:
                    story_content = f.read()
                print(f"[Generate Story] DEBUG: Read story content length: {len(story_content)}")
                print(f"[Generate Story] DEBUG: First 200 chars: {story_content[:200]}")
            else:
                story_content = "故事已生成，但文件读取失败"
        else:
            story_content = "故事已生成，但文件下载失败"
        
        # 更新分集状态
        episode.generation_story = story_content
        episode.generation_story_status = 'completed'
        episode.updated_at = datetime.utcnow()
        db.session.commit()

        print(f"[Generate Story] DEBUG: Returning story_content type: {type(story_content)}")
        return jsonify({
            'message': '故事生成成功',
            'story_content': story_content,
            'story_file': '/generation/' + str(episode_id) + '/story.txt',
            'task_id': task_id
        })

    except Exception as e:
        print(f"[Generate Story] 生成故事失败: {e}")
        traceback.print_exc()
        episode.generation_story_status = 'failed'
        episode.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'error': f'故事生成失败: {str(e)}'}), 500


@bp.route('/api/episodes/<int:episode_id>/generate/characters', methods=['POST'])
@login_required
def generate_characters(episode_id):
    """生成角色信息（调用后端API）"""
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403

    print(f"[Generate Characters] Starting character generation for episode {episode_id}")

    try:
        # 获取后端API主机
        api_host = get_backend_api_host()
        
        # 获取或创建生成任务
        task_id = get_or_create_generation_task(episode_id, episode, api_host)
        if not task_id:
            raise Exception("Failed to get or create generation task")
        
        print(f"[Generate Characters] Using task ID: {task_id}")
        
        # 角色生成需要先执行develop_story和extract_characters步骤
        character_steps = [
            ('develop_story', 'story.txt'),
            ('extract_characters', 'characters.json')
        ]
        
        # 执行每个步骤
        for step_name, artifact_name in character_steps:
            print(f"[Generate Characters] Executing step: {step_name}")
            success, error_msg = execute_backend_step(task_id, step_name, api_host)
            
            if not success:
                # 更新分集状态为失败
                episode.generation_characters_status = 'failed'
                episode.updated_at = datetime.utcnow()
                db.session.commit()
                
                return jsonify({
                    'error': f'角色信息生成失败 (步骤 {step_name}): {error_msg}'
                }), 500
        
        # 下载生成的角色文件
        download_success = download_backend_artifact(episode_id, task_id, 'characters.json', api_host, current_user.username, episode.project_id, episode.episode_number)
        print(f"[Generate Characters] download_success: {download_success}")
        
        characters = []
        if download_success:
            # 读取角色信息
            characters_file = os.path.join(get_episode_dir(current_user.username, episode.project_id, episode.episode_number), 'characters.json')
            
            if os.path.exists(characters_file):
                print(f"[Generate Characters] Found characters.json at: {characters_file}")
            
            if characters_file:
                with open(characters_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f"[Generate Characters] Raw data: {data}")
                    
                    # 处理嵌套的JSON结构
                    if isinstance(data, dict) and 'content' in data:
                        content = data['content']
                        if isinstance(content, str):
                            characters = json.loads(content)
                        else:
                            characters = content
                    else:
                        characters = data
                print(f"[Generate Characters] Parsed characters: {characters}")
            else:
                print(f"[Generate Characters] characters.json not found in any path: {possible_paths}")
                characters = [{"error": "文件读取失败"}]
        else:
            print(f"[Generate Characters] Download failed!")
            characters = [{"error": "文件下载失败"}]
        
        # 保存角色到数据库（角色管理）
        try:
            print(f"[Generate Characters] Starting save to DB, characters count: {len(characters) if isinstance(characters, list) else 'not a list'}")
            
            # 过滤掉错误项
            valid_characters = [c for c in characters if isinstance(c, dict) and 'error' not in c]
            print(f"[Generate Characters] Valid characters: {len(valid_characters)}")
            
            if not valid_characters:
                print(f"[Generate Characters] No valid characters to save")
                
            existing_chars = Character.query.filter_by(
                project_id=project.id,
                episode_number=episode.episode_number
            ).all()
            
            if existing_chars:
                print(f"[Generate Characters] 该集角色已存在，无需重复保存，共{len(existing_chars)}个角色")
            else:
                # 映射角色数据并保存到数据库
                for i, char in enumerate(valid_characters):
                    char_name = char.get('identifier_in_scene', char.get('name', f'角色{i+1}'))
                    
                    # 从description中提取信息
                    desc = char.get('description', '')
                    static_desc = char.get('static_features', '')
                    dynamic_desc = char.get('dynamic_features', '')
                    
                    new_char = Character(
                        name=char_name,
                        role='主角' if i == 0 else '配角',
                        description=static_desc + '\n' + dynamic_desc if static_desc or dynamic_desc else desc,
                        appearance=desc,
                            personality=dynamic_desc[:200] if dynamic_desc else '',
                            color='#4F46E5',
                            project_id=project.id,
                            episode_number=episode.episode_number
                        )
                    db.session.add(new_char)
                    print(f"[Generate Characters] Added character: {char_name}")
                
                db.session.commit()
                print(f"[Generate Characters] 已保存{len(valid_characters)}个角色到数据库")
        except Exception as char_err:
            print(f"[Generate Characters] 保存角色到数据库失败: {char_err}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
        
        # 更新分集状态
        episode.generation_characters_status = 'completed'
        episode.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'message': '角色信息生成成功',
            'characters': characters,
            'characters_file': '/generation/' + str(episode_id) + '/characters.json',
            'task_id': task_id
        })

    except Exception as e:
        print(f"[Generate Characters] 生成角色信息失败: {e}")
        traceback.print_exc()
        episode.generation_characters_status = 'failed'
        episode.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'error': f'生成角色信息失败: {str(e)}'}), 500


@bp.route('/api/episodes/<int:episode_id>/generate/portraits', methods=['POST'])
@login_required
def generate_portraits(episode_id):
    """生成角色肖像（调用后端API）"""
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403

    print(f"[Generate Portraits] Starting character portraits generation for episode {episode_id}")

    try:
        # 获取后端API主机
        api_host = get_backend_api_host()
        
        # 获取或创建生成任务
        task_id = get_or_create_generation_task(episode_id, episode, api_host)
        if not task_id:
            raise Exception("Failed to get or create generation task")
        
        print(f"[Generate Portraits] Using task ID: {task_id}")
        
        # 肖像生成需要先执行develop_story, extract_characters和generate_character_portraits步骤
        portrait_steps = [
            ('develop_story', 'story.txt'),
            ('extract_characters', 'characters.json'),
            ('generate_character_portraits', 'character_portraits_registry.json')
        ]
        
        # 执行每个步骤
        for step_name, artifact_name in portrait_steps:
            print(f"[Generate Portraits] Executing step: {step_name}")
            success, error_msg = execute_backend_step(task_id, step_name, api_host)
            
            if not success:
                # 更新分集状态为失败
                episode.generation_portraits_status = 'failed'
                episode.updated_at = datetime.utcnow()
                db.session.commit()
                
                return jsonify({
                    'error': f'角色肖像生成失败 (步骤 {step_name}): {error_msg}'
                }), 500
        
        # 下载生成的肖像注册表文件
        download_success = download_backend_artifact(episode_id, task_id, 'character_portraits_registry.json', api_host, current_user.username, episode.project_id, episode.episode_number)
        
        portraits_registry = {}
        if download_success:
            # 读取肖像注册表
            episode_dir = get_episode_dir(current_user.username, episode.project_id, episode.episode_number)
            registry_file = os.path.join(episode_dir, 'character_portraits_registry.json')
            if os.path.exists(registry_file):
                with open(registry_file, 'r', encoding='utf-8') as f:
                    portraits_registry = json.load(f)
        else:
            portraits_registry = {'error': '文件下载失败'}
        
        # 保存角色到数据库（角色管理）
        try:
            print(f"[Generate Portraits] Starting save to DB")
            
            # 读取characters.json
            characters_file = os.path.join(episode_dir, 'characters.json')
            
            characters = []
            if characters_file:
                with open(characters_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict) and 'content' in data:
                        content = data['content']
                        if isinstance(content, str):
                            characters = json.loads(content)
                        else:
                            characters = content
                    else:
                        characters = data
            
            valid_characters = [c for c in characters if isinstance(c, dict) and 'error' not in c]
            print(f"[Generate Portraits] Found {len(valid_characters)} characters in JSON")
            
            # 读取portraits_registry获取图片URL
            portraits_urls = {}
            if portraits_registry and isinstance(portraits_registry, dict):
                for char_name, portraits in portraits_registry.items():
                    if isinstance(portraits, dict):
                        front_path = portraits.get('front', {}).get('path', '')
                        side_path = portraits.get('side', {}).get('path', '')
                        back_path = portraits.get('back', {}).get('path', '')
                        
                        if front_path or side_path or back_path:
                            # 转换路径为API URL
                            def path_to_api_url(file_path):
                                if not file_path:
                                    return ''
                                # 提取相对路径: character_portraits/xxx/front.png
                                file_path = file_path.replace('\\', '/')
                                if 'character_portraits/' in file_path:
                                    rel_path = file_path.split('character_portraits/')[-1]
                                    return f"{api_host}/api/v1/generate/file?work_dir={current_user.username}/{episode.project_id}/{episode.episode_number}&path=character_portraits/{rel_path}"
                                return ''
                            
                            portraits_urls[char_name] = {
                                'front': path_to_api_url(front_path),
                                'side': path_to_api_url(side_path),
                                'back': path_to_api_url(back_path)
                            }
            
            print(f"[Generate Portraits] Portrait URLs: {portraits_urls}")
            
            existing_chars = Character.query.filter_by(
                project_id=project.id,
                episode_number=episode.episode_number
            ).all()
            
            if existing_chars:
                print(f"[Generate Portraits] 该集角色已存在，将更新头像URL，共{len(existing_chars)}个角色")
                for char in existing_chars:
                    # 尝试匹配角色名获取portrait URL
                    char_name = char.name
                    if char_name in portraits_urls:
                        urls = portraits_urls[char_name]
                        char.avatar = urls.get('front', '')
                        char.avatar_front = urls.get('front', '')
                        char.avatar_side = urls.get('side', '')
                        char.avatar_back = urls.get('back', '')
                        print(f"[Generate Portraits] Updated character {char_name} avatar URLs")
                db.session.commit()
            else:
                for i, char in enumerate(valid_characters):
                    char_name = char.get('identifier_in_scene', char.get('name', f'角色{i+1}'))
                    static_desc = char.get('static_features', '')
                    dynamic_desc = char.get('dynamic_features', '')
                    desc = char.get('description', '')
                    
                    # 获取portrait URL
                    portrait_urls = portraits_urls.get(char_name, {})
                    
                    new_char = Character(
                        name=char_name,
                        role='主角' if i == 0 else '配角',
                        description=static_desc + '\n' + dynamic_desc if static_desc or dynamic_desc else desc,
                        appearance=desc,
                        personality=dynamic_desc[:200] if dynamic_desc else '',
                        avatar=portrait_urls.get('front', ''),
                        avatar_front=portrait_urls.get('front', ''),
                        avatar_side=portrait_urls.get('side', ''),
                        avatar_back=portrait_urls.get('back', ''),
                        color='#4F46E5',
                        project_id=project.id,
                        episode_number=episode.episode_number
                    )
                    db.session.add(new_char)
                    print(f"[Generate Portraits] Added character: {char_name} with avatar URLs")
                
                db.session.commit()
                print(f"[Generate Portraits] 已保存{len(valid_characters)}个角色到数据库")
        except Exception as char_err:
            print(f"[Generate Portraits] 保存角色到数据库失败: {char_err}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
        
        # 更新分集状态
        episode.generation_portraits_status = 'completed'
        episode.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'message': '角色肖像生成成功',
            'portraits_registry': portraits_registry,
            'registry_file': '/generation/' + str(episode_id) + '/character_portraits_registry.json',
            'task_id': task_id
        })

    except Exception as e:
        print(f"[Generate Portraits] 生成角色肖像失败: {e}")
        traceback.print_exc()
        episode.generation_portraits_status = 'failed'
        episode.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'error': f'生成角色肖像失败: {str(e)}'}), 500


@bp.route('/api/episodes/<int:episode_id>/generate/scene', methods=['POST'])
@login_required
def generate_scene(episode_id):
    """生成场景（调用后端API）"""
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403

    print(f"[Generate Scene] Starting scene generation for episode {episode_id}")

    try:
        data = request.get_json()
        scene_index = data.get('scene_index', 0)

        # 获取后端API主机
        api_host = get_backend_api_host()
        
        # 获取或创建生成任务
        task_id = get_or_create_generation_task(episode_id, episode, api_host)
        if not task_id:
            raise Exception("Failed to get or create generation task")
        
        print(f"[Generate Scene] Using task ID: {task_id}, scene_index: {scene_index}")
        
        # 场景生成包含四个步骤：write_script, design_storyboard, decompose_visual_descriptions, construct_camera_tree
        scene_steps = [
            ('write_script', 'script.json'),
            ('design_storyboard', 'storyboard.json'),
            ('decompose_visual_descriptions', 'shot_descriptions.json'),
            ('construct_camera_tree', 'camera_tree.json')
        ]
        
        # 执行每个步骤
        for step_name, artifact_name in scene_steps:
            print(f"[Generate Scene] Executing step: {step_name}")
            success, error_msg = execute_backend_step(task_id, step_name, api_host)
            
            if not success:
                # 更新分集状态为失败
                status_key = f'generation_scene_{scene_index}_status'
                setattr(episode, status_key, 'failed')
                episode.updated_at = datetime.utcnow()
                db.session.commit()
                
                return jsonify({
                    'error': f'场景生成失败 (步骤 {step_name}): {error_msg}'
                }), 500
        
        # 下载生成的文件到前端目录
        episode_dir = get_episode_dir(current_user.username, episode.project_id, episode.episode_number)
        scene_dir = os.path.join(episode_dir, f'scene_{scene_index}')
        os.makedirs(scene_dir, exist_ok=True)
        
        # 后端场景目录（目前固定为scene_0）
        backend_scene_dir = 'scene_0'
        
        downloaded_files = {}
        artifacts_to_download = [
            # (后端文件路径, 本地保存路径)
            ('script.json', os.path.join(episode_dir, 'script.json')),
            (f'{backend_scene_dir}/storyboard.json', os.path.join(scene_dir, 'storyboard.json')),
            (f'{backend_scene_dir}/shot_descriptions.json', os.path.join(scene_dir, 'shot_descriptions.json')),
            (f'{backend_scene_dir}/camera_tree.json', os.path.join(scene_dir, 'camera_tree.json'))
        ]
        
        for backend_path, local_path in artifacts_to_download:
            download_success = download_backend_file(task_id, backend_path, local_path, api_host)
            if download_success:
                downloaded_files[backend_path] = local_path
                print(f"[Generate Scene] Downloaded {backend_path} to {local_path}")
            else:
                print(f"[Generate Scene] Warning: Failed to download {backend_path}")
        
        # 读取故事板和摄像机树用于返回
        storyboard = {}
        camera_tree = {}
        
        storyboard_path = os.path.join(scene_dir, 'storyboard.json')
        if os.path.exists(storyboard_path):
            with open(storyboard_path, 'r', encoding='utf-8') as f:
                storyboard = json.load(f)
        
        camera_tree_path = os.path.join(scene_dir, 'camera_tree.json')
        if os.path.exists(camera_tree_path):
            with open(camera_tree_path, 'r', encoding='utf-8') as f:
                camera_tree = json.load(f)
        
        # 创建shots目录
        shots_dir = os.path.join(scene_dir, 'shots')
        os.makedirs(shots_dir, exist_ok=True)

        # 更新分集状态
        status_key = f'generation_scene_{scene_index}_status'
        setattr(episode, status_key, 'completed')
        episode.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'message': f'场景 {scene_index} 生成成功',
            'storyboard': storyboard,
            'camera_tree': camera_tree,
            'downloaded_files': downloaded_files,
            'scene_files': {
                'storyboard': f'/generation/{episode_id}/scene_{scene_index}/storyboard.json',
                'camera_tree': f'/generation/{episode_id}/scene_{scene_index}/camera_tree.json',
                'shot_descriptions': f'/generation/{episode_id}/scene_{scene_index}/shot_descriptions.json',
                'script': f'/generation/{episode_id}/script.json'
            },
            'task_id': task_id
        })

    except Exception as e:
        print(f"[Generate Scene] 生成场景失败: {e}")
        traceback.print_exc()
        status_key = f'generation_scene_{scene_index}_status'
        setattr(episode, status_key, 'failed')
        episode.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'error': f'生成场景失败: {str(e)}'}), 500


@bp.route('/api/episodes/<int:episode_id>/generate/shots', methods=['POST'])
@login_required
def generate_shots(episode_id):
    """生成所有镜头（调用后端API）"""
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403

    print(f"[Generate Shots] Starting shots generation for episode {episode_id}")

    try:
        data = request.get_json()
        scene_index = data.get('scene_index', 0)

        # 获取后端API主机
        api_host = get_backend_api_host()
        
        # 获取或创建生成任务
        task_id = get_or_create_generation_task(episode_id, episode, api_host)
        if not task_id:
            raise Exception("Failed to get or create generation task")
        
        print(f"[Generate Shots] Using task ID: {task_id}, scene_index: {scene_index}")
        
        # 镜头生成包含三个步骤：construct_camera_tree, generate_frames, generate_videos
        shot_steps = [
            ('construct_camera_tree', 'camera_tree'),
            ('generate_frames', 'frames'),
            ('generate_videos', 'videos')
        ]
        
        # 执行每个步骤
        for step_name, step_desc in shot_steps:
            print(f"[Generate Shots] Executing step: {step_name}")
            success, error_msg = execute_backend_step(task_id, step_name, api_host)
            
            if not success:
                # 更新分集状态为失败
                episode.generation_shots_status = 'failed'
                episode.updated_at = datetime.utcnow()
                db.session.commit()
                
                return jsonify({
                    'error': f'镜头生成失败 (步骤 {step_name}): {error_msg}'
                }), 500
        
        # 下载生成的镜头文件到前端目录
        episode_dir = get_episode_dir(current_user.username, episode.project_id, episode.episode_number)
        scene_dir = os.path.join(episode_dir, f'scene_{scene_index}')
        os.makedirs(scene_dir, exist_ok=True)
        
        # 读取shot_descriptions.json以获取镜头数量和信息
        shot_descriptions = []
        shot_descriptions_path = os.path.join(scene_dir, 'shot_descriptions.json')
        if os.path.exists(shot_descriptions_path):
            with open(shot_descriptions_path, 'r', encoding='utf-8') as f:
                shot_descriptions = json.load(f)
        else:
            print(f"[Generate Shots] Warning: shot_descriptions.json not found at {shot_descriptions_path}")
            # 尝试从后端下载
            backend_scene_dir = 'scene_0'
            shot_desc_backend_path = f'{backend_scene_dir}/shot_descriptions.json'
            download_success = download_backend_file(task_id, shot_desc_backend_path, shot_descriptions_path, api_host)
            if download_success and os.path.exists(shot_descriptions_path):
                with open(shot_descriptions_path, 'r', encoding='utf-8') as f:
                    shot_descriptions = json.load(f)
        
        shots_count = len(shot_descriptions) if shot_descriptions else 0
        print(f"[Generate Shots] Found {shots_count} shots in shot_descriptions")
        
        # 前端不需要下载任何文件，图片和视频都通过后端URL访问
        # 封面图片由后端在合成视频时自动生成 (final_video_cover.png)
        
        # 更新分集状态
        episode.generation_shots_status = 'completed'
        episode.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'message': '镜头生成成功',
            'shots_count': shots_count,
            'task_id': task_id
        })

    except Exception as e:
        print(f"[Generate Shots] 生成镜头失败: {e}")
        traceback.print_exc()
        episode.generation_shots_status = 'failed'
        episode.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'error': f'生成镜头失败: {str(e)}'}), 500


@bp.route('/api/episodes/<int:episode_id>/generate/final', methods=['POST'])
@login_required
def generate_final_video(episode_id):
    """生成最终视频（调用后端API）"""
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403

    print(f"[Generate Final Video] Starting final video generation for episode {episode_id}")

    try:
        # 获取后端API主机
        api_host = get_backend_api_host()
        
        # 获取或创建生成任务
        task_id = get_or_create_generation_task(episode_id, episode, api_host)
        if not task_id:
            raise Exception("Failed to get or create generation task")
        
        print(f"[Generate Final Video] Using task ID: {task_id}")
        
        # 执行concatenate_videos步骤
        step_name = "concatenate_videos"
        print(f"[Generate Final Video] Executing step: {step_name}")
        success, error_msg = execute_backend_step(task_id, step_name, api_host)
        
        if not success:
            # 更新分集状态为失败
            episode.generation_final_status = 'failed'
            episode.generation_status = 'failed'
            episode.updated_at = datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'error': f'最终视频生成失败: {error_msg}'
            }), 500
        
        # 前端不需要下载视频文件，视频通过后端URL访问
        # 只有 shot_descriptions.json 需要保存
        
        # 设置视频URL - 使用后端API直接访问视频文件
        video_url = f'{api_host}/api/v1/generate/file?work_dir={current_user.username}/{episode.project_id}/{episode.episode_number}&path=final_video.mp4'
        print(f"[Generate Final Video] Setting video_url for episode {episode_id}: {video_url}")
        
        # 更新分集状态
        episode.generation_final_status = 'completed'
        episode.generation_status = 'completed'
        episode.status = 'ready'  # 分集准备就绪
        episode.video_url = video_url
        episode.generation_completed_at = datetime.utcnow()
        episode.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'message': '最终视频生成成功',
            'video_url': video_url,
            'files': {
                'final_video': f'/generation/{episode_id}/final_video.mp4',
                'backend_final_video': f'{api_host}/api/v1/generate/file?work_dir={episode.project_id}/{episode.episode_number}&path=final_video.mp4'
            },
            'episode_status': 'ready',
            'task_id': task_id
        })

    except Exception as e:
        print(f"[Generate Final Video] 生成最终视频失败: {e}")
        traceback.print_exc()
        episode.generation_final_status = 'failed'
        episode.generation_status = 'failed'
        episode.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'error': f'生成最终视频失败: {str(e)}'}), 500


@bp.route('/api/episodes/<int:episode_id>/generation/status', methods=['GET'])
@login_required
def get_generation_status(episode_id):
    """获取生成状态"""
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403

    # 检查文件是否存在
    episode_dir = get_episode_dir(current_user.username, episode.project_id, episode.episode_number)
    
    print(f"[Status] Checking episode dir: {episode_dir}")
    
    story_exists = os.path.exists(os.path.join(episode_dir, 'story.txt'))
    characters_exists = os.path.exists(os.path.join(episode_dir, 'characters.json'))
    portraits_exists = os.path.exists(os.path.join(episode_dir, 'character_portraits_registry.json'))
    
    # 检查是否存在任意 scene_ 目录
    scene_exists = False
    shots_exists = False
    
    # # 检查所有可能的目录
    # for check_dir in possible_dirs:
    #     if not os.path.exists(check_dir):
    #         continue
    #     print(f"[Status] Checking directory: {check_dir}")
    #
    #     for item in os.listdir(check_dir):
    #         if os.path.isdir(os.path.join(check_dir, item)) and item.startswith('scene_'):
    #             storyboard_path = os.path.join(check_dir, item, 'storyboard.json')
    #             if os.path.exists(storyboard_path):
    #                 scene_exists = True
    #                 print(f"[Status] Found scene directory: {item}")
    #                 # 检查shots目录中是否有视频文件
    #                 shots_dir = os.path.join(check_dir, item, 'shots')
    #                 if os.path.exists(shots_dir):
    #                     for shot_item in os.listdir(shots_dir):
    #                         shot_dir = os.path.join(shots_dir, shot_item)
    #                         if os.path.isdir(shot_dir) and shot_item.startswith('shot_'):
    #                             video_path = os.path.join(shot_dir, 'video.mp4')
    #                             if os.path.exists(video_path):
    #                                 shots_exists = True
    #                                 print(f"[Status] Found video: {video_path}")
    #                                 break
    #             if shots_exists:
    #                 break
    #     if shots_exists:
    #         break
    
    final_exists = os.path.exists(os.path.join(episode_dir, 'final_video.mp4'))
    
    print(f"[Status] Episode {episode_id} files check:")
    print(f"  story.txt exists: {story_exists}")
    print(f"  characters.json exists: {characters_exists}")
    print(f"  character_portraits_registry.json exists: {portraits_exists}")
    print(f"  any scene_*/storyboard.json exists: {scene_exists}")
    print(f"  final_video.mp4 exists: {final_exists}")
    print(f"  shots_exists: {shots_exists}")
    
    # 根据文件是否存在来确定状态
    def get_status(field_name, exists):
        if not exists:
            # 文件不存在则状态应为 pending
            return 'pending'
        # 文件存在则状态为已完成
        return 'completed'
    
    status = {
        'story': get_status('generation_story_status', story_exists),
        'characters': get_status('generation_characters_status', characters_exists),
        'portraits': get_status('generation_portraits_status', portraits_exists),
        'scene_0': get_status('generation_scene_0_status', scene_exists),
        'shots': get_status('generation_shots_status', shots_exists),
        'final_video': get_status('generation_final_status', final_exists),
        'overall': getattr(episode, 'generation_status', 'pending'),
        'generation_mode': episode.generation_mode or 'step_by_step',
        'status': episode.status
    }

    print(f"[Status] Episode {episode_id} - final status: {status}")
    print(f"  shots_exists: {shots_exists}")
    
    return jsonify({
        'status': status,
        'episode': episode.to_dict()
    })



@bp.route('/api/episodes/<int:episode_id>/generation/characters', methods=['GET'])
@login_required
def get_generation_characters(episode_id):
    """获取生成的角色信息"""
    episode = Episode.query.get_or_404(episode_id)
    
    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403
    
    # 新的目录结构
    episode_dir = get_episode_dir(current_user.username, episode.project_id, episode.episode_number)
    
    try:
        characters_file = os.path.join(episode_dir, 'characters.json')
        print(f"[Get Characters] Looking for characters in: {characters_file}")

        if os.path.exists(characters_file):
            with open(characters_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 处理嵌套的JSON结构
            if isinstance(data, dict) and 'content' in data:
                content_str = data['content']
                if isinstance(content_str, str):
                    characters = json.loads(content_str)
                else:
                    characters = content_str
            else:
                characters = data
            
            # 映射字段名以适配前端
            for char in characters:
                if 'identifier_in_scene' in char:
                    char['name'] = char['identifier_in_scene']
            
            print(f"[Get Characters] Found {len(characters)} characters")
            return jsonify({'characters': characters})
        else:
            print(f"[Get Characters] characters.json not found in {episode_dir}")
            return jsonify({'characters': []})
    except Exception as e:
        print(f"读取角色信息失败: {e}")
        return jsonify({'characters': []})


@bp.route('/api/episodes/<int:episode_id>/generation/scene/<int:scene_index>', methods=['GET'])
@login_required
def get_generation_scene(episode_id, scene_index):
    """获取生成的场景信息"""
    try:
        episode = Episode.query.get_or_404(episode_id)
        
        # 验证用户是否有权访问该项目
        project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
        if not project:
            return jsonify({'error': '无权访问此分集'}), 403
        
        episode_dir = get_episode_dir(current_user.username, episode.project_id, episode.episode_number)
        scene_dir = os.path.join(episode_dir, f'scene_{scene_index}')

        scene_info = {
            'scene_index': scene_index,
            'exists': os.path.exists(scene_dir),
            'shots_count': 0,
            'files': []
        }

        if os.path.exists(scene_dir):
            # 计算shots数量
            shots_dir = os.path.join(scene_dir, 'shots')
            if os.path.exists(shots_dir):
                shot_dirs = [d for d in os.listdir(shots_dir) if os.path.isdir(os.path.join(shots_dir, d))]
                scene_info['shots_count'] = len(shot_dirs)

            # 列出文件
            for file in os.listdir(scene_dir):
                if file.endswith('.json'):
                    scene_info['files'].append(file)

        return jsonify(scene_info)
    except Exception as e:
        print(f"读取场景信息失败: {e}")
        return jsonify({'error': f'读取场景信息失败: {str(e)}'}), 500


@bp.route('/api/episodes/<int:episode_id>/generation/shots', methods=['GET'])
@login_required
def get_generation_shots(episode_id):
    """获取生成的镜头信息（按场景分组）"""
    try:
        episode = Episode.query.get_or_404(episode_id)
        
        # 验证用户是否有权访问该项目
        project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
        if not project:
            return jsonify({'error': '无权访问此分集'}), 403
        
        # 新的目录结构
        episode_dir = get_episode_dir(current_user.username, episode.project_id, episode.episode_number)
        
        if not os.path.exists(episode_dir):
            return jsonify({'scenes': []})
        
        # 查找所有 scene_ 目录
        scenes = []
        
        if os.path.exists(episode_dir):
            scene_dirs = sorted([d for d in os.listdir(episode_dir) if os.path.isdir(os.path.join(episode_dir, d)) and d.startswith('scene_')],
                               key=lambda x: int(x.replace('scene_', '')) if x.replace('scene_', '').isdigit() else 999)
            
            for scene_dir_name in scene_dirs:
                scene_path = os.path.join(episode_dir, scene_dir_name)
                scene_index = int(scene_dir_name.replace('scene_', ''))
                
                # 读取场景描述
                storyboard_path = os.path.join(scene_path, 'storyboard.json')
                scene_name = f'场景 {scene_index + 1}'
                scene_description = ''
                if os.path.exists(storyboard_path):
                    try:
                        with open(storyboard_path, 'r', encoding='utf-8') as f:
                            sb = json.load(f)
                            if isinstance(sb, list) and sb[0]:
                                scene_name = sb[0].get('scene_name', scene_name)
                                scene_description = sb[0].get('visual_desc', '')
                            elif isinstance(sb, dict):
                                scene_name = sb.get('scene_name', scene_name)
                                scene_description = sb.get('visual_desc', '')
                    except:
                        pass
                
                shots_dir = os.path.join(scene_path, 'shots')
                shots = []
                
                if os.path.exists(shots_dir):
                    shot_dirs = sorted([d for d in os.listdir(shots_dir) if os.path.isdir(os.path.join(shots_dir, d)) and d.isdigit()],
                                       key=lambda x: int(x))
                    
                    for shot_dir in shot_dirs:
                        shot_path = os.path.join(shots_dir, shot_dir)
                        shot_index = int(shot_dir)
                        
                        # 读取镜头描述
                        description_file = os.path.join(shot_path, 'shot_description.json')
                        shot_desc = f'镜头 {shot_index + 1}'
                        if os.path.exists(description_file):
                            try:
                                with open(description_file, 'r', encoding='utf-8') as f:
                                    desc = json.load(f)
                                    shot_desc = desc.get('description', desc.get('visual_desc', shot_desc))
                            except:
                                pass
                        
                        shots.append({
                            'shot_index': shot_index,
                            'description': shot_desc,
                            'has_video': os.path.exists(os.path.join(shot_path, 'video.mp4')),
                            'has_first_frame': os.path.exists(os.path.join(shot_path, 'first_frame.png')),
                            'has_last_frame': os.path.exists(os.path.join(shot_path, 'last_frame.png')),
                        })
                
                scenes.append({
                    'scene_index': scene_index,
                    'scene_name': scene_name,
                    'scene_description': scene_description,
                    'shots': shots
                })
        
        return jsonify({'scenes': scenes})
    except Exception as e:
        print(f"读取镜头信息失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'scenes': []})


@bp.route('/api/episodes/<int:episode_id>/generation/complete', methods=['POST'])
@login_required
def complete_generation(episode_id):
    """完成生成流程"""
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403

    # 更新分集状态
    episode.generation_completed_at = datetime.utcnow()
    episode.status = 'ready'
    episode.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '生成流程完成',
        'episode': episode.to_dict()
    })


# ==================== 后端API辅助函数 ====================

def get_backend_api_host():
    """获取后端API主机地址"""
    api_host = current_app.config.get('API_HOST', 'http://localhost:5001')
    print(f"[Backend API] Using API host: {api_host}")
    return api_host

def get_or_create_generation_task(episode_id, episode, api_host):
    """获取或创建生成任务"""
    # 检查是否已有任务ID
    task_id = None
    generation_config = {}
    if episode.generation_config:
        try:
            generation_config = json.loads(episode.generation_config)
            task_id = generation_config.get('backend_task_id')
        except:
            pass
    
    if task_id:
        # 验证任务是否存在
        try:
            resp = requests.get(f"{api_host}/api/v1/tasks/{task_id}", timeout=10)
            if resp.status_code == 200:
                task_data = resp.json()
                task_status = task_data.get('status')
                print(f"[Backend API] Task {task_id} status: {task_status}")
                
                # 如果任务失败或完成，需要创建新任务
                if task_status in ['failed', 'completed']:
                    print(f"[Backend API] Task {task_id} is {task_status}, creating new one")
                    task_id = None
                else:
                    print(f"[Backend API] Using existing task: {task_id}")
                    return task_id
            else:
                print(f"[Backend API] Task {task_id} not found, creating new one")
        except Exception as e:
            print(f"[Backend API] Error checking task {task_id}: {e}, creating new one")
    
    # 创建新任务
    try:
        # 构建任务数据
        idea = episode.idea or f"Episode {episode.episode_number}: {episode.title}"
        user_requirement = episode.user_requirement or ""
        style = episode.style or "anime"
        
        # 工作目录：generation_shortvideo/{username}/{project_id}/{episode_number}
        work_dir = f"generation_shortvideo/{current_user.username}/{episode.project_id}/{episode.episode_number}"
        
        task_data = {
            "idea": idea,
            "user_requirement": user_requirement,
            "style": style,
            "mode": "stepwise",
            "work_dir": work_dir
        }
        
        print(f"[Backend API] Creating new task with data: {task_data}")
        resp = requests.post(f"{api_host}/api/v1/tasks", json=task_data, timeout=30)
        
        if resp.status_code != 201:
            print(f"[Backend API] Failed to create task: {resp.status_code} - {resp.text}")
            raise Exception(f"Failed to create task: {resp.text}")
        
        result = resp.json()
        task_id = result.get('task_id')
        if not task_id:
            raise Exception("No task_id in response")
        
        # 保存任务ID到generation_config
        generation_config['backend_task_id'] = task_id
        generation_config['backend_work_dir'] = result.get('work_dir')
        episode.generation_config = json.dumps(generation_config)
        db.session.commit()
        
        print(f"[Backend API] Created new task: {task_id}")
        return task_id
        
    except Exception as e:
        print(f"[Backend API] Error creating task: {e}")
        traceback.print_exc()
        raise

def execute_backend_step(task_id, step_name, api_host, max_retries=3):
    """执行后端步骤，带重试和轮询"""
    step_url = f"{api_host}/api/v1/tasks/{task_id}/steps/{step_name}"
    
    for attempt in range(max_retries):
        print(f"[Backend API] Executing step {step_name}, attempt {attempt + 1}/{max_retries}")
        
        try:
            # 执行步骤
            resp = requests.post(step_url, timeout=30)
            
            if resp.status_code == 409:  # Conflict
                print(f"[Backend API] Step conflict, checking task status")
                # 获取任务状态
                status_resp = requests.get(f"{api_host}/api/v1/tasks/{task_id}", timeout=10)
                if status_resp.status_code == 200:
                    status_data = status_resp.json()
                    task_status = status_data.get('status')
                    print(f"[Backend API] Task status: {task_status}, current_step: {status_data.get('current_step')}, progress: {status_data.get('progress')}")
                    
                    # 如果任务失败，不视为已完成
                    if task_status == 'failed':
                        error_msg = status_data.get('error', 'Unknown error')
                        print(f"[Backend API] Task failed with error: {error_msg}")
                        # 重置任务状态以便重新运行
                        reset_url = f"{api_host}/api/v1/tasks/{task_id}/reset"
                        try:
                            requests.post(reset_url, timeout=10)
                            print(f"[Backend API] Task reset, will retry")
                        except:
                            pass
                        if attempt < max_retries - 1:
                            time.sleep(3)
                            continue
                        return False, f"Task failed: {error_msg}"
                    
                    # 对于 generate_frames 步骤，需要检查实际文件是否存在
                    if step_name == 'generate_frames':
                        # 获取工作目录
                        work_dir = status_data.get('work_dir', '')
                        if work_dir:
                            shots_dir = os.path.join(work_dir, 'scene_0', 'shots')
                            print(f"[Backend API] Checking shots directory: {shots_dir}")
                            # 检查 shots 目录和文件
                            import os as os_check
                            if os_check.exists(shots_dir):
                                shot_count = 0
                                for shot_idx in os_check.listdir(shots_dir):
                                    shot_path = os_check.join(shots_dir, shot_idx)
                                    if os_check.isdir(shot_path):
                                        # 检查关键文件是否存在
                                        first_frame = os_check.join(shot_path, 'first_frame.png')
                                        selector_output = os_check.join(shot_path, 'first_frame_selector_output.json')
                                        shot_desc = os_check.join(shot_path, 'shot_description.json')
                                        if os_check.exists(first_frame) and os_check.exists(selector_output) and os_check.exists(shot_desc):
                                            shot_count += 1
                                            print(f"[Backend API] Shot {shot_idx}: all required files exist")
                                
                                # 获取 shot_descriptions 数量
                                shot_desc_file = os.path.join(work_dir, 'scene_0', 'shot_descriptions.json')
                                expected_shots = 1
                                if os_check.exists(shot_desc_file):
                                    import json as json_check
                                    with open(shot_desc_file, 'r', encoding='utf-8') as f:
                                        shot_descs = json_check.load(f)
                                        expected_shots = len(shot_descs)
                                
                                print(f"[Backend API] Found {shot_count} completed shots, expected {expected_shots}")
                                if shot_count >= expected_shots and expected_shots > 0:
                                    print(f"[Backend API] Step {step_name} already completed (all shots have required files)")
                                    return True, None
                                else:
                                    print(f"[Backend API] Step {step_name} not complete, files missing, will re-execute")
                                    return False, "Step not complete, will re-execute"
                            else:
                                print(f"[Backend API] Shots directory doesn't exist, will execute step")
                                return False, "Shots directory doesn't exist, will re-execute"
                        else:
                            print(f"[Backend API] No work_dir found, will execute step")
                            return False, "No work_dir found, will re-execute"
                    
                    # 如果进度已达到预期，认为已完成
                    elif status_data.get('progress', 0) >= get_step_progress(step_name):
                        print(f"[Backend API] Step {step_name} appears already completed (progress >= {get_step_progress(step_name)})")
                        return True, None
                
                # 如果尝试次数用尽或遇到其他错误
                return False, f"Step conflict, task status: {status_data.get('status')}"
            
            if 200 <= resp.status_code < 300:
                print(f"[Backend API] Step {step_name} started successfully")
                
                # 轮询直到步骤完成
                max_wait_time = 300  # 5分钟最大等待
                poll_interval = 5    # 每5秒轮询一次
                
                for wait_attempt in range(max_wait_time // poll_interval):
                    time.sleep(poll_interval)
                    
                    # 检查任务状态
                    status_resp = requests.get(f"{api_host}/api/v1/tasks/{task_id}", timeout=10)
                    if status_resp.status_code != 200:
                        print(f"[Backend API] Failed to get task status: {status_resp.status_code}")
                        continue
                    
                    status_data = status_resp.json()
                    task_status = status_data.get('status')
                    progress = status_data.get('progress', 0)
                    current_step = status_data.get('current_step')
                    
                    print(f"[Backend API] Poll {wait_attempt + 1}: status={task_status}, step={current_step}, progress={progress}%")
                    
                    if task_status == 'failed':
                        error_msg = status_data.get('error', 'Unknown error')
                        print(f"[Backend API] Step {step_name} failed: {error_msg}")
                        return False, error_msg
                    
                    # 检查步骤是否完成：进度达到预期或步骤发生变化
                    if progress >= get_step_progress(step_name) or (current_step != step_name and current_step is not None):
                        print(f"[Backend API] Step {step_name} completed: progress={progress}%, step={current_step}")
                        return True, None
                
                # 超时
                print(f"[Backend API] Step {step_name} timed out after {max_wait_time} seconds")
                return False, "Step execution timed out"
                
            else:
                print(f"[Backend API] Step {step_name} failed to start: {resp.status_code} - {resp.text}")
                if attempt < max_retries - 1:
                    time.sleep(3)
                else:
                    return False, f"Failed to start step: {resp.text}"
                    
        except Exception as e:
            print(f"[Backend API] Error executing step {step_name}: {e}")
            traceback.print_exc()
            if attempt < max_retries - 1:
                time.sleep(3)
            else:
                return False, str(e)
    
    return False, "Max retries reached"

def get_step_progress(step_name):
    """获取步骤对应的预期进度"""
    progress_map = {
        'develop_story': 10,
        'extract_characters': 20,
        'generate_character_portraits': 30,
        'write_script': 40,
        'design_storyboard': 50,
        'decompose_visual_descriptions': 60,
        'construct_camera_tree': 70,
        'generate_frames': 80,
        'generate_videos': 90,
        'concatenate_videos': 100
    }
    return progress_map.get(step_name, 0)

def download_backend_file(task_id, filename, local_path, api_host):
    """从后端下载文件"""
    try:
        # 尝试直接获取文件内容
        file_url = f"{api_host}/api/v1/tasks/{task_id}/artifacts/{filename}?content=true"
        print(f"[Backend API] Downloading file: {file_url}")
        
        resp = requests.get(file_url, timeout=60)
        if resp.status_code == 200:
            # 确保目录存在
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # 检查响应类型：如果是JSON且包含content字段，提取内容
            content_type = resp.headers.get('Content-Type', '').lower()
            if 'application/json' in content_type:
                try:
                    data = resp.json()
                    # 检查是否为后端返回的包装结构
                    if isinstance(data, dict):
                        # 检查是否有content字段
                        if 'content' in data:
                            content = data['content']
                            content_type_val = data.get('type', 'text')
                            
                            # 根据type决定如何保存
                            if content_type_val == 'binary':
                                # 二进制内容需要解码
                                import base64
                                try:
                                    binary_content = base64.b64decode(content)
                                    with open(local_path, 'wb') as f:
                                        f.write(binary_content)
                                    print(f"[Backend API] Binary content extracted and saved: {local_path}")
                                    return True
                                except Exception as decode_err:
                                    print(f"[Backend API] Failed to decode binary: {decode_err}")
                                    # 如果解码失败，尝试直接写入
                                    if isinstance(content, str):
                                        content = content.encode('utf-8')
                                    with open(local_path, 'wb') as f:
                                        f.write(content)
                                    return True
                            else:
                                # 文本内容
                                if isinstance(content, str):
                                    with open(local_path, 'w', encoding='utf-8') as f:
                                        f.write(content)
                                else:
                                    with open(local_path, 'w', encoding='utf-8') as f:
                                        json.dump(content, f, ensure_ascii=False, indent=2)
                                print(f"[Backend API] Text content extracted and saved: {local_path}")
                                return True
                        elif 'path' in data and 'size' in data:
                            # 这是后端返回的文件元数据，不是实际内容
                            # 需要使用不同的API获取实际内容
                            print(f"[Backend API] Received file metadata, downloading actual content...")
                            # 使用不带 ?content=true 的方式获取实际文件
                            file_url_raw = f"{api_host}/api/v1/tasks/{task_id}/artifacts/{filename}"
                            resp_raw = requests.get(file_url_raw, timeout=60)
                            if resp_raw.status_code == 200:
                                with open(local_path, 'wb') as f:
                                    f.write(resp_raw.content)
                                print(f"[Backend API] File downloaded successfully: {local_path}")
                                return True
                            else:
                                print(f"[Backend API] Failed to download actual file: {resp_raw.status_code}")
                                return False
                except Exception as json_err:
                    print(f"[Backend API] Failed to parse JSON response: {json_err}, falling back to raw content")
            
            # 默认写入原始内容
            with open(local_path, 'wb') as f:
                f.write(resp.content)
            print(f"[Backend API] File downloaded successfully: {local_path}")
            return True
        else:
            print(f"[Backend API] Failed to download file: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"[Backend API] Error downloading file {filename}: {e}")
        traceback.print_exc()
        return False

def download_backend_artifact(episode_id, task_id, artifact_name, api_host, username=None, project_id=None, episode_number=None):
    """下载后端生成的文件到前端目录"""
    # 前端目录结构：generation_shortvideo/{username}/{project_id}/{episode_number}
    if username is None or project_id is None or episode_number is None:
        # 如果没有提供，从数据库获取
        episode = Episode.query.get(episode_id)
        if episode:
            project = Project.query.get(episode.project_id)
            if project and project.creator:
                username = project.creator.username
            else:
                username = 'unknown'
            project_id = episode.project_id
            episode_number = episode.episode_number
    
    local_dir = get_episode_dir(username, project_id, episode_number)
    local_path = os.path.join(local_dir, artifact_name)
    
    return download_backend_file(task_id, artifact_name, local_path, api_host)

# ==================== 单步生成接口实现 ====================

@bp.route('/generation/<int:episode_id>/<path:filename>')
@login_required
def serve_generation_file(episode_id, filename):
    """提供生成文件的访问"""
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return "无权访问此文件", 403

    # 新的目录结构
    file_path = os.path.join(get_episode_dir(current_user.username, episode.project_id, episode.episode_number), filename)
    
    if not os.path.exists(file_path):
        return "文件不存在", 404

    # 根据文件类型返回内容
    if filename.endswith('.json'):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify(json.loads(content))
    elif filename.endswith('.txt'):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    else:
        # 对于图片和视频文件，直接提供文件
        return send_file(file_path)