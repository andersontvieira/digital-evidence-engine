"""Runtime-only artificial images shared by tests and Windows/Linux parity checks."""

from io import BytesIO

from PIL import Image, ImageDraw, ImageEnhance


def pattern():
    image = Image.new("RGB", (64, 40), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((3, 5, 28, 24), fill=(23, 77, 151))
    draw.ellipse((32, 8, 58, 35), fill=(205, 61, 19))
    draw.line((0, 39, 63, 0), fill=(0, 0, 0), width=3)
    return image


def encoded(image, fmt="PNG", **options):
    stream = BytesIO()
    image.save(stream, format=fmt, **options)
    return stream.getvalue()


def samples():
    base = pattern()
    rgba = base.convert("RGBA")
    rgba.putalpha(Image.linear_gradient("L").resize(base.size))
    palette = base.quantize(colors=8)
    palette.info["transparency"] = 0
    exif = Image.Exif()
    exif[274] = 6
    different = Image.new("RGB", (64, 40), (14, 19, 88))
    return {
        "jpeg": (encoded(base, "JPEG", quality=95), "jpeg"),
        "png": (encoded(base), "png"),
        "recompressed": (encoded(base, "JPEG", quality=55), "jpeg"),
        "resized": (encoded(base.resize((37, 23))), "png"),
        "brightness": (encoded(ImageEnhance.Brightness(base).enhance(1.1)), "png"),
        "contrast": (encoded(ImageEnhance.Contrast(base).enhance(0.9)), "png"),
        "crop": (encoded(base.crop((4, 3, 58, 36))), "png"),
        "different": (encoded(different), "png"),
        "oriented_jpeg": (encoded(base, "JPEG", exif=exif), "jpeg"),
        "rgba": (encoded(rgba), "png"),
        "palette": (encoded(palette), "png"),
        "la": (encoded(rgba.convert("LA")), "png"),
    }
