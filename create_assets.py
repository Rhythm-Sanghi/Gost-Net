#!/usr/bin/env python3
"""
Ghost Net Asset Generator
Creates icon.png (512x512) and presplash.png (1080x1920) for Android packaging.

Run this script before building with buildozer:
    python create_assets.py
"""

from PIL import Image, ImageDraw, ImageFont
import os


def create_icon(output_path="icon.png", size=512):
    """
    Create a Ghost Net icon with a ghost/radar design.
    
    Design: Dark grey background with a white ghost outline and radar sweep effect.
    """
    # Create dark background
    bg_color = (35, 35, 35)  # Dark grey (#232323)
    img = Image.new('RGBA', (size, size), bg_color)
    draw = ImageDraw.Draw(img)
    
    # Draw radar circles (concentric circles)
    center = size // 2
    radar_color = (76, 175, 80, 100)  # Material Green with transparency
    for radius in [size//2 - 20, size//2 - 60, size//2 - 100]:
        draw.ellipse(
            [center - radius, center - radius, center + radius, center + radius],
            outline=radar_color,
            width=3
        )
    
    # Draw radar sweep line
    sweep_color = (76, 175, 80, 180)
    draw.line([center, center, center + size//2 - 30, center - size//3], 
              fill=sweep_color, width=4)
    
    # Draw ghost shape (simplified)
    ghost_color = (255, 255, 255, 200)
    ghost_size = size // 3
    ghost_x = center - ghost_size // 2
    ghost_y = center - ghost_size // 2
    
    # Ghost head (circle)
    draw.ellipse(
        [ghost_x, ghost_y, ghost_x + ghost_size, ghost_y + ghost_size],
        fill=ghost_color
    )
    
    # Ghost body (rectangle with wavy bottom)
    body_y = ghost_y + ghost_size // 2
    draw.rectangle(
        [ghost_x, body_y, ghost_x + ghost_size, body_y + ghost_size // 2],
        fill=ghost_color
    )
    
    # Ghost eyes
    eye_color = (35, 35, 35)
    eye_size = ghost_size // 8
    left_eye_x = ghost_x + ghost_size // 3
    right_eye_x = ghost_x + 2 * ghost_size // 3
    eye_y = ghost_y + ghost_size // 3
    
    draw.ellipse(
        [left_eye_x - eye_size, eye_y - eye_size, 
         left_eye_x + eye_size, eye_y + eye_size],
        fill=eye_color
    )
    draw.ellipse(
        [right_eye_x - eye_size, eye_y - eye_size, 
         right_eye_x + eye_size, eye_y + eye_size],
        fill=eye_color
    )
    
    # Add glow effect around the icon
    glow = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    for i in range(10):
        alpha = 20 - i * 2
        glow_draw.ellipse(
            [center - size//2 + i*5, center - size//2 + i*5, 
             center + size//2 - i*5, center + size//2 - i*5],
            outline=(76, 175, 80, alpha)
        )
    
    img = Image.alpha_composite(img.convert('RGBA'), glow)
    
    # Save
    img.save(output_path, 'PNG')
    print(f"✓ Icon created: {output_path} ({size}x{size})")
    return output_path


def create_presplash(output_path="presplash.png", width=1080, height=1920):
    """
    Create a presplash screen for Ghost Net.
    
    Design: Dark background (#121212) with centered logo and tagline.
    """
    # Create dark background
    bg_color = (18, 18, 18)  # #121212
    img = Image.new('RGBA', (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    
    # Draw central logo area (larger ghost with radar)
    center_x = width // 2
    center_y = height // 2 - 100  # Offset up slightly
    
    # Animated radar circles
    radar_color = (76, 175, 80, 80)
    for i, radius in enumerate([200, 280, 360]):
        alpha = 80 - i * 20
        color = (76, 175, 80, alpha)
        draw.ellipse(
            [center_x - radius, center_y - radius, 
             center_x + radius, center_y + radius],
            outline=color,
            width=3
        )
    
    # Draw large ghost
    ghost_color = (255, 255, 255, 220)
    ghost_size = 280
    ghost_x = center_x - ghost_size // 2
    ghost_y = center_y - ghost_size // 2
    
    # Ghost head
    draw.ellipse(
        [ghost_x, ghost_y, ghost_x + ghost_size, ghost_y + ghost_size],
        fill=ghost_color
    )
    
    # Ghost body
    body_y = ghost_y + ghost_size // 2
    draw.rectangle(
        [ghost_x, body_y, ghost_x + ghost_size, body_y + ghost_size // 2],
        fill=ghost_color
    )
    
    # Wavy bottom
    wave_y = body_y + ghost_size // 2
    wave_points = []
    for i in range(0, ghost_size + 1, ghost_size // 6):
        x = ghost_x + i
        y = wave_y + (15 if i % (ghost_size // 3) == 0 else 0)
        wave_points.append((x, y))
    wave_points.append((ghost_x + ghost_size, body_y))
    wave_points.append((ghost_x, body_y))
    draw.polygon(wave_points, fill=ghost_color)
    
    # Ghost eyes
    eye_color = (18, 18, 18)
    eye_size = ghost_size // 8
    left_eye_x = ghost_x + ghost_size // 3
    right_eye_x = ghost_x + 2 * ghost_size // 3
    eye_y = ghost_y + ghost_size // 3
    
    draw.ellipse(
        [left_eye_x - eye_size, eye_y - eye_size, 
         left_eye_x + eye_size, eye_y + eye_size],
        fill=eye_color
    )
    draw.ellipse(
        [right_eye_x - eye_size, eye_y - eye_size, 
         right_eye_x + eye_size, eye_y + eye_size],
        fill=eye_color
    )
    
    # App name text (using default PIL font)
    try:
        # Try to use a better font if available
        font_large = ImageFont.truetype("arial.ttf", 80)
        font_medium = ImageFont.truetype("arial.ttf", 50)
        font_small = ImageFont.truetype("arial.ttf", 40)
    except:
        # Fallback to default
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    # App name
    app_name = "Ghost Net"
    name_bbox = draw.textbbox((0, 0), app_name, font=font_large)
    name_width = name_bbox[2] - name_bbox[0]
    name_x = center_x - name_width // 2
    name_y = center_y + ghost_size // 2 + 120
    
    draw.text((name_x, name_y), app_name, fill=(255, 255, 255), font=font_large)
    
    # Tagline
    tagline = "Secure • Offline • Free"
    tagline_bbox = draw.textbbox((0, 0), tagline, font=font_small)
    tagline_width = tagline_bbox[2] - tagline_bbox[0]
    tagline_x = center_x - tagline_width // 2
    tagline_y = height - 200
    
    draw.text((tagline_x, tagline_y), tagline, 
              fill=(76, 175, 80), font=font_small)
    
    # Version info
    version = "v1.0.0"
    version_bbox = draw.textbbox((0, 0), version, font=font_small)
    version_width = version_bbox[2] - version_bbox[0]
    version_x = center_x - version_width // 2
    version_y = height - 120
    
    draw.text((version_x, version_y), version, 
              fill=(150, 150, 150), font=font_small)
    
    # Save
    img.save(output_path, 'PNG')
    print(f"✓ Presplash created: {output_path} ({width}x{height})")
    return output_path


def main():
    """Generate all required assets for Ghost Net."""
    print("Ghost Net Asset Generator")
    print("=" * 50)
    
    # Create assets directory if it doesn't exist
    os.makedirs("assets", exist_ok=True)
    
    # Generate icon
    icon_path = create_icon("icon.png", 512)
    
    # Generate presplash
    presplash_path = create_presplash("presplash.png", 1080, 1920)
    
    print("=" * 50)
    print("✓ All assets generated successfully!")
    print(f"  - {icon_path}")
    print(f"  - {presplash_path}")
    print("\nYou can now build with: buildozer android debug")


if __name__ == "__main__":
    main()
