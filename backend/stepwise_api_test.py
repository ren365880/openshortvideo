#!/usr/bin/env python3
"""
简化版视频生成API客户端 - 增强日志版
"""

import json
import time
import requests
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:5001/api/v1"


def log_request(method, url, data=None):
    """记录请求信息"""
    logger.info(f"[REQUEST] {method} {url}")
    if data:
        logger.debug(f"[REQUEST BODY] {json.dumps(data, ensure_ascii=False)}")


def log_response(response):
    """记录响应信息"""
    logger.info(f"[RESPONSE] HTTP {response.status_code}")
    logger.debug(f"[RESPONSE HEADERS] {dict(response.headers)}")
    try:
        body = response.json()
        logger.debug(f"[RESPONSE BODY] {json.dumps(body, ensure_ascii=False, indent=2)}")
        return body
    except:
        logger.debug(f"[RESPONSE TEXT] {response.text}")
        return None


def get_task_status(task_id):
    """获取任务完整状态"""
    url = f"{BASE_URL}/tasks/{task_id}"
    log_request("GET", url)
    
    resp = requests.get(url)
    body = log_response(resp)
    
    if resp.status_code == 200 and body:
        logger.info(f"[TASK STATUS] ID: {body.get('task_id')}")
        logger.info(f"[TASK STATUS] Status: {body.get('status')}")
        logger.info(f"[TASK STATUS] Current Step: {body.get('current_step')}")
        logger.info(f"[TASK STATUS] Progress: {body.get('progress', 0)}%")
        logger.info(f"[TASK STATUS] Error: {body.get('error')}")
        logger.info(f"[TASK STATUS] Work Dir: {body.get('work_dir')}")
    
    return resp, body


