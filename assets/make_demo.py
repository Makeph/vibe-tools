from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 960
HEIGHT = 300
TOP_BAR_HEIGHT = 28
FONT_SIZE = 19
LINE_HEIGHT = FONT_SIZE + 8
LEFT_PADDING = 22
TEXT_TOP = TOP_BAR_HEIGHT + 18
FRAME_DURATION_MS = 90

BACKGROUND = "#0d1117"
TOP_BAR = "#161b22"
RED = "#ff5f56"
AMBER = "#ffbd2e"
GREEN = "#27c93f"
WHITE = "#ffffff"
LIGHT_GREY = "#c9d1d9"
MUTED = "#8b949e"
WARNING = "#e5c07b"

SCENES = [
    [
        "$ slopcheck app.py",
        "package              status",
        "------------------   ------------------",
        "requests             ok",
        "reqeusts             NOT FOUND  (not on PyPI - did you mean 'requests'?)",
        "super-helper-ai-42   NOT FOUND  (not on PyPI - likely hallucinated)",
        "",
        "[!] 2 suspicious package(s) of 3 checked. Verify before installing.",
    ],
    [
        "$ llmcost README.md vibe_tools/",
        "Input: 1,204 tokens from 6 source(s); assuming 500 output tokens",
        "",
        "model                in $       out $      total $",
        "gpt-5-mini             0.0003     0.0010      0.0013",
        "claude-haiku-4-5       0.0012     0.0025      0.0037",
        "claude-opus-4-8        0.0181     0.0375      0.0556",
    ],
    [
        "$ ctxpack . --redact | llmcost",
        "packed 14 files, ~9,820 tokens",
        "redacted 1 secret(s) before packing.",
        "claude-sonnet-4-6      total $  0.0312",
    ],
]


def load_font():
    for name in (
        r"C:\Windows\Fonts\consola.ttf",
        "consolas.ttf",
        "DejaVuSansMono.ttf",
    ):
        try:
            return ImageFont.truetype(name, FONT_SIZE)
        except OSError:
            pass
    return ImageFont.load_default()


def text_width(draw, text, font):
    return draw.textlength(text, font=font)


def draw_line(draw, position, line, font):
    x, y = position

    if line.startswith("$"):
        draw.text((x, y), "$", fill=GREEN, font=font)
        command_x = x + text_width(draw, "$", font)
        draw.text((command_x, y), line[1:], fill=WHITE, font=font)
        return

    if "NOT FOUND" in line or line.startswith("[!]"):
        draw.text((x, y), line, fill=WARNING, font=font)
        return

    stripped = line.strip()
    is_separator = bool(stripped) and set(stripped) == {"-"}
    is_column_header = stripped in {
        "package              status",
        "model                in $       out $      total $",
    }
    if is_separator or is_column_header:
        draw.text((x, y), line, fill=MUTED, font=font)
        return

    start = 0
    while True:
        token_index = line.find("ok", start)
        if token_index == -1:
            draw.text(
                (x + text_width(draw, line[:start], font), y),
                line[start:],
                fill=LIGHT_GREY,
                font=font,
            )
            break

        before = line[start:token_index]
        draw.text(
            (x + text_width(draw, line[:start], font), y),
            before,
            fill=LIGHT_GREY,
            font=font,
        )
        draw.text(
            (x + text_width(draw, line[:token_index], font), y),
            "ok",
            fill=GREEN,
            font=font,
        )
        start = token_index + 2


def render_frame(lines, font):
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, TOP_BAR_HEIGHT), fill=TOP_BAR)

    circle_y = TOP_BAR_HEIGHT // 2
    for circle_x, color in ((16, RED), (38, AMBER), (60, GREEN)):
        radius = 6
        draw.ellipse(
            (
                circle_x - radius,
                circle_y - radius,
                circle_x + radius,
                circle_y + radius,
            ),
            fill=color,
        )

    for index, line in enumerate(lines):
        draw_line(
            draw,
            (LEFT_PADDING, TEXT_TOP + index * LINE_HEIGHT),
            line,
            font,
        )
    return image


def main():
    font = load_font()
    frames = []
    durations = []

    for scene in SCENES:
        for visible_line_count in range(1, len(scene) + 1):
            frame = render_frame(scene[:visible_line_count], font)
            frames.extend((frame, frame.copy()))
            durations.extend((FRAME_DURATION_MS, FRAME_DURATION_MS))

        held_frame = render_frame(scene, font)
        for _ in range(12):
            frames.append(held_frame.copy())
            durations.append(FRAME_DURATION_MS)

        cleared_frame = render_frame([], font)
        frames.extend((cleared_frame, cleared_frame.copy()))
        durations.extend((FRAME_DURATION_MS, FRAME_DURATION_MS))

    output_path = Path(__file__).with_name("demo.gif")
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        disposal=2,
        optimize=True,
    )
    print(f"Wrote {output_path} ({WIDTH}x{HEIGHT}, {len(frames)} frames)")


if __name__ == "__main__":
    main()
