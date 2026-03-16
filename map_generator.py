import io
import random
from pathlib import Path
from typing import Tuple
from urllib.parse import quote

import requests
from PIL import Image, ImageDraw, ImageFont

from config import ASSETS_DIR, IMAGE_API


class BattleVisualizer:
    def __init__(self, assets_path: Path = ASSETS_DIR):
        self.assets_path = Path(assets_path)
        self.assets_path.mkdir(parents=True, exist_ok=True)
        self._font_candidates = [
            self.assets_path / "DejaVuSans.ttf",
            self.assets_path / "DejaVuSans-Bold.ttf",
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ]

    def _load_font(self, size: int, bold: bool = False):
        preferred = ["arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else ["arial.ttf", "DejaVuSans.ttf"]
        for candidate in self._font_candidates:
            if not candidate.exists():
                continue
            if any(name.lower() in candidate.name.lower() for name in preferred):
                try:
                    return ImageFont.truetype(str(candidate), size)
                except OSError:
                    continue
        for candidate in self._font_candidates:
            if candidate.exists():
                try:
                    return ImageFont.truetype(str(candidate), size)
                except OSError:
                    continue
        return ImageFont.load_default()

    def generate_battle_image(
        self,
        region: str,
        district: str,
        attacker_faction: str,
        defender_faction: str,
        result: str,
        casualties: Tuple[int, int],
    ) -> str:
        prompt = self._create_prompt(region, district, result)
        try:
            bg = self._fetch_ai_image(prompt)
            final_image = self._add_battle_overlay(
                bg, region, district, attacker_faction, defender_faction, result, casualties
            )
            filename = f"battle_{random.randint(10000, 99999)}.png"
            filepath = self.assets_path / filename
            final_image.save(filepath, "PNG")
            return str(filepath)
        except Exception:
            return self._generate_fallback_image(region, district, result)

    def _create_prompt(self, region: str, district: str, result: str) -> str:
        base_scenes = {
            "победа": "battlefield smoke, armored vehicles, soldiers, sunrise",
            "поражение": "retreating soldiers, burning vehicles, dramatic clouds",
            "захват": "urban battle operation, tactical advance, military convoy",
        }
        atmosphere = base_scenes.get(result, "military conflict scene")
        return (
            f"Tactical battlefield near {district} in {region} region, {atmosphere}, "
            f"drone perspective, cinematic lighting, realistic details"
        )

    def _fetch_ai_image(self, prompt: str) -> Image.Image:
        encoded_prompt = quote(prompt, safe="")
        base = IMAGE_API.rstrip("/") + "/"
        url = f"{base}{encoded_prompt}?width=1024&height=1024&nologo=true"
        response = requests.get(url, timeout=35)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGB")

    def _add_battle_overlay(
        self,
        base_img: Image.Image,
        region: str,
        district: str,
        att_faction: str,
        def_faction: str,
        result: str,
        casualties: Tuple[int, int],
    ) -> Image.Image:
        img = base_img.resize((1024, 1024)).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle([0, 680, 1024, 1024], fill=(0, 0, 0, 165))
        img = Image.alpha_composite(img, overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

        font_large = self._load_font(44, bold=True)
        font_medium = self._load_font(30, bold=False)
        font_small = self._load_font(24, bold=False)

        draw.text((40, 705), f"TACTICAL REPORT: {district}", fill=(245, 245, 245), font=font_large)
        draw.text((40, 760), f"Region: {region}", fill=(200, 210, 220), font=font_medium)
        draw.text((40, 810), f"{att_faction} vs {def_faction}", fill=(255, 220, 130), font=font_medium)

        colors = {"победа": (80, 230, 80), "поражение": (235, 90, 90), "захват": (120, 170, 255)}
        status_color = colors.get(result, (255, 255, 255))
        draw.text((560, 705), f"Result: {result.upper()}", fill=status_color, font=font_large)
        draw.text((560, 790), f"Attacker losses: {casualties[0]}", fill=(255, 135, 135), font=font_small)
        draw.text((560, 830), f"Defender losses: {casualties[1]}", fill=(255, 135, 135), font=font_small)

        return img

    def _generate_fallback_image(self, region: str, district: str, result: str) -> str:
        img = Image.new("RGB", (1024, 1024), (24, 30, 38))
        draw = ImageDraw.Draw(img)
        for i in range(0, 1024, 64):
            draw.line([(i, 0), (i, 1024)], fill=(50, 64, 78), width=1)
            draw.line([(0, i), (1024, i)], fill=(50, 64, 78), width=1)

        for _ in range(6):
            points = [(random.randint(20, 1000), random.randint(20, 1000)) for _ in range(5)]
            color = (
                random.randint(55, 90),
                random.randint(85, 145),
                random.randint(55, 90),
            )
            draw.polygon(points, fill=color, outline=(95, 155, 95))

        title_font = self._load_font(52, bold=True)
        sub_font = self._load_font(36, bold=False)
        draw.text((70, 380), "TACTICAL MAP", fill=(220, 220, 220), font=title_font)
        draw.text((70, 470), district, fill=(250, 250, 250), font=sub_font)
        draw.text((70, 530), f"{region} | {result.upper()}", fill=(255, 220, 140), font=sub_font)

        filepath = self.assets_path / f"tactical_{random.randint(10000, 99999)}.png"
        img.save(filepath, "PNG")
        return str(filepath)

    def generate_territory_map(self, user_id: int, territories: list) -> str:
        img = Image.new("RGB", (1200, 800), (18, 24, 30))
        draw = ImageDraw.Draw(img)
        draw.rectangle([45, 45, 1155, 755], fill=(38, 48, 58), outline=(110, 130, 150), width=3)

        font_title = self._load_font(38, bold=True)
        font_text = self._load_font(24, bold=False)
        draw.text((85, 80), f"TERRITORIES: PLAYER {user_id}", fill=(255, 225, 120), font=font_title)

        y = 155
        for terr in territories:
            color = (105, 245, 105) if terr["owner_id"] == user_id else (245, 120, 120)
            draw.text((95, y), f"- {terr['district']} ({terr['region']})", fill=color, font=font_text)
            draw.text((655, y), f"Defense: {terr['defense']}", fill=(210, 210, 210), font=font_text)
            y += 42
            if y > 720:
                break

        filepath = self.assets_path / f"territory_map_{user_id}.png"
        img.save(filepath, "PNG")
        return str(filepath)