def execute_step_with_retry(task_id, step, max_retries=3):
    """执行步骤，带重试和详细日志，添加轮询等待"""
    url = f"{BASE_URL}/tasks/{task_id}/steps/{step}"
    
    # 步骤进度映射
    step_progress_map = {
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
    
    expected_progress = step_progress_map.get(step, 0)
    
    for attempt in range(max_retries):
        logger.info(f"[STEP EXECUTION] Step: {step}, Attempt: {attempt + 1}/{max_retries}")
        
        # 执行前检查状态
        logger.info("[STEP EXECUTION] Checking task status before execution...")
        check_resp, check_data = get_task_status(task_id)
        
        if check_data:
            current_status = check_data.get('status')
            current_step = check_data.get('current_step')
            current_progress = check_data.get('progress', 0)
            logger.info(f"[STEP EXECUTION] Pre-execution status: {current_status}, step: {current_step}, progress: {current_progress}%")
            
            # 如果任务已失败，直接返回
            if current_status == 'failed':
                logger.error(f"[STEP EXECUTION] Task is already failed! Error: {check_data.get('error')}")
                return None
            
            # 如果步骤似乎已经完成（进度达到预期），检查是否真的需要执行
            if current_progress >= expected_progress:
                logger.info(f"[STEP EXECUTION] Step {step} appears already completed (progress: {current_progress}% >= {expected_progress}%)")
                # 返回当前状态，但继续检查文件是否存在
                return check_data
        
        # 执行步骤
        log_request("POST", url)
        step_resp = requests.post(url)
        body = log_response(step_resp)
        
        if 200 <= step_resp.status_code < 300:
            logger.info(f"[STEP EXECUTION] Step {step} started successfully")
            
            # 修改：添加轮询等待直到步骤完成
            logger.info(f"[STEP EXECUTION] Waiting for step to complete (polling)...")
            max_wait_time = 120  # 最大等待120秒
            poll_interval = 3   # 每3秒轮询一次
            
            for wait_attempt in range(max_wait_time // poll_interval):
                time.sleep(poll_interval)
                
                # 检查执行状态
                poll_resp, poll_data = get_task_status(task_id)
                
                if not poll_data:
                    logger.error("[STEP EXECUTION] Failed to get poll data")
                    continue
                
                poll_status = poll_data.get('status')
                poll_step = poll_data.get('current_step')
                poll_progress = poll_data.get('progress', 0)
                
                logger.debug(f"[STEP EXECUTION] Poll {wait_attempt + 1}: status={poll_status}, step={poll_step}, progress={poll_progress}%")
                
                # 检查步骤执行是否失败
                if poll_status == 'failed':
                    logger.error(f"[STEP EXECUTION] Step {step} failed during execution")
                    logger.error(f"[STEP EXECUTION] Error: {poll_data.get('error')}")
                    return poll_data
                
                # 检查步骤是否完成：进度达到预期或步骤发生变化
                if poll_progress >= expected_progress or (poll_step != step and poll_step is not None):
                    logger.info(f"[STEP EXECUTION] Step {step} completed: progress={poll_progress}%, step={poll_step}")
                    return poll_data
            
            # 如果超时，检查当前状态
            logger.warning(f"[STEP EXECUTION] Step {step} timed out after {max_wait_time} seconds")
            timeout_resp, timeout_data = get_task_status(task_id)
            if timeout_data:
                logger.warning(f"[STEP EXECUTION] Final status after timeout: status={timeout_data.get('status')}, step={timeout_data.get('current_step')}, progress={timeout_data.get('progress', 0)}%")
                return timeout_data
            return None
        else:
            logger.error(f"[STEP EXECUTION] Step {step} failed to start (HTTP {step_resp.status_code})")
            logger.error(f"[STEP EXECUTION] Error: {step_resp.text}")
            
            if step_resp.status_code == 409:  # Conflict
                logger.error(f"[STEP EXECUTION] Conflict error - task may be in wrong state")
                # Get detailed status
                get_task_status(task_id)
            
            if attempt < max_retries - 1:
                logger.info(f"[STEP EXECUTION] Retrying in 3 seconds...")
                time.sleep(3)
            else:
                logger.error(f"[STEP EXECUTION] Max retries reached, giving up")
                return None
    return None

def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("视频生成API客户端启动")
    logger.info("=" * 80)
    
    # 1. 创建任务
    logger.info("\n[PHASE 1] 创建新的视频生成任务...")
    create_url = f"{BASE_URL}/tasks"
    create_data = {
        "idea": "一只猫和一只狗在花园里玩耍。",
        "user_requirement": "面向全年龄段，场景不超过1个。每个场景的镜头数不超过1个。",
        "style": "卡通风格",
        "mode": "stepwise",
        "work_dir": "generation_shortvideo/text_video_debug2xxx"
    }
    
    log_request("POST", create_url, create_data)
    response = requests.post(create_url, json=create_data)
    body = log_response(response)
    
    if not (200 <= response.status_code < 300):
        logger.error(f"创建任务失败 (HTTP {response.status_code}): {response.text}")
        return
    
    task_id = body.get("task_id")
    if not task_id:
        logger.error("未获取到任务ID")
        return
    
    logger.info(f"任务已创建，ID: {task_id}")
    logger.info(f"工作目录: {body.get('work_dir')}")
    
    # 2. 获取初始状态
    logger.info("\n[PHASE 2] 检查初始任务状态...")
    _, initial_data = get_task_status(task_id)
    
    # 3. 执行步骤化生成
    logger.info("\n[PHASE 3] 开始步骤化生成...")
    steps = [
        "develop_story",
        "extract_characters",
        "generate_character_portraits",
        "write_script",
        "design_storyboard",
        "decompose_visual_descriptions",
        "construct_camera_tree",
        "generate_frames",
        "generate_videos",
        "concatenate_videos"
    ]
    
    for i, step in enumerate(steps, 1):
        logger.info(f"\n[STEP {i}/{len(steps)}] {'='*60}")
        logger.info(f"[STEP {i}/{len(steps)}] 执行步骤: {step}")
        logger.info(f"[STEP {i}/{len(steps)}] {'='*60}")
        
        result = execute_step_with_retry(task_id, step)
        
        if result is None:
            logger.error(f"[STEP {i}/{len(steps)}] 步骤执行失败，停止流程")
            break
        
        if result.get('status') == 'failed':
            logger.error(f"[STEP {i}/{len(steps)}] 任务已失败，停止流程")
            logger.error(f"[STEP {i}/{len(steps)}] 错误信息: {result.get('error')}")
            break
        
        if result.get('status') == 'completed' and result.get('progress', 0) >= 100:
            logger.info(f"[STEP {i}/{len(steps)}] 任务已完成！进度: {result.get('progress', 0)}%")
            break
        elif result.get('status') == 'completed':
            logger.info(f"[STEP {i}/{len(steps)}] 步骤完成，继续下一个步骤...")
    
    # 4. 监控进度
    logger.info("\n[PHASE 4] 等待任务完成...")
    logger.info("开始监控任务进度...")
    
    last_status = None
    last_progress = -1
    
    while True:
        _, data = get_task_status(task_id)
        
        if not data:
            logger.error("获取任务状态失败")
            break
        
        status = data.get("status")
        progress = data.get("progress", 0)
        current_step = data.get("current_step")
        error = data.get("error")
        
        # 只在状态变化时打印
        if status != last_status or progress != last_progress:
            logger.info(f"[MONITOR] 状态: {status}, 进度: {progress:.1f}%, 当前步骤: {current_step}")
            if error:
                logger.error(f"[MONITOR] 错误: {error}")
            last_status = status
            last_progress = progress
        else:
            logger.debug(f"[MONITOR] 状态未变化: {status}, {progress}%")
        
        if status in ["completed", "failed", "cancelled"]:
            logger.info(f"\n[MONITOR] 任务最终状态: {status}")
            if status == "failed":
                logger.error(f"[MONITOR] 失败原因: {error}")
            break
        
        time.sleep(2)
    
    # 5. 下载文件
    if status == "completed":
        logger.info("\n[PHASE 5] 下载生成的文件...")
        
        artifacts_url = f"{BASE_URL}/tasks/{task_id}/artifacts"
        log_request("GET", artifacts_url)
        artifacts_resp = requests.get(artifacts_url)
        artifacts_data = log_response(artifacts_resp)
        
        if artifacts_data:
            logger.info(f"可用文件列表:")
            for file_info in artifacts_data.get('all_files', []):
                logger.info(f"  - {file_info.get('name')} ({file_info.get('size', 0)} bytes)")
        
        # 下载视频
        logger.info("\n下载最终视频...")
        video_url = f"{BASE_URL}/tasks/{task_id}/artifacts/final_video.mp4?content=true"
        log_request("GET", video_url)
        video_resp = requests.get(video_url)
        logger.info(f"[DOWNLOAD] Video response: HTTP {video_resp.status_code}, Size: {len(video_resp.content)} bytes")
        
        if video_resp.status_code == 200:
            with open("final_video.mp4", "wb") as f:
                f.write(video_resp.content)
            logger.info("视频已下载到: final_video.mp4")
        else:
            logger.error(f"下载视频失败: {video_resp.text}")
        
        # 下载其他文件
        logger.info("\n下载其他文件...")
        files_to_download = ["story.txt", "script.json", "storyboard.json"]
        for filename in files_to_download:
            file_url = f"{BASE_URL}/tasks/{task_id}/artifacts/{filename}?content=true"
            log_request("GET", file_url)
            resp = requests.get(file_url)
            
            if resp.status_code == 200:
                with open(filename, "wb") as f:
                    f.write(resp.content)
                logger.info(f"已下载: {filename} ({len(resp.content)} bytes)")
            else:
                logger.warning(f"下载失败: {filename} (HTTP {resp.status_code})")
    else:
        logger.error(f"\n任务未完成，无法下载文件。最终状态: {status}")
    
    logger.info("\n" + "=" * 80)
    logger.info("客户端执行完毕")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
