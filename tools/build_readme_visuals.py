#!/usr/bin/env python3
"""Build deterministic README PNG components from repository-owned source assets.

This maintenance helper is intentionally outside the release packages. It needs
Pillow and writes only the five generated README components listed in OUTPUTS.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ICONS = DOCS / "icons"
SCALE = 2
FONT_CANDIDATES = {
    "regular": (
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    ),
    "bold": (
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    ),
}

OUTPUTS = (
    DOCS / "download-skill.png",
    DOCS / "download-workbuddy.png",
    DOCS / "platform-codex.png",
    DOCS / "platform-claude.png",
    DOCS / "platform-workbuddy.png",
)


def sc(value: int | float) -> int:
    return round(value * SCALE)


def box(values: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    return tuple(sc(value) for value in values)


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    weight = "bold" if bold else "regular"
    path = next((candidate for candidate in FONT_CANDIDATES[weight] if candidate.exists()), None)
    if path is None:
        raise RuntimeError(f"No supported CJK {weight} font was found")
    return ImageFont.truetype(str(path), sc(size))


def rounded_icon(source: Path, size: int, *, radius: int | None = None) -> Image.Image:
    image = Image.open(source).convert("RGBA").resize((sc(size), sc(size)), Image.Resampling.LANCZOS)
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)
    resolved_radius = sc(radius if radius is not None else size // 2)
    draw.rounded_rectangle((0, 0, image.width - 1, image.height - 1), radius=resolved_radius, fill=255)
    image.putalpha(ImageChops.multiply(image.getchannel("A"), mask))
    return image


def paste_center(canvas: Image.Image, image: Image.Image, center: tuple[int, int]) -> None:
    x = sc(center[0]) - image.width // 2
    y = sc(center[1]) - image.height // 2
    canvas.alpha_composite(image, (x, y))


def draw_pill(
    draw: ImageDraw.ImageDraw,
    coords: tuple[int, int, int, int],
    fill: str,
    label: str,
    label_color: str = "#FFFFFF",
    label_size: int = 16,
) -> None:
    draw.rounded_rectangle(box(coords), radius=sc(21), fill=fill)
    cx = (coords[0] + coords[2]) / 2
    cy = (coords[1] + coords[3]) / 2 - 1
    draw.text((sc(cx), sc(cy)), label, font=font(label_size, bold=True), fill=label_color, anchor="mm")


def platform_header(
    output: Path,
    *,
    background: str,
    border: str,
    accent: str,
    title_color: str,
    subtitle_color: str,
    title: str,
    subtitle: str,
    tag: str,
    icon_name: str,
) -> None:
    canvas = Image.new("RGBA", (sc(900), sc(76)), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(box((2, 2, 898, 74)), radius=sc(14), fill=background, outline=border, width=sc(2))
    draw.rounded_rectangle(box((2, 2, 13, 74)), radius=sc(5), fill=accent)

    if icon_name == "claude":
        draw.ellipse(box((31, 17, 73, 59)), fill="#FFF8F3", outline="#E7C1A8", width=sc(1))
        icon = rounded_icon(ICONS / "claude.png", 29)
    elif icon_name == "codex":
        icon = rounded_icon(ICONS / "codex.png", 42)
    else:
        icon = rounded_icon(ICONS / "workbuddy.png", 42, radius=11)
    paste_center(canvas, icon, (52, 38))

    draw.text((sc(88), sc(11)), title, font=font(22, bold=True), fill=title_color)
    draw.text((sc(88), sc(43)), subtitle, font=font(14), fill=subtitle_color)
    draw_pill(draw, (698, 20, 870, 56), accent, tag, label_size=14)
    canvas.convert("RGB").save(output, optimize=True)


def horizontal_gradient(size: tuple[int, int], left: str, right: str) -> Image.Image:
    gradient = Image.new("RGBA", size)
    ld = tuple(int(left[index : index + 2], 16) for index in (1, 3, 5))
    rd = tuple(int(right[index : index + 2], 16) for index in (1, 3, 5))
    draw = ImageDraw.Draw(gradient)
    for x in range(size[0]):
        ratio = x / max(1, size[0] - 1)
        color = tuple(round(ld[i] + (rd[i] - ld[i]) * ratio) for i in range(3)) + (255,)
        draw.line((x, 0, x, size[1]), fill=color)
    return gradient


def primary_download(output: Path) -> None:
    canvas = Image.new("RGBA", (sc(900), sc(80)), "white")
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(box((8, 10, 892, 76)), radius=sc(16), fill=(108, 67, 31, 42))
    shadow = shadow.filter(ImageFilter.GaussianBlur(sc(5)))
    canvas.alpha_composite(shadow)

    gradient = horizontal_gradient((sc(884), sc(66)), "#E3943D", "#F5C56B")
    mask = Image.new("L", gradient.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, gradient.width - 1, gradient.height - 1), radius=sc(16), fill=255)
    gradient.putalpha(mask)
    canvas.alpha_composite(gradient, (sc(8), sc(6)))
    draw = ImageDraw.Draw(canvas)
    draw.ellipse(box((30, 15, 78, 63)), fill="#FFFFFF")

    codex = rounded_icon(ICONS / "codex.png", 30)
    paste_center(canvas, codex, (48, 34))
    draw.ellipse(box((51, 37, 75, 61)), fill="#FFF8F3", outline="#FFFFFF", width=sc(2))
    claude = rounded_icon(ICONS / "claude.png", 16)
    paste_center(canvas, claude, (63, 49))

    draw.text((sc(94), sc(11)), "下载通用 Skill ZIP", font=font(21, bold=True), fill="#173E31")
    draw.text((sc(94), sc(41)), "OpenAI Codex · Claude Code 适用　最新 Release · 解压即用", font=font(14), fill="#5E442D")
    draw_pill(draw, (720, 20, 864, 58), "#173E31", "立即下载", label_size=15)
    draw.line(box((835, 32, 842, 39)), fill="#F5C56B", width=sc(3))
    draw.line(box((835, 46, 842, 39)), fill="#F5C56B", width=sc(3))
    canvas.convert("RGB").save(output, optimize=True)


def workbuddy_download(output: Path) -> None:
    canvas = Image.new("RGBA", (sc(900), sc(68)), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(box((8, 4, 892, 64)), radius=sc(15), fill="#F1F7F4", outline="#2E6B4E", width=sc(2))
    draw.rounded_rectangle(box((8, 4, 18, 64)), radius=sc(5), fill="#2E6B4E")
    icon = rounded_icon(ICONS / "workbuddy.png", 40, radius=10)
    paste_center(canvas, icon, (49, 34))
    draw.text((sc(84), sc(8)), "下载 WorkBuddy ZIP", font=font(20, bold=True), fill="#173E31")
    draw.text((sc(84), sc(37)), "WorkBuddy Open Platform 专用导入包", font=font(13), fill="#5B7067")
    draw_pill(draw, (720, 15, 864, 53), "#2E6B4E", "立即下载", label_size=15)
    draw.line(box((835, 27, 842, 34)), fill="#F5C56B", width=sc(3))
    draw.line(box((835, 41, 842, 34)), fill="#F5C56B", width=sc(3))
    canvas.convert("RGB").save(output, optimize=True)


def main() -> None:
    for required in (ICONS / "codex.png", ICONS / "claude.png", ICONS / "workbuddy.png"):
        if not required.exists():
            raise SystemExit(f"Missing source asset: {required}")

    primary_download(DOCS / "download-skill.png")
    workbuddy_download(DOCS / "download-workbuddy.png")
    platform_header(
        DOCS / "platform-codex.png",
        background="#EAF4EF",
        border="#B9D5C8",
        accent="#155B45",
        title_color="#173E31",
        subtitle_color="#5B7067",
        title="OpenAI Codex",
        subtitle="ZIP 一键安装或 Git 克隆 · 安装后用技能名显式调用",
        tag="推荐 · 通用 Skill ZIP",
        icon_name="codex",
    )
    platform_header(
        DOCS / "platform-claude.png",
        background="#FBF2E9",
        border="#E5C3A5",
        accent="#A95D36",
        title_color="#713D27",
        subtitle_color="#765A49",
        title="Claude Code",
        subtitle="遵循 Agent Skills 的 SKILL.md 结构 · 支持通用发布包",
        tag="兼容 · Agent Skills",
        icon_name="claude",
    )
    platform_header(
        DOCS / "platform-workbuddy.png",
        background="#EEF4F8",
        border="#B8CDD9",
        accent="#376B82",
        title_color="#294F62",
        subtitle_color="#5A6E79",
        title="WorkBuddy Open Platform",
        subtitle="使用专用 ZIP 直接导入 · 同步保留完整技能说明与资源",
        tag="专用 · WorkBuddy ZIP",
        icon_name="workbuddy",
    )
    for output in OUTPUTS:
        print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()
