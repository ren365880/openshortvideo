import logging
import asyncio
import requests
import json
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from PIL import Image
from io import BytesIO
import tempfile
from tools.upload_image import ImageUploader

from tenacity import retry, stop_after_attempt
from interfaces.image_output import ImageOutput
from utils.retry import after_func
from utils.rate_limiter import RateLimiter
from database import get_db  # 新增导入


# 配置logging - 在模块级别设置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(),  # 输出到终端
    ]
)

class ImageGeneratorNanobananaWuYinAPI:
    """
    使用 wuyinkeji.com 提供的 nano-banana 模型生成图像的异步类。
    流程：创建任务 -> 轮询状态 -> 下载图像。
    """

    def __init__(
            self,
            api_key: str,
            rate_limiter: Optional[RateLimiter] = None,
            base_url: str = "https://api.wuyinkeji.com/api/",
            poll_interval: int = 5,
            max_poll_attempts: int = 60,
    ):
        """
        初始化图像生成器。

        Args:
            api_key: 第三方服务的API密钥。
            rate_limiter: 可选的速率限制器。
            base_url: 第三方API的基础URL。
            poll_interval: 轮询任务状态的间隔时间（秒）。
            max_poll_attempts: 最大轮询次数。
        """
        self.api_key = api_key
        self.rate_limiter = rate_limiter
        self.base_url = base_url.rstrip('/')
        self.poll_interval = poll_interval
        self.max_poll_attempts = max_poll_attempts
        # 初始化数据库连接
        try:
            self.db = get_db()
            logging.info("数据库连接成功初始化")
        except Exception as e:
            logging.warning(f"数据库连接初始化失败: {e}")
            self.db = None

    async def _get_image_url_from_local_path(self, local_path: str) -> Optional[str]:
        """
        从本地路径获取图片URL。

        Args:
            local_path: 本地图片路径

        Returns:
            图片URL，如果找不到则返回None
        """
        logging.debug(f"开始从本地路径获取URL: {local_path}")

        if not self.db:
            logging.warning("数据库未启用，无法从本地路径获取URL")
            return None

        try:
            # 获取绝对路径
            abs_path = os.path.abspath(local_path)
            logging.debug(f"绝对路径: {abs_path}")

            # 检查文件是否存在
            file_exists = os.path.exists(abs_path)
            logging.debug(f"文件是否存在: {file_exists}")

            if not file_exists:
                logging.warning(f"文件不存在: {abs_path}")

                # 尝试查找相对路径
                cwd = os.getcwd()
                logging.debug(f"当前工作目录: {cwd}")

                # 尝试相对路径
                if os.path.exists(local_path):
                    abs_path = os.path.abspath(local_path)
                    logging.info(f"使用相对路径找到文件: {abs_path}")
                else:
                    # 尝试在常见目录中查找
                    possible_paths = [
                        abs_path,
                        local_path,
                        os.path.join(cwd, local_path),
                        os.path.join(cwd, "generated_images", os.path.basename(local_path)),
                        os.path.join("generated_images", os.path.basename(local_path)),
                    ]

                    for path in possible_paths:
                        if os.path.exists(path):
                            abs_path = os.path.abspath(path)
                            logging.info(f"在备用路径找到文件: {abs_path}")
                            break

            # 再次检查文件是否存在
            if not os.path.exists(abs_path):
                logging.error(f"文件不存在，无法继续: {abs_path}")
                return None

            # 获取文件信息
            file_size = os.path.getsize(abs_path)
            logging.debug(f"文件大小: {file_size} bytes")

            # 从数据库查询URL
            logging.debug(f"查询数据库，路径: {abs_path}")

            # 假设数据库对象有get_upload_url方法
            try:
                if hasattr(self.db, 'get_upload_url'):
                    url = self.db.get_upload_url(abs_path)
                    logging.debug(f"数据库查询结果: {url}")
                elif hasattr(self.db, 'get_image_by_path'):
                    image_info = self.db.get_image_by_path(abs_path)
                    url = image_info.get('upload_url') if image_info else None
                    logging.debug(f"数据库查询结果: {url}")
                    logging.debug(f"完整图片信息: {image_info}")
                else:
                    # 尝试直接查询数据库
                    import sqlite3
                    db_path = "images.db"
                    if os.path.exists(db_path):
                        conn = sqlite3.connect(db_path)
                        cursor = conn.cursor()
                        cursor.execute('SELECT image_url FROM images WHERE local_path = ?', (abs_path,))
                        result = cursor.fetchone()
                        conn.close()
                        url = result[0] if result else None
                        logging.debug(f"直接数据库查询结果: {url}")
                    else:
                        logging.error(f"数据库文件不存在: {db_path}")
                        return None
            except Exception as db_error:
                logging.error(f"数据库查询错误: {db_error}")
                return None

            if url:
                logging.info(f"从数据库找到URL: {url} 对应路径: {abs_path}")
                return url
            else:
                logging.warning(f"数据库中没有找到路径对应的URL: {abs_path}")

                # 尝试通过文件名查找
                filename = os.path.basename(abs_path)
                logging.debug(f"尝试通过文件名查找: {filename}")

                try:
                    if hasattr(self.db, 'search_images'):
                        images = self.db.search_images(filename)
                        for img in images:
                            if img.get('local_path') and os.path.basename(img['local_path']) == filename:
                                url = img.get('upload_url')
                                if url:
                                    logging.info(f"通过文件名找到URL: {url}")
                                    return url
                except Exception as e:
                    logging.debug(f"文件名查找失败: {e}")

                # 可以在这里实现自动上传并保存到数据库
                logging.info(f"文件存在但数据库无记录，需要上传: {abs_path}")

                # 尝试上传图片
                try:
                    pil_image = Image.open(abs_path)
                    upload_url = await self._upload_image(pil_image)

                    if upload_url:
                        logging.info(f"图片上传成功，URL: {upload_url}")

                        # 保存到数据库
                        try:
                            if hasattr(self.db, 'update_image_url'):
                                self.db.update_image_url(abs_path, upload_url)
                                logging.info(f"已更新数据库记录: {abs_path} -> {upload_url}")
                            elif hasattr(self.db, 'add_image'):
                                self.db.add_image(
                                    local_path=abs_path,
                                    upload_url=upload_url,
                                    metadata={"auto_uploaded": True}
                                )
                                logging.info(f"已添加数据库记录: {abs_path}")
                        except Exception as save_error:
                            logging.error(f"保存到数据库失败: {save_error}")

                        return upload_url
                except Exception as upload_error:
                    logging.error(f"图片上传失败: {upload_error}")

                return None

        except Exception as e:
            logging.error(f"从本地路径获取URL失败: {e}", exc_info=True)
            return None

    async def _upload_image(self, image: Image.Image) -> str:
        """
        将PIL Image上传到Supabase存储并返回URL。
        使用ImageUploader工具从配置文件加载认证信息。
        """
        logging.info("开始上传图片到Supabase...")

        # 1. 将PIL Image保存到临时文件
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
            temp_path = tmp_file.name
            image.save(temp_path, format='PNG')
            logging.debug(f"临时图片保存至: {temp_path}")

        try:
            # 2. 导入ImageUploader（假设项目结构支持）
            # 3. 获取配置路径（默认使用类属性或固定路径）
            config_path = getattr(self, 'config_path', 'configs/idea2video_deepseek_veo3_fast.yaml')

            # 4. 准备元数据（可从self属性获取，或自定义默认值）
            title = getattr(self, 'upload_title', 'AI生成图片')
            description = getattr(self, 'upload_description', '由Idea2Video流程生成的图片')
            category = getattr(self, 'upload_category', 'knowledge')
            tags = getattr(self, 'upload_tags', ['ai', 'generated'])
            is_public = getattr(self, 'upload_is_public', True)

            # 5. 创建上传器实例
            uploader = ImageUploader(
                image_path=temp_path,
                config_path=config_path,
                title=title,
                description=description,
                category=category,
                tags=tags,
                is_public=is_public
            )

            # 6. 在线程池中执行同步上传（避免阻塞事件循环）
            loop = asyncio.get_running_loop()
            success = await loop.run_in_executor(None, uploader.run)

            if success and uploader.file_url:
                logging.info(f"图片上传成功，URL: {uploader.file_url}")
                return uploader.file_url
            else:
                logging.error("图片上传失败")
                # 若需兼容原函数行为，可返回模拟URL；否则抛出异常
                raise RuntimeError("图片上传失败")

        except Exception as e:
            logging.error(f"上传过程中发生异常: {e}")
            # 可选择返回模拟URL（原函数行为）
            # import uuid
            # return f"https://example.com/{uuid.uuid4()}.png"
            raise
        finally:
            # 7. 清理临时文件
            if os.path.exists(temp_path):
                os.unlink(temp_path)
                logging.debug(f"临时文件已删除: {temp_path}")

    @retry(stop=stop_after_attempt(1), after=after_func)
    async def generate_single_image(
            self,
            prompt: str,
            reference_image_paths: List[str] = [],
            aspect_ratio: Optional[str] = "16:9",
            **kwargs,
    ) -> ImageOutput:
        """
        异步生成单张图像的核心方法，适配原有接口。

        Args:
            prompt: 图像描述提示词。
            reference_image_paths: 参考图像本地路径列表（暂不支持，参数保留以备后用）。
            aspect_ratio: 期望的图像宽高比。

        Returns:
            ImageOutput: 包含PIL图像对象的输出。

        Raises:
            ValueError: 当任务失败或未生成图像时抛出。
            requests.RequestException: 当网络请求失败时抛出。
        """
        logging.info(f"调用 nano-banana API 生成图像，提示词: {prompt[:50]}...")
        logging.info(f"====================入参===========================")
        logging.info(f"====reference_image_paths=={kwargs}")
        logging.info(f"====aspect_ratio=={reference_image_paths}")
        logging.info(f"====================入参===========================")

        # 1. 创建图像生成任务
        task_id = await self._create_task(prompt, aspect_ratio,reference_image_paths)
        #task_id = """image_62438a4f-badc-4919-b712-aa1cbf39b625"""
        if task_id == "direct":
            # 直接返回的图片已在 _create_task 中处理并抛出特殊异常或返回
            # 此处为示例，假设不直接返回图片
            pass

        # 2. 轮询任务状态直至完成
        image_url = await self._poll_task_status(task_id)

        # 3. 下载图像并转换为PIL Image
        pil_image = await self._download_image(image_url, prompt, task_id)

        # 4. 返回与原有接口兼容的格式
        return ImageOutput(fmt="pil", ext="png", data=pil_image,image_url=image_url)

    async def _create_task(self, prompt: str, aspect_ratio: str,reference_image_paths:list) -> str:
        """
        异步：创建图像生成任务。
        """
        if len(reference_image_paths) !=0:
            if isinstance(reference_image_paths, list):
                new_reference_image_paths = []
                for line in reference_image_paths:
                    first_frame_url = await self._get_image_url_from_local_path(line)
                    new_reference_image_paths.append(first_frame_url)
                reference_image_paths = new_reference_image_paths

        url = f"{self.base_url}/async/image_nanoBanana2"
        data = {
            "key": self.api_key,
            "prompt": prompt,
            "urls": reference_image_paths,
            "aspectRatio": aspect_ratio
        }

        headers = {"Content-Type": "application/json"}
        logging.info(f"创建nanoBanana任务，完整参数: {json.dumps(data, ensure_ascii=False, indent=2)}")

        if self.rate_limiter:
            await self.rate_limiter.acquire()

        # 将同步的 requests.post 转换为异步执行
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(None,
                                                  lambda: requests.post(url, headers=headers, data=json.dumps(data)))
        except requests.exceptions.RequestException as e:
            logging.error(f"创建任务请求失败: {e}")
            raise

        if response.status_code != 200:
            logging.error(f"创建任务失败，状态码: {response.status_code}, 响应: {response.text}")
            raise ValueError(f"API请求失败: {response.status_code}")

        content_type = response.headers.get('content-type', '')
        if 'application/json' in content_type:
            result = response.json()
            print(f"创建任务响应: {json.dumps(result, ensure_ascii=False, indent=2)}")
            if result.get('code') == 200 and 'data' in result and 'id' in result['data']:
                task_id = result['data']['id']
                logging.info(f"任务创建成功，任务ID: {task_id}")
                print(f"✓ 任务创建成功! 任务ID: {task_id}")
                return task_id
            else:
                msg = result.get('msg', '未知错误')
                logging.error(f"任务创建API返回错误: {msg}")
                print(f"✗ 任务创建失败: {msg}")
                raise ValueError(f"任务创建失败: {msg}")
        elif 'image' in content_type:
            # 直接返回图片的情况
            # 此处可以直接处理图片，示例中我们选择抛出异常或走另一个流程
            logging.warning("API直接返回了图片，但当前流程设计为轮询任务ID模式。")
            # 可以将图片保存或直接加载，这里根据需求调整
            # pil_image = Image.open(BytesIO(response.content))
            # return ImageOutput(fmt="pil", ext="png", data=pil_image)
            raise ValueError("直接返回图片的模式未在本示例中实现，请使用轮询模式。")
        else:
            logging.error(f"未知的响应类型: {content_type}")
            raise ValueError(f"未知的API响应类型: {content_type}")

    async def _poll_task_status(self, task_id: str) -> str:
        """
        异步：轮询任务状态，直到成功或失败。

        改进版本：更健壮的状态判断，更好的调试信息。
        """
        url = f"{self.base_url}/async/detail"
        params = {"key": self.api_key, "id": task_id}

        for attempt in range(self.max_poll_attempts):
            print(f"\n--- 第 {attempt + 1} 次检查任务状态 ---")
            logging.info(f"轮询任务状态 (尝试 {attempt + 1}/{self.max_poll_attempts})，任务ID: {task_id}")

            loop = asyncio.get_event_loop()
            try:
                response = await loop.run_in_executor(None, lambda: requests.get(url, params=params))
                response.raise_for_status()
                result = response.json()
                print(f"轮询响应: {json.dumps(result, ensure_ascii=False, indent=2)}")
            except Exception as e:
                logging.warning(f"轮询请求失败: {e}，等待后重试...")
                print(f"轮询请求失败: {e}，等待后重试...")
                await asyncio.sleep(self.poll_interval)
                continue

            if result.get('code') != 200:
                error_msg = result.get('msg', '未知错误')
                logging.warning(f"轮询API返回错误: {error_msg}，等待后重试...")
                print(f"轮询API返回错误: {error_msg}，等待后重试...")
                await asyncio.sleep(self.poll_interval)
                continue

            data = result.get('data', {})
            status = data.get('status')
            result_data = data.get('result')
            image_url = result_data[0] if result_data and isinstance(result_data, list) else None
            fail_reason = data.get('fail_reason', '')
            # 更灵活的状态判断逻辑
            if status == 2:  # 完成
                if image_url and image_url.strip():
                    logging.info(f"任务完成，获取到图片URL: {image_url}")
                    print(f"✓ 任务完成，获取到图片URL: {image_url}")
                    return image_url
                else:
                    logging.warning("任务已完成，但图片URL为空，继续等待...")
                    print("任务已完成，但图片URL为空，继续等待...")
                    await asyncio.sleep(self.poll_interval)
                    continue
            elif status == 1:  # 处理中
                logging.info(f"任务正在处理中... 等待 {self.poll_interval} 秒...")
                print(f"任务正在处理中... 等待 {self.poll_interval} 秒...")
                await asyncio.sleep(self.poll_interval)
                continue
            elif status == 0:  # 可能的状态：等待中/排队中
                logging.info(f"任务排队中（状态: {status}）... 等待 {self.poll_interval} 秒...")
                print(f"任务排队中（状态: {status}）... 等待 {self.poll_interval} 秒...")
                await asyncio.sleep(self.poll_interval)
                continue
            elif status is None:
                logging.warning("任务状态为None，继续等待...")
                print("任务状态为None，继续等待...")
                await asyncio.sleep(self.poll_interval)
                continue
            elif status == 3 or status == -1:  # 可能的状态：失败
                error_msg = fail_reason or f"任务失败，状态码: {status}"
                logging.error(error_msg)
                print(f"✗ {error_msg}")
                #raise ValueError(f"图像生成任务失败: {error_msg}")
            else:
                # 未知状态，但可能仍然是处理中
                logging.warning(f"未知状态: {status}，继续等待...")
                print(f"未知状态: {status}，继续等待...")
                await asyncio.sleep(self.poll_interval)
                continue

        # 轮询超时
        error_msg = f"在 {self.max_poll_attempts * self.poll_interval} 秒后仍未获取到任务结果"
        logging.error(error_msg)
        print(f"✗ {error_msg}")
        raise TimeoutError(error_msg)

    async def _download_image(self, image_url: str, prompt: str, task_id: str) -> Image.Image:
        """
        异步：从给定的URL下载图像并转换为PIL Image对象。
        """
        logging.info(f"开始下载图像: {image_url}")
        print(f"开始下载图像: {image_url}")
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(None, lambda: requests.get(image_url, stream=True))
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.error(f"下载图像请求失败: {e}")
            print(f"✗ 下载图像请求失败: {e}")
            raise

        # 将响应内容读取到内存并转换为PIL Image
        image_data = BytesIO()
        for chunk in response.iter_content(chunk_size=8192):
            image_data.write(chunk)
        image_data.seek(0)

        pil_image = Image.open(image_data)
        print(f"✓ 图像下载成功! 尺寸: {pil_image.size}")

        # （可选）保存图像到本地，保留您原有代码的功能
        await self._save_image_to_disk(pil_image, prompt, task_id)

        return pil_image

    async def _save_image_to_disk(self, image: Image.Image, prompt: str, task_id: str):
        """
        异步：将PIL图像保存到本地目录。
        """
        try:
            os.makedirs("generated_images", exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # 简化提示词用于文件名
            safe_prompt = "".join(c for c in prompt[:30] if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_prompt = safe_prompt.replace(' ', '_') if safe_prompt else "image"
            filename = f"generated_images/{task_id}_{timestamp}_{safe_prompt}.png"
            image.save(filename, "PNG")
            logging.info(f"图像已保存至: {filename}")
            print(f"✓ 图像已保存至: {filename}")
        except Exception as e:
            logging.warning(f"保存图像到磁盘时发生错误（不影响返回）: {e}")
            print(f"⚠ 保存图像到磁盘时发生错误（不影响返回）: {e}")