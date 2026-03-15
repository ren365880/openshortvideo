import asyncio
from pipelines.idea2video_pipeline import Idea2VideoPipeline


# # SET YOUR OWN IDEA, USER REQUIREMENT, AND STYLE HERE
# idea = \
#     """
# A beaufitul fit woman with black hair, great butt and thigs is exercising in a
# gym surrounded by glass windows with a beautiful beach view on the outside.
# She is performing glute exercises that highlight her beautiful back and sexy outfit
# and showing the audience the proper form. Between the 1 different exercises she looks
# at the camera with a gorgeous look asking the viewer understood the proper form.
# """
# user_requirement = \
#     """
# For adults, do not exceed 1 scenes. Each scene should be no more than 1 shots.
# """
# style = "Realistic, warm feel"

# SET YOUR OWN IDEA, USER REQUIREMENT, AND STYLE HERE
idea = \
    """这是一个关于剑仙与妖将的奇幻故事"""
user_requirement = \
    """面向全年龄段，场景不超过1个。每个场景的镜头数不超过1个。"""
style = "生动、温暖、充满童趣的探险风格"

async def main():
    pipeline = Idea2VideoPipeline.init_from_config(
        config_path="configs/idea2video_deepseek_veo3_fast.yaml",working_dir="D:/mywork/pythonProject/openshortvideo_finall/backend/generation_shortvideo/18409272023/2/2")
    await pipeline(idea=idea, user_requirement=user_requirement, style=style)

if __name__ == "__main__":
    asyncio.run(main())
