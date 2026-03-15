import requests
import time
import json
from typing import Optional, Dict, Any, List, Union

class UnifiedGeneratorClient:
    """统一生成服务客户端"""

    def __init__(self, base_url: str, api_key: str):
        """
        :param base_url: 服务地址，例如 'http://192.168.2.15:58888'
        :param api_key: Bearer token，用于授权
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

    def _post(self, endpoint: str, data: dict) -> dict:
        """发送 POST 请求，返回 JSON 响应"""
        url = f"{self.base_url}{endpoint}"
        resp = requests.post(url, headers=self.headers, json=data)
        resp.raise_for_status()
        return resp.json()

    def submit_task(self, params: dict) -> str:
        """
        提交任务，返回 requestId
        params 中至少包含 model 和 prompt，其他参数根据任务类型可选
        """
        resp = self._post('/v1/generation/submit', params)
        return resp['requestId']

    def get_status(self, request_id: str) -> dict:
        """查询任务状态，返回完整响应"""
        return self._post('/v1/generation/status', {'requestId': request_id})

    def wait_for_result(self, request_id: str, poll_interval: float = 2.0,
                        timeout: float = 300.0) -> Dict[str, Any]:
        """
        轮询等待任务完成，返回 results 字段
        :param poll_interval: 轮询间隔（秒）
        :param timeout: 超时时间（秒）
        :return: 任务结果字典，包含 media_type 和 files 列表
        :raises TimeoutError: 超时
        :raises Exception: 任务失败时抛出异常，包含失败原因
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            resp = self.get_status(request_id)
            status = resp['status']
            if status == 'Succeed':
                return resp['results']
            elif status == 'Failed':
                reason = resp.get('reason', 'Unknown error')
                raise Exception(f"Task failed: {reason}")
            elif status in ('Pending', 'Running'):
                time.sleep(poll_interval)
            else:
                raise Exception(f"Unexpected status: {status}")
        raise TimeoutError(f"Task {request_id} timeout after {timeout}s")

    # ---------- 便捷方法 ----------
    def text_to_image(self,
                      prompt: str,
                      height: Optional[int] = None,
                      width: Optional[int] = None,
                      negative_prompt: str = "",
                      num_inference_steps: Optional[int] = None,
                      guidance_scale: Optional[float] = None,
                      seed: Optional[int] = None,
                      **kwargs) -> Dict[str, Any]:
        """文生图，返回结果"""
        params = {
            'model': 'black-forest-labs/FLUX.2-klein-4B',
            'prompt': prompt,
            'negative_prompt': negative_prompt,
            **kwargs
        }
        if height is not None:
            params['height'] = height
        if width is not None:
            params['width'] = width
        if num_inference_steps is not None:
            params['num_inference_steps'] = num_inference_steps
        if guidance_scale is not None:
            params['guidance_scale'] = guidance_scale
        if seed is not None:
            params['seed'] = seed

        request_id = self.submit_task(params)
        return self.wait_for_result(request_id)

    def image_edit(self,
                   prompt: str,
                   image_url: str,
                   height: Optional[int] = None,
                   width: Optional[int] = None,
                   negative_prompt: str = "",
                   num_inference_steps: Optional[int] = None,
                   guidance_scale: Optional[float] = None,
                   seed: Optional[int] = None,
                   **kwargs) -> Dict[str, Any]:
        """图生图（编辑），返回结果"""
        params = {
            'model': 'black-forest-labs/FLUX.2-klein-4B',
            'prompt': prompt,
            'image': image_url,
            'negative_prompt': negative_prompt,
            **kwargs
        }
        if height is not None:
            params['height'] = height
        if width is not None:
            params['width'] = width
        if num_inference_steps is not None:
            params['num_inference_steps'] = num_inference_steps
        if guidance_scale is not None:
            params['guidance_scale'] = guidance_scale
        if seed is not None:
            params['seed'] = seed

        request_id = self.submit_task(params)
        return self.wait_for_result(request_id)

    def text_to_video(self,
                      prompt: str,
                      frames: int = 49,
                      height: int = 480,
                      width: int = 832,
                      negative_prompt: str = "",
                      num_inference_steps: int = 50,
                      guidance_scale: float = 6.0,
                      motion_score: int = 30,
                      fps: int = 16,
                      seed: Optional[int] = None,
                      **kwargs) -> Dict[str, Any]:
        """文生视频，返回结果"""
        params = {
            'model': 'Efficient-Large-Model/SANA-Video_2B_480p_diffusers',
            'prompt': prompt,
            'negative_prompt': negative_prompt,
            'frames': frames,
            'height': height,
            'width': width,
            'num_inference_steps': num_inference_steps,
            'guidance_scale': guidance_scale,
            'motion_score': motion_score,
            'fps': fps,
            **kwargs
        }
        if seed is not None:
            params['seed'] = seed

        request_id = self.submit_task(params)
        return self.wait_for_result(request_id)

    def image_to_video(self,
                       prompt: str,
                       image_url: str,
                       frames: int = 49,
                       height: int = 480,
                       width: int = 832,
                       negative_prompt: str = "",
                       num_inference_steps: int = 50,
                       guidance_scale: float = 6.0,
                       motion_score: int = 30,
                       fps: int = 16,
                       seed: Optional[int] = None,
                       **kwargs) -> Dict[str, Any]:
        """图生视频，返回结果"""
        params = {
            'model': 'Efficient-Large-Model/SANA-Video_2B_480p_diffusers',
            'prompt': prompt,
            'image': image_url,
            'negative_prompt': negative_prompt,
            'frames': frames,
            'height': height,
            'width': width,
            'num_inference_steps': num_inference_steps,
            'guidance_scale': guidance_scale,
            'motion_score': motion_score,
            'fps': fps,
            **kwargs
        }
        if seed is not None:
            params['seed'] = seed

        request_id = self.submit_task(params)
        return self.wait_for_result(request_id)

