import logging
import requests
import json
import os
from tenacity import retry, stop_after_attempt


@retry(stop=stop_after_attempt(3))
def download_video(url, save_path):
    try:
        logging.info(f"Downloading video from {url} to {save_path}")

        response = requests.get(url, stream=True)
        response.raise_for_status()  # 检查请求是否成功
        
        content_type = response.headers.get('Content-Type', '')
        content_length = response.headers.get('Content-Length', '')
        logging.info(f"Response Content-Type: {content_type}, Content-Length: {content_length}")

        # Check if response is JSON (error response)
        if 'application/json' in content_type or 'text/' in content_type:
            try:
                json_resp = response.json()
                logging.error(f"Received JSON response instead of video: {json_resp}")
                # Save the error response for debugging
                with open(save_path, 'w', encoding='utf-8') as f:
                    json.dump(json_resp, f, ensure_ascii=False, indent=2)
                logging.error(f"Saved error response to {save_path}")
                return
            except:
                pass

        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logging.info(f"Video downloaded successfully to {save_path}")
        
        # 从视频中提取第一帧作为封面
        if save_path.endswith('.mp4'):
            cover_path = save_path.replace('.mp4', '_cover.png')
            try:
                from moviepy import VideoFileClip
                clip = VideoFileClip(save_path)
                clip.save_frame(cover_path, t=0)
                clip.close()
                logging.info(f"Cover extracted successfully to {cover_path}")
            except Exception as cover_e:
                logging.warning(f"Failed to extract cover: {cover_e}")
    
    except Exception as e:
        logging.error(f"Error downloading video: {e}")
        raise e
