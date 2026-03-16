import io
import random
from pathlib import Path
from typing import List, Tuple
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

    def generate_battle_image(self, region: str, district: str, *args) -> str:
        attacker_label = "Атакующий"
        defender_label = "Оборона"
        result = "бой"
        casualties: Tuple[int, int] = (0, 0)

        if len(args) >= 7:
            attacker_label = f"{args[0]} ({args[1]})"
            defender_label = f"{args[2]} ({args[3]})"
            result = str(args[4])
            casualties = args[5] if isinstance(args[5], tuple) else (0, 0)
        elif len(args) >= 4:
            attacker_label = str(args[0])
            defender_label = str(args[1])
            result = str(args[2])
            casualties = args[3] if isinstance(args[3], tuple) else (0, 0)

        prompt = self._create_prompt(region, district, result)
        try:
            bg = self._fetch_ai_image(prompt)
            final_image = self._add_battle_overlay(
                bg,
                region,
                district,
                attacker_label,
                defender_label,
                result,
                casualties,
            )
            filename = f"battle_{random.randint(10000, 99999)}.png"
            filepath = self.assets_path / filename
            final_image.save(filepath, "PNG")
            return str(filepath)
        except Exception:
            return self._generate_fallback_image(region, district, result)

    def _create_prompt(self, region: str, district: str, result: str) -> str:
        scenes = {
            "ПОБЕДА": "victorious military offensive, dramatic smoke, armored vehicles",
            "ПОРАЖЕНИЕ": "defensive battle, heavy smoke, damaged equipment",
            "захват": "tactical city assault, military convoy, urban combat",
            "поражение": "failed assault, retreating forces, battlefield smoke",
            "бой": "active frontline battle with military vehicles",
        }
        atmosphere = scenes.get(result, scenes["бой"])
        return (
            f"Tactical war report near {district}, {region}, "
            f"{atmosphere}, drone perspective, cinematic, highly detailed"
        )

    def _fetch_ai_image(self, prompt: str) -> Image.Image:
        encoded = quote(prompt, safe="")
        url = f"{IMAGE_API.rstrip('/')}/{encoded}?width=1024&height=1024&nologo=true"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGB")

    def _add_battle_overlay(
        self,
        base_img: Image.Image,
        region: str,
        district: str,
        attacker: str,
        defender: str,
        result: str,
        casualties: Tuple[int, int],
    ) -> Image.Image:
        img = base_img.resize((1024, 1024)).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw_overlay = ImageDraw.Draw(overlay)
        draw_overlay.rectangle([0, 680, 1024, 1024], fill=(0, 0, 0, 170))
        img = Image.alpha_composite(img, overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

        font_l = self._load_font(42, bold=True)
        font_m = self._load_font(28)
        font_s = self._load_font(22)

        draw.text((35, 700), f"TACTICAL REPORT: {district}", fill=(245, 245, 245), font=font_l)
        draw.text((35, 755), f"Region: {region}", fill=(205, 215, 225), font=font_m)
        draw.text((35, 805), f"{attacker} vs {defender}", fill=(255, 220, 130), font=font_m)

        colors = {
            "ПОБЕДА": (90, 240, 90),
            "ПОРАЖЕНИЕ": (240, 95, 95),
            "захват": (125, 180, 255),
            "поражение": (240, 95, 95),
        }
        status_color = colors.get(result, (255, 255, 255))
        draw.text((560, 700), f"Result: {result}", fill=status_color, font=font_l)
        draw.text((560, 790), f"Attacker losses: {casualties[0]}", fill=(255, 140, 140), font=font_s)
        draw.text((560, 830), f"Defender losses: {casualties[1]}", fill=(255, 140, 140), font=font_s)

        return img

    def _generate_fallback_image(self, region: str, district: str, result: str) -> str:
        img = Image.new("RGB", (1024, 1024), (25, 32, 40))
        draw = ImageDraw.Draw(img)

        for i in range(0, 1024, 64):
            draw.line([(i, 0), (i, 1024)], fill=(52, 65, 80), width=1)
            draw.line([(0, i), (1024, i)], fill=(52, 65, 80), width=1)

        for _ in range(6):
            points = [(random.randint(30, 990), random.randint(30, 990)) for _ in range(5)]
            color = (random.randint(55, 95), random.randint(90, 150), random.randint(55, 95))
            draw.polygon(points, fill=color, outline=(100, 160, 100))

        title = self._load_font(52, bold=True)
        sub = self._load_font(32)
        draw.text((70, 390), "TACTICAL MAP", fill=(220, 220, 220), font=title)
        draw.text((70, 470), district, fill=(250, 250, 250), font=sub)
        draw.text((70, 520), f"{region} | {result}", fill=(255, 220, 150), font=sub)

        filepath = self.assets_path / f"fallback_{random.randint(10000, 99999)}.png"
        img.save(filepath, "PNG")
        return str(filepath)

    def generate_territory_map(self, user_id: int, *args) -> str:
        username = f"user_{user_id}"
        faction = ""
        territories: List[dict] = []

        if len(args) == 1 and isinstance(args[0], list):
            territories = args[0]
        elif len(args) >= 3 and isinstance(args[2], list):
            username = str(args[0])
            faction = str(args[1])
            territories = args[2]

        img = Image.new("RGB", (1280, 820), (18, 24, 32))
        draw = ImageDraw.Draw(img)
        draw.rectangle([40, 40, 1240, 780], fill=(38, 48, 60), outline=(110, 130, 150), width=3)

        title = self._load_font(38, bold=True)
        text_f = self._load_font(24)

        draw.text((80, 80), f"MAP: {username} {faction}".strip(), fill=(255, 225, 120), font=title)

        y = 150
        for terr in territories:
            occupied = terr.get("original_faction") != faction if faction else False
            color = (255, 130, 130) if occupied else (110, 245, 110)
            line = (
                f"- {terr['district']} ({terr['region']}) | DEF {terr.get('defense', 0)} | "
                f"FORT {terr.get('fortification', 0)} | PART {terr.get('partisan', 0)}"
            )
            draw.text((80, y), line, fill=color, font=text_f)
            y += 36
            if y > 735:
                break

        filepath = self.assets_path / f"territory_map_{user_id}.png"
        img.save(filepath, "PNG")
        return str(filepath)
