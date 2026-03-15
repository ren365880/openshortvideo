import os
import logging
from agents import Screenwriter, CharacterExtractor, CharacterPortraitsGenerator
from pipelines.script2video_pipeline import Script2VideoPipeline
from interfaces import CharacterInScene
from typing import List, Dict, Optional
import asyncio
import json
from moviepy import VideoFileClip, concatenate_videoclips
import yaml
from langchain.chat_models import init_chat_model
from utils.rate_limiter import RateLimiter
import importlib


class Idea2VideoPipeline:
    def __init__(
        self,
        chat_model: str,
        mllm_model: str ,
        image_generator: str,
        video_generator: str,
        working_dir: str,
    ):
        self.chat_model = chat_model
        self.mllm_model = mllm_model
        self.image_generator = image_generator
        self.video_generator = video_generator
        self.working_dir = working_dir
        os.makedirs(self.working_dir, exist_ok=True)

        self.screenwriter = Screenwriter(chat_model=self.chat_model)
        self.character_extractor = CharacterExtractor(
            chat_model=self.chat_model)
        self.character_portraits_generator = CharacterPortraitsGenerator(
            image_generator=self.image_generator)

    @classmethod
    def init_from_config(
        cls,
        config_path: str,
        working_dir: str,
    ):
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        mllm_model_args = config["mllm_model"]["init_args"]
        mllm_model = init_chat_model(**mllm_model_args)

        chat_model_args = config["chat_model"]["init_args"]
        chat_model = init_chat_model(**chat_model_args)

        # Create separate rate limiters for each service
        chat_model_rpm = config.get("chat_model", {}).get("max_requests_per_minute", None)
        chat_model_rpd = config.get("chat_model", {}).get("max_requests_per_day", None)
        mllm_model_rpm = config.get("mllm_model", {}).get("max_requests_per_minute", None)
        mllm_model_rpd = config.get("mllm_model", {}).get("max_requests_per_day", None)
        image_generator_rpm = config.get("image_generator", {}).get("max_requests_per_minute", None)
        image_generator_rpd = config.get("image_generator", {}).get("max_requests_per_day", None)
        video_generator_rpm = config.get("video_generator", {}).get("max_requests_per_minute", None)
        video_generator_rpd = config.get("video_generator", {}).get("max_requests_per_day", None)

        chat_model_rate_limiter = RateLimiter(
            max_requests_per_minute=chat_model_rpm,
            max_requests_per_day=chat_model_rpd
        ) if (chat_model_rpm or chat_model_rpd) else None

        mllm_model_rate_limiter = RateLimiter(
            max_requests_per_minute=mllm_model_rpm,
            max_requests_per_day=mllm_model_rpd
        ) if (mllm_model_rpm or mllm_model_rpd) else None

        image_rate_limiter = RateLimiter(
            max_requests_per_minute=image_generator_rpm,
            max_requests_per_day=image_generator_rpd
        ) if (image_generator_rpm or image_generator_rpd) else None

        video_rate_limiter = RateLimiter(
            max_requests_per_minute=video_generator_rpm,
            max_requests_per_day=video_generator_rpd
        ) if (video_generator_rpm or video_generator_rpd) else None

        # Display rate limiting configuration
        if mllm_model_rate_limiter:
            limits = []
            if chat_model_rpm:
                limits.append(f"{mllm_model_rpm} req/min")
            if mllm_model_rpd:
                limits.append(f"{mllm_model_rpd} req/day")
            print(f"MLLM model rate limiting: {', '.join(limits)}")

        # Display rate limiting configuration
        if chat_model_rate_limiter:
            limits = []
            if chat_model_rpm:
                limits.append(f"{chat_model_rpm} req/min")
            if chat_model_rpd:
                limits.append(f"{chat_model_rpd} req/day")
            print(f"Chat model rate limiting: {', '.join(limits)}")

        if image_rate_limiter:
            limits = []
            if image_generator_rpm:
                limits.append(f"{image_generator_rpm} req/min")
            if image_generator_rpd:
                limits.append(f"{image_generator_rpd} req/day")
            print(f"Image generator rate limiting: {', '.join(limits)}")

        if video_rate_limiter:
            limits = []
            if video_generator_rpm:
                limits.append(f"{video_generator_rpm} req/min")
            if video_generator_rpd:
                limits.append(f"{video_generator_rpd} req/day")
            print(f"Video generator rate limiting: {', '.join(limits)}")

        image_generator_cls_module, image_generator_cls_name = config["image_generator"]["class_path"].rsplit(
            ".", 1)
        print(234,image_generator_cls_module,image_generator_cls_name)
        image_generator_cls = getattr(importlib.import_module(
            image_generator_cls_module), image_generator_cls_name)
        image_generator_args = config["image_generator"]["init_args"]
        image_generator_args["rate_limiter"] = image_rate_limiter
        print(123423,image_generator_args)
        image_generator = image_generator_cls(**image_generator_args)

        video_generator_cls_module, video_generator_cls_name = config["video_generator"]["class_path"].rsplit(
            ".", 1)
        video_generator_cls = getattr(importlib.import_module(
            video_generator_cls_module), video_generator_cls_name)
        video_generator_args = config["video_generator"]["init_args"]
        video_generator_args["rate_limiter"] = video_rate_limiter
        video_generator = video_generator_cls(**video_generator_args)

        return cls(
            mllm_model=mllm_model,
            chat_model=chat_model,
            image_generator=image_generator,
            video_generator=video_generator,
            working_dir=working_dir,
        )

    async def extract_characters(
        self,
        story: str,
    ):
        save_path = os.path.join(self.working_dir, "characters.json")

        if os.path.exists(save_path):
            with open(save_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Handle wrapped format: {"content": "...", "type": "text"}
            if isinstance(data, dict) and 'content' in data:
                content = data['content']
                if isinstance(content, str):
                    try:
                        data = json.loads(content)
                    except json.JSONDecodeError:
                        raise ValueError(f"Invalid JSON string in content field: {content[:100]}...")
                else:
                    data = content
            
            # At this point, data should be a list of character dicts
            if not isinstance(data, list):
                raise ValueError(f"Expected list of characters, got {type(data)}")
            
            characters = [CharacterInScene.model_validate(character) for character in data]
            print(f"[LOAD] Loaded {len(characters)} characters from existing file.")
        else:
            characters = await self.character_extractor.extract_characters(story)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump([character.model_dump()
                          for character in characters], f, ensure_ascii=False, indent=4)
            print(
                f"[SUCCESS] Extracted {len(characters)} characters from story and saved to {save_path}.")

        return characters

    async def generate_character_portraits(
        self,
        characters: List[CharacterInScene],
        character_portraits_registry: Optional[Dict[str, Dict[str, Dict[str, str]]]],
        style: str,
    ):
        character_portraits_registry_path = os.path.join(
            self.working_dir, "character_portraits_registry.json")
        if character_portraits_registry is None:
            if os.path.exists(character_portraits_registry_path):
                with open(character_portraits_registry_path, 'r', encoding='utf-8') as f:
                    character_portraits_registry = json.load(f)
            else:
                character_portraits_registry = {}
        
        # 检查每个角色是否缺少某个角度的图片
        tasks = []
        for character in characters:
            char_name = character.identifier_in_scene
            existing = character_portraits_registry.get(char_name, {})
            
            # 检查是否缺少某个角度（需要检查实际文件是否存在）
            needs_generation = False
            missing_views = []
            
            character_dir = os.path.join(
                self.working_dir, "character_portraits", f"{character.idx}_{char_name}")
            
            for view in ['front', 'side', 'back']:
                view_path = os.path.join(character_dir, f"{view}.png")
                if not os.path.exists(view_path):
                    needs_generation = True
                    missing_views.append(view)
            
            if needs_generation:
                print(f"[PORTRAIT] Character '{char_name}' missing views: {missing_views}, will generate")
                tasks.append(self.generate_portraits_for_single_character(character, style))
            else:
                print(f"[PORTRAIT] Character '{char_name}' has all portrait views, skipping")
        
        if tasks:
            for future in asyncio.as_completed(tasks):
                result = await future
                for char_name, portraits in result.items():
                    # 只合并实际生成的视图
                    if char_name not in character_portraits_registry:
                        character_portraits_registry[char_name] = {}
                    
                    for view in ['front', 'side', 'back']:
                        if view in portraits and portraits[view].get('path'):
                            character_portraits_registry[char_name][view] = portraits[view]
                
                with open(character_portraits_registry_path, 'w', encoding='utf-8') as f:
                    json.dump(character_portraits_registry,
                              f, ensure_ascii=False, indent=4)

            print(
                f"[SUCCESS] Completed character portrait generation for {len(tasks)} characters.")
        else:
            print(
                "[SKIP] All characters already have portraits, skipping portrait generation.")

        return character_portraits_registry

    async def develop_story(
        self,
        idea: str,
        user_requirement: str,
    ):
        save_path = os.path.join(self.working_dir, "story.txt")
        if os.path.exists(save_path):
            with open(save_path, "r", encoding="utf-8") as f:
                story = f.read()
                print(f"[LOAD] Loaded story from existing file.")
        else:
            print("[STORY] Developing story...")
            story = await self.screenwriter.develop_story(idea=idea, user_requirement=user_requirement)
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(story)
                print(f"[SUCCESS] Developed story and saved to {save_path}.")

        return story

    async def write_script_based_on_story(
        self,
        story: str,
        user_requirement: str,
    ):
        save_path = os.path.join(self.working_dir, "script.json")
        if os.path.exists(save_path):
            with open(save_path, "r", encoding="utf-8") as f:
                script = json.load(f)
                print(f"[LOAD] Loaded script from existing file.")
        else:
            print("[SCRIPT] Writing script based on story...")
            script = await self.screenwriter.write_script_based_on_story(story=story, user_requirement=user_requirement)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(script, f, ensure_ascii=False, indent=4)
                print(f"[SUCCESS] Written script based on story and saved to {save_path}.")
        return script

    async def generate_portraits_for_single_character(
        self,
        character: CharacterInScene,
        style: str,
    ):
        character_dir = os.path.join(
            self.working_dir, "character_portraits", f"{character.idx}_{character.identifier_in_scene}")
        os.makedirs(character_dir, exist_ok=True)
        
        result = {}

        front_portrait_path = os.path.join(character_dir, "front.png")
        if os.path.exists(front_portrait_path):
            print(f"[PORTRAIT] {character.identifier_in_scene} front.png already exists, skipping")
            result["front"] = {
                "path": front_portrait_path,
                "description": f"A front view portrait of {character.identifier_in_scene}.",
            }
        else:
            try:
                front_portrait_output = await self.character_portraits_generator.generate_front_portrait(character, style)
                front_portrait_output.save(front_portrait_path)
                result["front"] = {
                    "path": front_portrait_path,
                    "description": f"A front view portrait of {character.identifier_in_scene}.",
                }
                print(f"[PORTRAIT] Generated front.png for {character.identifier_in_scene}")
            except Exception as e:
                print(f"[PORTRAIT] Failed to generate front.png for {character.identifier_in_scene}: {e}")

        side_portrait_path = os.path.join(character_dir, "side.png")
        if os.path.exists(side_portrait_path):
            print(f"[PORTRAIT] {character.identifier_in_scene} side.png already exists, skipping")
            result["side"] = {
                "path": side_portrait_path,
                "description": f"A side view portrait of {character.identifier_in_scene}.",
            }
        else:
            try:
                side_portrait_output = await self.character_portraits_generator.generate_side_portrait(character, front_portrait_path)
                side_portrait_output.save(side_portrait_path)
                result["side"] = {
                    "path": side_portrait_path,
                    "description": f"A side view portrait of {character.identifier_in_scene}.",
                }
                print(f"[PORTRAIT] Generated side.png for {character.identifier_in_scene}")
            except Exception as e:
                print(f"[PORTRAIT] Failed to generate side.png for {character.identifier_in_scene}: {e}")

        back_portrait_path = os.path.join(character_dir, "back.png")
        if os.path.exists(back_portrait_path):
            print(f"[PORTRAIT] {character.identifier_in_scene} back.png already exists, skipping")
            result["back"] = {
                "path": back_portrait_path,
                "description": f"A back view portrait of {character.identifier_in_scene}.",
            }
        else:
            try:
                back_portrait_output = await self.character_portraits_generator.generate_back_portrait(character, front_portrait_path)
                back_portrait_output.save(back_portrait_path)
                result["back"] = {
                    "path": back_portrait_path,
                    "description": f"A back view portrait of {character.identifier_in_scene}.",
                }
                print(f"[PORTRAIT] Generated back.png for {character.identifier_in_scene}")
            except Exception as e:
                print(f"[PORTRAIT] Failed to generate back.png for {character.identifier_in_scene}: {e}")

        if result:
            print(f"[OK] Completed character portrait generation for {character.identifier_in_scene}")

        return {
            character.identifier_in_scene: result
        }

    async def __call__(
        self,
        idea: str,
        user_requirement: str,
        style: str,
    ):

        story = await self.develop_story(idea=idea, user_requirement=user_requirement)

        characters = await self.extract_characters(story=story)

        character_portraits_registry = await self.generate_character_portraits(
            characters=characters,
            character_portraits_registry=None,
            style=style,
        )

        scene_scripts = await self.write_script_based_on_story(story=story, user_requirement=user_requirement)

        all_video_paths = []

        for idx, scene_script in enumerate(scene_scripts):
            scene_working_dir = os.path.join(self.working_dir, f"scene_{idx}")
            os.makedirs(scene_working_dir, exist_ok=True)
            script2video_pipeline = Script2VideoPipeline(
                mllm_model = self.mllm_model,
                chat_model=self.chat_model,
                image_generator=self.image_generator,
                video_generator=self.video_generator,
                working_dir=scene_working_dir,
            )
            final_video_path = await script2video_pipeline(
                script=scene_script,
                user_requirement=user_requirement,
                style=style,
                characters=characters,
                character_portraits_registry=character_portraits_registry,
            )
            all_video_paths.append(final_video_path)

        final_video_path = os.path.join(self.working_dir, "final_video.mp4")
        if os.path.exists(final_video_path):
            print(f"[SKIP] Skipped concatenating videos, already exists.")
        else:
            print(f"[VIDEO] Starting concatenating videos...")
            video_clips = [VideoFileClip(final_video_path)
                           for final_video_path in all_video_paths]
            final_video = concatenate_videoclips(video_clips)
            final_video.write_videofile(final_video_path)
            print(f"[OK] Concatenated videos, saved to {final_video_path}.")

        # 从视频中提取第一帧作为封面
        if final_video_path.endswith('.mp4'):
            cover_path = final_video_path.replace('.mp4', '_cover.png')
            try:
                clip = VideoFileClip(final_video_path)
                clip.save_frame(cover_path, t=0)
                clip.close()
                logging.info(f"Cover extracted successfully to {cover_path}")
            except Exception as cover_e:
                logging.warning(f"Failed to extract cover: {cover_e}")
        return final_video_path
