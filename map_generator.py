import io
import math
import os
import random
from pathlib import Path
from typing import Dict, List, Tuple

import requests
from PIL import Image, ImageDraw, ImageFont

from config import ASSETS_DIR


class BattleVisualizer:
    def __init__(self, assets_path: Path = ASSETS_DIR):
        self.assets_path = Path(assets_path)
        self.assets_path.mkdir(parents=True, exist_ok=True)

        # Координаты центров областей: (lon, lat)
        self.region_coords = {
            "Киевская": (30.5, 50.4),
            "Харьковская": (36.2, 49.9),
            "Донецкая": (37.8, 48.0),
            "Луганская": (39.3, 48.9),
            "Запорожская": (35.1, 47.8),
            "Херсонская": (33.3, 46.6),
            "Днепропетровская": (35.0, 48.4),
            "Одесская": (30.7, 46.4),
            "Львовская": (24.0, 49.8),
            "Винницкая": (28.5, 49.2),
            "Полтавская": (34.5, 49.5),
            "Сумская": (34.8, 50.9),
            "Черниговская": (31.3, 51.5),
            "Житомирская": (28.7, 50.3),
            "Ровенская": (26.2, 50.6),
            "Волынская": (25.3, 50.7),
            "Закарпатская": (22.3, 48.6),
            "Ивано-Франковская": (24.7, 48.9),
            "Тернопольская": (25.6, 49.5),
            "Хмельницкая": (27.0, 49.4),
            "Черкасская": (32.0, 49.4),
            "Кировоградская": (32.3, 48.5),
            "Николаевская": (31.9, 47.4),
            "Черновицкая": (25.9, 48.3),
        }

        self.faction_colors = {
            "Киевская": (255, 215, 0),
            "Харьковская": (0, 100, 255),
            "Донецкая": (200, 50, 50),
            "Луганская": (150, 0, 0),
            "Запорожская": (255, 140, 0),
            "Херсонская": (0, 150, 200),
            "Днепропетровская": (75, 0, 130),
            "Одесская": (0, 200, 200),
            "Львовская": (255, 20, 147),
            "Винницкая": (50, 205, 50),
            "Полтавская": (255, 215, 0),
            "Сумская": (0, 128, 128),
            "Черниговская": (139, 69, 19),
            "Житомирская": (107, 142, 35),
            "Ровенская": (218, 112, 214),
            "Волынская": (255, 165, 0),
            "Закарпатская": (30, 144, 255),
            "Ивано-Франковская": (220, 20, 60),
            "Тернопольская": (0, 206, 209),
            "Хмельницкая": (255, 105, 180),
            "Черкасская": (34, 139, 34),
            "Кировоградская": (210, 105, 30),
            "Николаевская": (100, 149, 237),
            "Черновицкая": (188, 143, 143),
        }

        self.min_lon, self.max_lon = 22.0, 40.5
        self.min_lat, self.max_lat = 44.0, 52.8

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

    def get_osm_map(self, center_lon: float, center_lat: float, zoom: int = 6) -> Image.Image:
        width, height = 1024, 1024
        static_url = (
            "https://staticmap.openstreetmap.de/staticmap.php"
            f"?center={center_lat},{center_lon}&zoom={zoom}&size={width}x{height}&maptype=mapnik"
        )

        try:
            response = requests.get(static_url, timeout=30)
            if response.status_code == 200:
                return Image.open(io.BytesIO(response.content)).convert("RGB")
        except Exception:
            pass

        return self._generate_fallback_map(width, height)

    def _generate_fallback_map(self, width: int, height: int) -> Image.Image:
        img = Image.new("RGB", (width, height), (20, 25, 30))
        draw = ImageDraw.Draw(img)

        for i in range(0, width, 64):
            draw.line([(i, 0), (i, height)], fill=(40, 50, 60), width=1)
        for i in range(0, height, 64):
            draw.line([(0, i), (width, i)], fill=(40, 50, 60), width=1)

        ukraine_outline = [
            (200, 150),
            (400, 100),
            (700, 120),
            (900, 200),
            (950, 400),
            (900, 700),
            (800, 900),
            (600, 950),
            (400, 900),
            (200, 800),
            (100, 600),
            (150, 300),
        ]
        draw.polygon(ukraine_outline, outline=(60, 80, 100), fill=(30, 40, 50))

        return img

    def latlon_to_pixel(self, lat: float, lon: float, width: int, height: int) -> Tuple[int, int]:
        x_ratio = (lon - self.min_lon) / (self.max_lon - self.min_lon)
        y_ratio = (self.max_lat - lat) / (self.max_lat - self.min_lat)

        x = int(max(0, min(width - 1, x_ratio * width)))
        y = int(max(0, min(height - 1, y_ratio * height)))
        return x, y

    def generate_battle_image(
        self,
        region: str,
        district: str,
        att_name: str,
        att_faction: str,
        def_name: str,
        def_faction: str,
        result: str,
        casualties: Tuple[int, int],
        victory: bool,
    ) -> str:
        width, height = 1200, 1200

        center_lon, center_lat = self.region_coords.get(region, (31.0, 48.5))
        img = self.get_osm_map(center_lon, center_lat, zoom=6)
        img = img.resize((width, height), Image.Resampling.LANCZOS)

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        font_title = self._load_font(46, bold=True)
        font_large = self._load_font(30, bold=True)
        font_medium = self._load_font(22)
        font_small = self._load_font(18)

        for reg, (lon, lat) in self.region_coords.items():
            x, y = self.latlon_to_pixel(lat, lon, width, height)
            color = self.faction_colors.get(reg, (100, 100, 100))

            if reg == att_faction:
                fill = (50, 200, 50, 90)
            elif reg == def_faction:
                fill = (200, 50, 50, 90)
            else:
                fill = (*color, 40)

            radius = 76 if reg in [att_faction, def_faction] else 48
            draw.ellipse(
                [x - radius, y - radius, x + radius, y + radius],
                fill=fill,
                outline=(*fill[:3], 150),
                width=3,
            )
            draw.text((x, y), reg[:9], fill=(255, 255, 255), font=font_small, anchor="mm")

        att_lon, att_lat = self.region_coords.get(att_faction, (31.0, 48.5))
        def_lon, def_lat = self.region_coords.get(def_faction, (center_lon, center_lat))

        x1, y1 = self.latlon_to_pixel(att_lat, att_lon, width, height)
        x2, y2 = self.latlon_to_pixel(def_lat, def_lon, width, height)

        dx, dy = x2 - x1, y2 - y1
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > 0:
            dx, dy = dx / dist * 70, dy / dist * 70
            x1, y1 = int(x1 + dx), int(y1 + dy)
            x2, y2 = int(x2 - dx), int(y2 - dy)

        self._draw_dashed_line(draw, x1, y1, x2, y2, (255, 255, 0), 3)
        if victory:
            self._draw_arrow(draw, x1, y1, x2, y2, (50, 255, 50), 7)
        else:
            self._draw_arrow(draw, x2, y2, x1, y1, (255, 50, 50), 7)

        battle_x = (x1 + x2) // 2 + random.randint(-30, 30)
        battle_y = (y1 + y2) // 2 + random.randint(-30, 30)
        self._draw_explosion(draw, battle_x, battle_y, (255, 100, 0) if victory else (120, 120, 120))

        panel_h = 190
        draw.rectangle([0, 0, width, panel_h], fill=(0, 0, 0, 200))
        draw.line([(0, panel_h), (width, panel_h)], fill=(255, 215, 0), width=3)

        draw.text((width // 2, 42), "⚔️ ТАКТИЧЕСКАЯ КАРТА", fill=(255, 215, 0), font=font_title, anchor="mm")
        draw.text((width // 2, 92), f"Район: {district} | Область: {region}", fill=(255, 255, 255), font=font_large, anchor="mm")

        result_color = (50, 255, 50) if victory else (255, 50, 50)
        result_text = "✅ ПРОРЫВ" if victory else "❌ ОТБОЙ"
        draw.text(
            (width // 2, 138),
            f"{att_name} ({att_faction}) → {def_name} ({def_faction})",
            fill=(210, 210, 210),
            font=font_medium,
            anchor="mm",
        )
        draw.text((width // 2, 172), result_text, fill=result_color, font=font_large, anchor="mm")

        stats_y = height - 124
        draw.rectangle([0, stats_y, width, height], fill=(0, 0, 0, 205))
        draw.line([(0, stats_y), (width, stats_y)], fill=(255, 215, 0), width=2)

        draw.text((width // 4, stats_y + 42), f"💀 Потери атаки: {casualties[0]}", fill=(255, 100, 100), font=font_medium, anchor="mm")
        draw.text((3 * width // 4, stats_y + 42), f"💀 Потери обороны: {casualties[1]}", fill=(255, 100, 100), font=font_medium, anchor="mm")
        draw.text((width // 2, stats_y + 84), f"Командир: {att_name}", fill=(100, 255, 100), font=font_medium, anchor="mm")

        out = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        filename = f"battle_{random.randint(100000, 999999)}.png"
        filepath = self.assets_path / filename
        out.save(filepath, "PNG")
        return str(filepath)

    def _draw_dashed_line(self, draw: ImageDraw.ImageDraw, x1: int, y1: int, x2: int, y2: int, color, width: int):
        dist = math.hypot(x2 - x1, y2 - y1)
        if dist <= 0:
            return

        dash, gap = 20, 10
        step = dash + gap
        count = max(1, int(dist // step))

        for i in range(count):
            start = (i * step) / dist
            end = min(((i * step) + dash) / dist, 1)
            sx = int(x1 + (x2 - x1) * start)
            sy = int(y1 + (y2 - y1) * start)
            ex = int(x1 + (x2 - x1) * end)
            ey = int(y1 + (y2 - y1) * end)
            draw.line([(sx, sy), (ex, ey)], fill=color, width=width)

    def _draw_arrow(self, draw: ImageDraw.ImageDraw, x1: int, y1: int, x2: int, y2: int, color, width: int):
        draw.line([(x1, y1), (x2, y2)], fill=color, width=width)

        angle = math.atan2(y2 - y1, x2 - x1)
        arrow_len = 28
        spread = math.pi / 6

        x3 = int(x2 - arrow_len * math.cos(angle - spread))
        y3 = int(y2 - arrow_len * math.sin(angle - spread))
        x4 = int(x2 - arrow_len * math.cos(angle + spread))
        y4 = int(y2 - arrow_len * math.sin(angle + spread))

        draw.polygon([(x2, y2), (x3, y3), (x4, y4)], fill=color)

    def _draw_explosion(self, draw: ImageDraw.ImageDraw, x: int, y: int, color):
        for r in [42, 30, 20]:
            alpha = int(255 * (42 - r) / 42)
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(*color, alpha))

        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            x2 = int(x + 50 * math.cos(rad))
            y2 = int(y + 50 * math.sin(rad))
            draw.line([(x, y), (x2, y2)], fill=(*color, 200), width=3)

    def generate_territory_map(self, user_id: int, username: str, faction: str, territories: List[dict]) -> str:
        width, height = 1200, 1200

        center_lon, center_lat = 31.0, 48.5
        img = self.get_osm_map(center_lon, center_lat, zoom=6)
        img = img.resize((width, height), Image.Resampling.LANCZOS)

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        font_title = self._load_font(36, bold=True)
        font_text = self._load_font(20)

        draw.rectangle([0, 0, width, 105], fill=(0, 0, 0, 200))
        draw.text((width // 2, 32), "🗺️ КАРТА ВЛАДЕНИЙ", fill=(255, 215, 0), font=font_title, anchor="mm")
        draw.text(
            (width // 2, 74),
            f"{username} | {faction} | {len(territories)} районов",
            fill=(255, 255, 255),
            font=font_text,
            anchor="mm",
        )

        for terr in territories:
            lon, lat = self.region_coords.get(terr["region"], (31.0, 48.5))
            x, y = self.latlon_to_pixel(lat, lon, width, height)

            color = self.faction_colors.get(terr["region"], (100, 255, 100))
            fill = (*color, 105)
            draw.ellipse([x - 60, y - 60, x + 60, y + 60], fill=fill, outline=(*color, 220), width=3)
            draw.text((x, y), terr["district"][:10], fill=(255, 255, 255), font=font_text, anchor="mm")

        legend_y = height - 155
        draw.rectangle([20, legend_y, 430, height - 20], fill=(0, 0, 0, 200))
        draw.text((32, legend_y + 30), "Легенда:", fill=(255, 255, 255), font=font_text)
        draw.text((32, legend_y + 62), "🟢 Твои территории", fill=(100, 255, 100), font=font_text)
        draw.text((32, legend_y + 94), "🔴 Вражеские", fill=(255, 100, 100), font=font_text)
        draw.text((32, legend_y + 126), "🟡 Линия фронта", fill=(255, 255, 0), font=font_text)

        result = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        filename = f"map_{user_id}_{random.randint(10000, 99999)}.png"
        filepath = self.assets_path / filename
        result.save(filepath, "PNG")
        return str(filepath)
