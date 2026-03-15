import logging
import asyncio
import json
import os
from typing import List, Optional, Union
from PIL import Image
from io import BytesIO
from tenacity import retry, stop_after_attempt
import aiohttp
import tempfile
from tools.upload_image import ImageUploader

from utils.rate_limiter import RateLimiter
from interfaces.video_output import VideoOutput
from database import get_db  # 新增导入

# 配置logging，设置为DEBUG级别以获得更详细的日志
logging.basicConfig(
    level=logging.DEBUG,  # 改为DEBUG级别
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(),
    ]
)

logger = logging.getLogger(__name__)  # 使用logger替代logging


class VideoGeneratorVeoFastAPI:
    """
    使用 wuyinkeji.com 提供的 Veo3 模型生成视频的异步类。
    """

    def __init__(
            self,
            api_key: str,
            base_url: str = "https://api.wuyinkeji.com/api",
            poll_interval: int = 5,
            max_poll_attempts: int = 120,
            rate_limiter: Optional[RateLimiter] = None,
    ):

        """
        初始化Veo3视频生成器。
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.poll_interval = poll_interval
        self.max_poll_attempts = max_poll_attempts

        # 初始化数据库连接
        try:
            self.db = get_db()
            logger.info("数据库连接成功初始化")
        except Exception as e:
            logger.warning(f"数据库连接初始化失败: {e}")
            self.db = None

        # 设置默认headers（Veo3使用application/json）
        self.headers = {
            "Authorization": api_key,
            "Content-Type": "application/json;charset=utf-8"
        }

        logger.info(f"初始化 Veo3 API，基础URL: {self.base_url}")

    @retry(stop=stop_after_attempt(1))
    async def generate_single_video(
            self,
            prompt: str = "",
            model: str = "veo3.1-fast",
            video_type: str = "text2video",
            reference_images: Union[List[Image.Image], List[str]] = None,
            first_frame_image: Optional[Union[Image.Image, str]] = None,
            last_frame_image: Optional[Union[Image.Image, str]] = None,
            ratio: str = "16:9",
            **kwargs,
    ) -> str:
        """
        异步生成单个视频的核心方法。

        Args:
            prompt: 提示词
            model: 模型名称
            video_type: 视频类型: "text2video" 或 "img2video"
            reference_images: 参考图片列表，可以是PIL Image对象或图片URL字符串
            first_frame_image: 首帧图片，可以是PIL Image对象或图片URL字符串
            last_frame_image: 尾帧图片，可以是PIL Image对象或图片URL字符串
            ratio: 视频比例 "16:9" 或 "9:16"

        Returns:
            str: 视频URL
        """
        logger.info(f"调用 Veo3 API 生成视频，提示词: {prompt[:50]}...")
        logger.info(f"模型: {model}, 类型: {video_type}, 比例: {ratio}")
        logger.info(f"====================入参===========================")
        logger.info(f"====reference_image_paths=={reference_images}")
        logger.info(f"====first_frame_image=={first_frame_image}")
        logger.info(f"====last_frame_image=={last_frame_image}")
        logger.info(f"====ratio=={ratio}")
        logger.info(f"====kwargs.keys()=={kwargs.keys()}")

        # 详细检查kwargs
        for key, value in kwargs.items():
            logger.info(f"====kwargs.{key}=={value}")
            if key == "reference_image_paths" and value:
                logger.info(f"====reference_image_paths type: {type(value)}")
                logger.info(f"====reference_image_paths length: {len(value)}")
                for i, path in enumerate(value):
                    logger.info(f"====path[{i}]: {path}")
                    logger.info(f"====path[{i}] type: {type(path)}")

        logger.info(f"====================入参===========================")

        # 处理图片参数
        first_frame_url = None
        last_frame_url = None

        # 检查是否通过kwargs传递了图片路径
        if "reference_image_paths" in kwargs and kwargs["reference_image_paths"]:
            image_paths = kwargs["reference_image_paths"]
            logger.info(f"从kwargs获取到图片路径: {image_paths}")

            # 处理首帧图片
            if len(image_paths) >= 1:
                first_frame_path = image_paths[0]
                logger.info(f"处理首帧图片路径: {first_frame_path}")

                if isinstance(first_frame_path, str):
                    first_frame_url = await self._get_image_url_from_local_path(first_frame_path)
                    if first_frame_url:
                        logger.info(f"首帧本地路径 {first_frame_path} 已转换为URL: {first_frame_url}")
                        first_frame_image = first_frame_url
                    else:
                        logger.warning(f"未找到首帧本地路径 {first_frame_path} 对应的URL")
                        # 尝试直接使用本地路径（如果是文件路径）
                        if os.path.exists(first_frame_path):
                            logger.info(f"首帧图片文件存在: {first_frame_path}")
                            # 可以尝试上传或直接使用本地文件
                            first_frame_image = first_frame_path
                else:
                    logger.info(f"首帧图片不是字符串类型，直接使用: {type(first_frame_path)}")
                    first_frame_image = first_frame_path

            # 处理尾帧图片
            if len(image_paths) >= 2:
                last_frame_path = image_paths[1]
                logger.info(f"处理尾帧图片路径: {last_frame_path}")

                if isinstance(last_frame_path, str):
                    last_frame_url = await self._get_image_url_from_local_path(last_frame_path)
                    if last_frame_url:
                        logger.info(f"尾帧本地路径 {last_frame_path} 已转换为URL: {last_frame_url}")
                        last_frame_image = last_frame_url
                    else:
                        logger.warning(f"未找到尾帧本地路径 {last_frame_path} 对应的URL")
                        # 尝试直接使用本地路径（如果是文件路径）
                        if os.path.exists(last_frame_path):
                            logger.info(f"尾帧图片文件存在: {last_frame_path}")
                            # 可以尝试上传或直接使用本地文件
                            last_frame_image = last_frame_path
                else:
                    logger.info(f"尾帧图片不是字符串类型，直接使用: {type(last_frame_path)}")
                    last_frame_image = last_frame_path

        # 如果first_frame_image或last_frame_image是PIL Image对象，需要上传
        if isinstance(first_frame_image, Image.Image):
            logger.info("首帧图片是PIL Image对象，需要上传")
            try:
                first_frame_url = await self._upload_image(first_frame_image)
                if first_frame_url:
                    logger.info(f"首帧图片上传成功，URL: {first_frame_url}")
                    first_frame_image = first_frame_url
            except Exception as e:
                logger.error(f"首帧图片上传失败: {e}")

        if isinstance(last_frame_image, Image.Image):
            logger.info("尾帧图片是PIL Image对象，需要上传")
            try:
                last_frame_url = await self._upload_image(last_frame_image)
                if last_frame_url:
                    logger.info(f"尾帧图片上传成功，URL: {last_frame_url}")
                    last_frame_image = last_frame_url
            except Exception as e:
                logger.error(f"尾帧图片上传失败: {e}")

        # 1. 创建视频生成任务
        logger.info("开始创建视频生成任务...")
        logger.info(
            f"参数: prompt={prompt[:50]}..., video_type={video_type}, first_frame={type(first_frame_image)}, last_frame={type(last_frame_image)}，reference_images={reference_images}")

        try:
            task_id = await self._create_video_task(
                prompt=prompt,
                model=model,
                video_type=video_type,
                reference_images=reference_images or [],
                first_frame_image=first_frame_image,
                last_frame_image=last_frame_image,
                ratio=ratio
            )
            logger.info(f"视频任务创建成功，任务ID: {task_id}")
        except Exception as e:
            logger.error(f"视频任务创建失败: {e}")
            raise
        task_id = "video_a1180811-98e0-40e7-a9d8-0260d00108a1"
        # 2. 轮询任务状态直到完成
        logger.info("开始轮询任务状态...")
        video_url = await self._poll_task_status(task_id)

        # 3. 返回视频输出
        return VideoOutput(fmt="url", ext="mp4", data=video_url)

    async def _get_image_url_from_local_path(self, local_path: str) -> Optional[str]:
        """
        从本地路径获取图片URL。

        Args:
            local_path: 本地图片路径

        Returns:
            图片URL，如果找不到则返回None
        """
        logger.debug(f"开始从本地路径获取URL: {local_path}")

        if not self.db:
            logger.warning("数据库未启用，无法从本地路径获取URL")
            return None

        try:
            # 获取绝对路径
            abs_path = os.path.abspath(local_path)
            logger.debug(f"绝对路径: {abs_path}")

            # 检查文件是否存在
            file_exists = os.path.exists(abs_path)
            logger.debug(f"文件是否存在: {file_exists}")

            if not file_exists:
                logger.warning(f"文件不存在: {abs_path}")

                # 尝试查找相对路径
                cwd = os.getcwd()
                logger.debug(f"当前工作目录: {cwd}")

                # 尝试相对路径
                if os.path.exists(local_path):
                    abs_path = os.path.abspath(local_path)
                    logger.info(f"使用相对路径找到文件: {abs_path}")
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
                            logger.info(f"在备用路径找到文件: {abs_path}")
                            break

            # 再次检查文件是否存在
            if not os.path.exists(abs_path):
                logger.error(f"文件不存在，无法继续: {abs_path}")
                return None

            # 获取文件信息
            file_size = os.path.getsize(abs_path)
            logger.debug(f"文件大小: {file_size} bytes")

            # 从数据库查询URL
            logger.debug(f"查询数据库，路径: {abs_path}")

            # 假设数据库对象有get_upload_url方法
            try:
                if hasattr(self.db, 'get_upload_url'):
                    url = self.db.get_upload_url(abs_path)
                    logger.debug(f"数据库查询结果: {url}")
                elif hasattr(self.db, 'get_image_by_path'):
                    image_info = self.db.get_image_by_path(abs_path)
                    url = image_info.get('upload_url') if image_info else None
                    logger.debug(f"数据库查询结果: {url}")
                    logger.debug(f"完整图片信息: {image_info}")
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
                        logger.debug(f"直接数据库查询结果: {url}")
                    else:
                        logger.error(f"数据库文件不存在: {db_path}")
                        return None
            except Exception as db_error:
                logger.error(f"数据库查询错误: {db_error}")
                return None

            if url:
                logger.info(f"从数据库找到URL: {url} 对应路径: {abs_path}")
                return url
            else:
                logger.warning(f"数据库中没有找到路径对应的URL: {abs_path}")

                # 尝试通过文件名查找
                filename = os.path.basename(abs_path)
                logger.debug(f"尝试通过文件名查找: {filename}")

                try:
                    if hasattr(self.db, 'search_images'):
                        images = self.db.search_images(filename)
                        for img in images:
                            if img.get('local_path') and os.path.basename(img['local_path']) == filename:
                                url = img.get('upload_url')
                                if url:
                                    logger.info(f"通过文件名找到URL: {url}")
                                    return url
                except Exception as e:
                    logger.debug(f"文件名查找失败: {e}")

                # 可以在这里实现自动上传并保存到数据库
                logger.info(f"文件存在但数据库无记录，需要上传: {abs_path}")

                # 尝试上传图片
                try:
                    pil_image = Image.open(abs_path)
                    upload_url = await self._upload_image(pil_image)

                    if upload_url:
                        logger.info(f"图片上传成功，URL: {upload_url}")

                        # 保存到数据库
                        try:
                            if hasattr(self.db, 'update_image_url'):
                                self.db.update_image_url(abs_path, upload_url)
                                logger.info(f"已更新数据库记录: {abs_path} -> {upload_url}")
                            elif hasattr(self.db, 'add_image'):
                                self.db.add_image(
                                    local_path=abs_path,
                                    upload_url=upload_url,
                                    metadata={"auto_uploaded": True}
                                )
                                logger.info(f"已添加数据库记录: {abs_path}")
                        except Exception as save_error:
                            logger.error(f"保存到数据库失败: {save_error}")

                        return upload_url
                except Exception as upload_error:
                    logger.error(f"图片上传失败: {upload_error}")

                return None

        except Exception as e:
            logger.error(f"从本地路径获取URL失败: {e}", exc_info=True)
            return None

    async def _create_video_task(
            self,
            prompt: str,
            model: str = "veo3.1-fast",
            video_type: str = "text2video",
            reference_images: Union[List[Image.Image], List[str]] = [],
            first_frame_image: Optional[Union[Image.Image, str]] = None,
            last_frame_image: Optional[Union[Image.Image, str]] = None,
            ratio: str = "16:9",
    ) -> int:
        """
        创建Veo3视频生成任务。
        """
        url = f"{self.base_url}/async/video_veo3.1_fast"
        # https://api.wuyinkeji.com/api/async/video_veo3.1_fast

        logger.info(f"创建Veo3任务，URL: {url}")
        logger.info(f"视频类型: {video_type}")
        logger.info(f"首帧图片类型: {type(first_frame_image)}")
        logger.info(f"尾帧图片类型: {type(last_frame_image)}")
        logger.info(f"reference_images片类型: {type(reference_images)}")
        # 构建请求数据
        data = {
            "prompt": prompt,
            "aspectRatio": ratio,
            "size": "1080p"
        }

        # 处理不同类型的图片参数
        try:
            # 1. 处理首帧图片（img2video类型必需）
            if video_type == "img2video":
                logger.info("处理img2video类型的图片参数")

                if first_frame_image is None:
                    error_msg = "img2video类型必须提供首帧图片"
                    logger.error(error_msg)
                    raise ValueError(error_msg)

                # 获取首帧图片URL
                if isinstance(first_frame_image, str):
                    first_frame_url = first_frame_image
                    logger.info(f"使用字符串形式的首帧图片: {first_frame_url[:100]}...")
                elif isinstance(first_frame_image, Image.Image):
                    logger.info("首帧图片是PIL Image对象，正在上传...")
                    first_frame_url = await self._upload_image(first_frame_image)
                    logger.info(f"首帧图片上传完成，URL: {first_frame_url[:100]}...")
                else:
                    error_msg = f"不支持的图片类型: {type(first_frame_image)}"
                    logger.error(error_msg)
                    raise ValueError(error_msg)

                data["firstFrameUrl"] = first_frame_url
                logger.info(f"设置首帧图片URL: {data['firstFrameUrl'][:100]}...")

                # 2. 处理尾帧图片（可选）
                if last_frame_image:
                    logger.info("处理尾帧图片...")

                    # 获取尾帧图片URL
                    if isinstance(last_frame_image, str):
                        last_frame_url = last_frame_image
                        logger.info(f"使用字符串形式的尾帧图片: {last_frame_url[:100]}...")
                    elif isinstance(last_frame_image, Image.Image):
                        logger.info("尾帧图片是PIL Image对象，正在上传...")
                        last_frame_url = await self._upload_image(last_frame_image)
                        logger.info(f"尾帧图片上传完成，URL: {last_frame_url[:100]}...")
                    else:
                        error_msg = f"不支持的图片类型: {type(last_frame_image)}"
                        logger.error(error_msg)
                        raise ValueError(error_msg)

                    data["lastFrameUrl"] = last_frame_url
                    logger.info(f"设置尾帧图片URL: {data['lastFrameUrl'][:100]}...")
                else:
                    logger.info("未提供尾帧图片")

            # 3. 处理参考图片（text2video类型，最多3张）
            elif video_type == "text2video" and reference_images:
                logger.info(f"处理text2video类型的参考图片，数量: {len(reference_images)}")

                if len(reference_images) > 3:
                    logger.warning(f"参考图片超过3张限制，只使用前3张")
                    reference_images = reference_images[:3]

                reference_urls = []
                for i, img in enumerate(reference_images):
                    try:
                        if isinstance(img, str):
                            img_url = img
                            logger.info(f"参考图片{i + 1}使用字符串URL: {img_url[:100]}...")
                        elif isinstance(img, Image.Image):
                            logger.info(f"参考图片{i + 1}是PIL Image对象，正在上传...")
                            img_url = await self._upload_image(img)
                            logger.info(f"参考图片{i + 1}上传完成，URL: {img_url[:100]}...")
                        else:
                            logger.warning(f"跳过不支持的图片类型: {type(img)}")
                            continue

                        reference_urls.append(img_url)
                        logger.info(f"参考图片{i + 1}URL添加成功")
                    except Exception as e:
                        logger.warning(f"参考图片{i + 1}处理失败: {e}")

                if reference_urls:
                    data["urls"] = reference_urls
                    logger.info(f"使用参考图片URLs: {data['urls'][:200]}...")
                else:
                    logger.warning("没有可用的参考图片URL")

        except Exception as e:
            logger.error(f"图片处理过程中出现错误: {e}", exc_info=True)
            raise

        logger.info(f"创建Veo3视频任务，完整参数: {json.dumps(data, ensure_ascii=False, indent=2)}")

        # # 发送请求
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                logger.debug(f"发送POST请求到: {url}")
                logger.debug(f"请求头: {self.headers}")
                logger.debug(f"请求数据: {data}")

                async with session.post(url, json=data, timeout=30) as response:
                    response_text = await response.text()
                    logger.debug(f"API响应状态: {response.status}")
                    logger.debug(f"API响应内容: {response_text}")

                    if response.status != 200:
                        logger.error(f"API请求失败，状态码: {response.status}")
                        logger.error(f"响应内容: {response_text}")
                        raise ValueError(f"API请求失败，状态码: {response.status}")

                    result = json.loads(response_text)
                    logger.debug(f"解析后的响应: {json.dumps(result, indent=2)}")

                    if result.get("code") == 200:
                        task_id = result["data"]["id"]
                        logger.info(f"Veo3视频生成任务创建成功，任务ID: {task_id}")
                        return task_id
                    else:
                        error_msg = result.get("msg", "未知错误")
                        logger.error(f"任务创建失败: {error_msg}")
                        logger.error(f"完整错误响应: {result}")
                        raise ValueError(f"任务创建失败: {error_msg}")

        except aiohttp.ClientError as e:
            logger.error(f"网络请求错误: {e}", exc_info=True)
            raise
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {e}")
            logger.error(f"原始响应: {response_text}")
            raise ValueError("API响应格式错误")
        except Exception as e:
            logger.error(f"创建任务时发生未知错误: {e}", exc_info=True)
            raise

    async def _upload_image(self, image: Image.Image) -> str:
        """
        将PIL Image上传到Supabase存储并返回URL。
        使用ImageUploader工具从配置文件加载认证信息。
        """
        logger.info("开始上传图片到Supabase...")

        # 1. 将PIL Image保存到临时文件
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
            temp_path = tmp_file.name
            image.save(temp_path, format='PNG')
            logger.debug(f"临时图片保存至: {temp_path}")

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
                logger.info(f"图片上传成功，URL: {uploader.file_url}")
                return uploader.file_url
            else:
                logger.error("图片上传失败")
                # 若需兼容原函数行为，可返回模拟URL；否则抛出异常
                raise RuntimeError("图片上传失败")

        except Exception as e:
            logger.error(f"上传过程中发生异常: {e}")
            # 可选择返回模拟URL（原函数行为）
            # import uuid
            # return f"https://example.com/{uuid.uuid4()}.png"
            raise
        finally:
            # 7. 清理临时文件
            if os.path.exists(temp_path):
                os.unlink(temp_path)
                logger.debug(f"临时文件已删除: {temp_path}")

    async def _poll_task_status(self, task_id: str) -> str:  # 参数类型改为 str
        """轮询任务状态，返回视频URL"""
        url = f"{self.base_url}/async/detail"
        params = {"id": task_id}

        for attempt in range(self.max_poll_attempts):
            try:
                async with aiohttp.ClientSession(headers=self.headers) as session:
                    async with session.get(url, params=params, timeout=10) as response:
                        result = await response.json()
                        if result.get("code") == 200:
                            data = result.get("data", {})
                            status = data.get("status")  # 0初始化 1进行中 2成功 3失败
                            video_urls = data.get("result", [])
                            message = data.get("message", "")

                            logger.info(f"任务状态: {status}, 视频URLs: {video_urls}")

                            if status == 2:  # 成功
                                if video_urls and len(video_urls) > 0:
                                    video_url = video_urls[0]
                                    logger.info(f"视频生成成功! URL: {video_url}")
                                    return video_url
                                else:
                                    logger.warning("成功状态但视频URL列表为空")
                            elif status == 3:  # 失败
                                error_msg = message or "未知失败原因"
                                logger.error(f"视频生成失败: {error_msg}")
                                raise ValueError(f"视频生成失败: {error_msg}")
                            elif status in (0, 1):  # 初始化或进行中
                                logger.info(f"任务处理中，当前状态: {status}")
                            else:
                                logger.warning(f"未知状态: {status}")
                        else:
                            logger.warning(f"查询失败: {result.get('msg')}")
            except Exception as e:
                logger.warning(f"查询异常: {e}")

            await asyncio.sleep(self.poll_interval)

        raise TimeoutError(f"任务 {task_id} 超时")

    async def get_task_details(self, task_id: str) -> dict:
        """获取任务详情，返回data部分"""
        url = f"{self.base_url}/async/detail"
        params = {"id": task_id}
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("code") == 200:
                        return result.get("data", {})
                return {}