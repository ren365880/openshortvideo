import base64
import cv2
from typing import List, Literal, Optional, Union
from PIL import Image

from database import get_db  # 新增导入
from utils.image import download_image



class ImageOutput:
    fmt: Literal["b64", "url", "pil", "np"]
    ext: str = "png"
    data: Union[str, Image.Image]
    image_url: str

    def __init__(
        self,
        fmt: Literal["b64", "url", "pil", "np"],
        ext: str,
        data: Union[str, Image.Image],
        image_url: str
    ):
        self.fmt = fmt
        self.ext = ext
        self.data = data
        self.image_url = image_url
        self.db = get_db()

    def save_b64(self, path: str) -> None:
        """Save a base64 encoded image to the specified path.

        Args:
            path (str): Path where the image will be saved.
        """
        with open(path, 'wb') as f:
            f.write(base64.b64decode(self.data))

    def save_url(self, path: str) -> None:
        """Download and save an image from a URL to the specified path.

        Args:
            path (str): Path where the image will be saved.
        """
        download_image(self.data, path)

    def save_pil(self, path: str) -> None:
        """Save a PIL Image to the specified path.

        Args:
            path (str): Path where the image will be saved.
        """
        self.data.save(path)

    def save_np(self, path: str) -> None:
        """Save a numpy array to the specified path.

        Args:
            path (str): Path where the image will be saved.
        """
        cv2.imencode('.png', self.data)[1].tofile(path)

    def save(self, path: str) -> None:
        print("======shy=============",path, self.image_url)
        save_func = getattr(self, f"save_{self.fmt}")
        save_func(path)

        # 保存到数据库
        if self.db:
            try:
                record_id = self.db.add_image_record(
                    local_path=path,
                    image_url=self.image_url,
                    task_id="",
                    prompt="",
                    aspect_ratio=""
                )
                print(f"图片记录已保存到数据库，ID: {record_id}, 本地路径: {path}, URL: {self.image_url}")
                print(f"✓ 图片记录已保存到数据库，ID: {record_id}")
            except Exception as e:
                print(f"保存到数据库失败: {e}")
                print(f"⚠ 保存到数据库失败: {e}")