# ---------- 使用示例 ----------
if __name__ == '__main__':
    # 初始化客户端
    client = UnifiedGeneratorClient(
        base_url='http://192.168.2.15:58888',
        api_key='sk-1234567890'  # 请替换为实际 token
    )
    negative_prompt = "低分辨率，低画质，肢体畸形，手指畸形，画面过饱和，蜡像感，人脸无细节，过度光滑，画面具有AI感。构图混乱。文字模糊，扭曲。"
    # 示例1：文生图
    # try:
    #     result = client.text_to_image(
    #         prompt="一位约 20 岁的中国女大学生，留着非常短的发型，散发出温柔而富有艺术气息的感觉。她的头发自然垂落，部分遮住脸颊，展现出一种帅气又迷人的气质。她拥有冷色调的白皙皮肤和精致的五官，表情略带羞涩却又隐含自信——嘴角微微歪斜，露出顽皮而青春的笑容。她穿着一件露肩上衣，露出一侧肩膀，身材比例匀称。画面为一张近距离自拍：她占据前景主体位置，背景清晰可见她的宿舍——上铺是一张整洁的床铺，铺着白色床单；书桌干净整齐，文具摆放有序；还有木制橱柜和抽屉。照片由智能手机拍摄，采用柔和均匀的环境光，色调自然、清晰度高，充满明亮活泼的青春日常氛围。",
    #         height=1024,
    #         width=1024,
    #         seed=42,
    #         negative_prompt=negative_prompt
    #     )
    #     print("文生图成功:", result['files'][0]['url'])
    # except Exception as e:
    #     print("文生图失败:", e)

    # 示例2：图生图（编辑）
    # try:
    result = client.image_edit(
        prompt="衣服换成蓝色",
        image_url="front.png",
        seed=42
    )
    print("图生图成功:", result['files'][0]['url'])
    # except Exception as e:
    #     print("图生图失败:", e)

    # # 示例3：文生视频
    # try:
    #     result = client.text_to_video(
    #         prompt="a cat playing with a ball",
    #         frames=49,
    #         height=480,
    #         width=832,
    #         seed=42
    #     )
    #     print("文生视频成功:", result['files'][0]['url'])
    # except Exception as e:
    #     print("文生视频失败:", e)
    #
    # # 示例4：图生视频
    # try:
    #     result = client.image_to_video(
    #         prompt="特写肖像。女孩带着温暖的微笑看着镜头。她的头发在风中微微飘动。肩膀随着呼吸有轻微的起伏。空中飘着柔和的雪花。阳光反射在她的皮肤上。梦幻般的氛围，背景柔焦。",
    #         image_url="i2v-1_flux-klein.png",
    #         frames=49,
    #         height=480,
    #         width=832,
    #         seed=42
    #     )
    #     print("图生视频成功:", result['files'][0]['url'])
    # except Exception as e:
    #     print("图生视频失败:", e)