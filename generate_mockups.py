#!/usr/bin/env python3
"""
Ghost Net - Mockup Screenshot Generator
Generates realistic app screenshots for marketing materials
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os


class MockupGenerator:
    """Generates realistic Ghost Net app screenshots"""
    
    # Design constants matching KivyMD theme
    CANVAS_WIDTH = 1080
    CANVAS_HEIGHT = 1920
    BG_COLOR = "#121212"  # Dark background
    SURFACE_COLOR = "#1E1E1E"  # Card/surface background
    ACCENT_COLOR = "#4CAF50"  # Neon green
    TEXT_PRIMARY = "#FFFFFF"
    TEXT_SECONDARY = "#B0B0B0"
    DIVIDER_COLOR = "#2E2E2E"
    
    # Layout constants
    STATUSBAR_HEIGHT = 80
    APPBAR_HEIGHT = 140
    BOTTOM_NAV_HEIGHT = 140
    PADDING = 40
    
    def __init__(self, output_dir: str = "mockups"):
        """Initialize generator with output directory"""
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
    def _hex_to_rgb(self, hex_color: str) -> tuple:
        """Convert hex color to RGB tuple"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def _draw_rounded_rect(self, draw: ImageDraw, bbox: tuple, radius: int, 
                          fill: str, outline: str = None, width: int = 0):
        """Draw a rounded rectangle"""
        x1, y1, x2, y2 = bbox
        draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, 
                              fill=self._hex_to_rgb(fill),
                              outline=self._hex_to_rgb(outline) if outline else None,
                              width=width)
    
    def _draw_circle(self, draw: ImageDraw, center: tuple, radius: int, fill: str):
        """Draw a circle"""
        x, y = center
        draw.ellipse([x-radius, y-radius, x+radius, y+radius], 
                    fill=self._hex_to_rgb(fill))
    
    def _get_font(self, size: int, bold: bool = False):
        """Get font with fallback"""
        try:
            if bold:
                return ImageFont.truetype("arialbd.ttf", size)
            return ImageFont.truetype("arial.ttf", size)
        except:
            return ImageFont.load_default()
    
    def _draw_statusbar(self, draw: ImageDraw):
        """Draw Android status bar"""
        # Background
        draw.rectangle([0, 0, self.CANVAS_WIDTH, self.STATUSBAR_HEIGHT], 
                      fill=self._hex_to_rgb("#000000"))
        
        # Time (left)
        font = self._get_font(36)
        draw.text((self.PADDING, self.STATUSBAR_HEIGHT//2), "14:30", 
                 fill=self._hex_to_rgb(self.TEXT_PRIMARY), 
                 font=font, anchor="lm")
        
        # Icons (right) - simplified
        x_pos = self.CANVAS_WIDTH - self.PADDING
        icon_spacing = 60
        for i in range(3):  # Battery, WiFi, Signal
            draw.rectangle([x_pos - 50, 25, x_pos - 10, 55], 
                          fill=self._hex_to_rgb(self.TEXT_SECONDARY))
            x_pos -= icon_spacing
    
    def _draw_appbar(self, draw: ImageDraw, title: str):
        """Draw app bar with title"""
        y_start = self.STATUSBAR_HEIGHT
        
        # Background
        draw.rectangle([0, y_start, self.CANVAS_WIDTH, y_start + self.APPBAR_HEIGHT], 
                      fill=self._hex_to_rgb(self.SURFACE_COLOR))
        
        # Title
        font = self._get_font(56, bold=True)
        draw.text((self.PADDING, y_start + self.APPBAR_HEIGHT//2), title, 
                 fill=self._hex_to_rgb(self.TEXT_PRIMARY), 
                 font=font, anchor="lm")
    
    def _draw_bottom_nav(self, draw: ImageDraw, active_index: int = 0):
        """Draw bottom navigation bar"""
        y_start = self.CANVAS_HEIGHT - self.BOTTOM_NAV_HEIGHT
        
        # Background
        draw.rectangle([0, y_start, self.CANVAS_WIDTH, self.CANVAS_HEIGHT], 
                      fill=self._hex_to_rgb(self.SURFACE_COLOR))
        
        # Navigation items
        items = ["Radar", "Chats", "Settings"]
        item_width = self.CANVAS_WIDTH // 3
        font = self._get_font(40)
        
        for i, item in enumerate(items):
            x_center = item_width * i + item_width // 2
            y_center = y_start + self.BOTTOM_NAV_HEIGHT // 2
            
            # Icon (simplified circle)
            color = self.ACCENT_COLOR if i == active_index else self.TEXT_SECONDARY
            self._draw_circle(draw, (x_center, y_center - 20), 30, color)
            
            # Label
            draw.text((x_center, y_center + 30), item, 
                     fill=self._hex_to_rgb(color), 
                     font=font, anchor="mm")
    
    def generate_radar_screen(self):
        """Generate Radar screen mockup showing peer discovery"""
        print("📡 Generating Radar screen mockup...")
        
        # Create canvas
        img = Image.new('RGB', (self.CANVAS_WIDTH, self.CANVAS_HEIGHT), 
                       self._hex_to_rgb(self.BG_COLOR))
        draw = ImageDraw.Draw(img)
        
        # Draw UI chrome
        self._draw_statusbar(draw)
        self._draw_appbar(draw, "👻 Ghost Net")
        self._draw_bottom_nav(draw, active_index=0)
        
        # Content area
        content_y = self.STATUSBAR_HEIGHT + self.APPBAR_HEIGHT + self.PADDING
        content_bottom = self.CANVAS_HEIGHT - self.BOTTOM_NAV_HEIGHT - self.PADDING
        
        # Draw radar circles (concentric)
        center_x = self.CANVAS_WIDTH // 2
        center_y = (content_y + content_bottom) // 2
        
        for radius in [500, 350, 200]:
            draw.ellipse([center_x - radius, center_y - radius, 
                         center_x + radius, center_y + radius],
                        outline=self._hex_to_rgb(self.DIVIDER_COLOR), 
                        width=3)
        
        # Draw center point
        self._draw_circle(draw, (center_x, center_y), 20, self.ACCENT_COLOR)
        
        # Draw peer nodes
        peers = [
            {"name": "Alice", "pos": (center_x - 200, center_y - 150), "status": "online"},
            {"name": "Bob", "pos": (center_x + 180, center_y + 100), "status": "online"},
        ]
        
        font_name = self._get_font(44, bold=True)
        font_status = self._get_font(32)
        
        for peer in peers:
            x, y = peer["pos"]
            
            # Peer indicator (glowing effect)
            for glow_radius in [60, 50, 40]:
                alpha = 50 if glow_radius == 60 else 100 if glow_radius == 50 else 255
                temp_img = Image.new('RGBA', (self.CANVAS_WIDTH, self.CANVAS_HEIGHT), (0, 0, 0, 0))
                temp_draw = ImageDraw.Draw(temp_img)
                temp_draw.ellipse([x - glow_radius, y - glow_radius, 
                                  x + glow_radius, y + glow_radius],
                                 fill=(76, 175, 80, alpha // 3))
                img.paste(temp_img, (0, 0), temp_img)
            
            self._draw_circle(draw, (x, y), 35, self.ACCENT_COLOR)
            
            # Name label below peer
            draw.text((x, y + 80), peer["name"], 
                     fill=self._hex_to_rgb(self.TEXT_PRIMARY), 
                     font=font_name, anchor="mm")
        
        # Status text at top of content area
        status_font = self._get_font(48)
        draw.text((center_x, content_y + 40), "🔍 Scanning for peers...", 
                 fill=self._hex_to_rgb(self.ACCENT_COLOR), 
                 font=status_font, anchor="mm")
        
        # Peer count
        count_font = self._get_font(40)
        draw.text((center_x, content_bottom - 40), f"Found {len(peers)} peer(s)", 
                 fill=self._hex_to_rgb(self.TEXT_SECONDARY), 
                 font=count_font, anchor="mm")
        
        # Save
        output_path = os.path.join(self.output_dir, "screenshot_radar.png")
        img.save(output_path)
        print(f"✅ Saved: {output_path}")
    
    def generate_chat_screen(self):
        """Generate Chat screen mockup showing conversation"""
        print("💬 Generating Chat screen mockup...")
        
        # Create canvas
        img = Image.new('RGB', (self.CANVAS_WIDTH, self.CANVAS_HEIGHT), 
                       self._hex_to_rgb(self.BG_COLOR))
        draw = ImageDraw.Draw(img)
        
        # Draw UI chrome
        self._draw_statusbar(draw)
        self._draw_appbar(draw, "💬 Chat with Alice")
        self._draw_bottom_nav(draw, active_index=1)
        
        # Content area
        content_y = self.STATUSBAR_HEIGHT + self.APPBAR_HEIGHT + self.PADDING
        content_bottom = self.CANVAS_HEIGHT - self.BOTTOM_NAV_HEIGHT - self.PADDING
        
        # Messages
        messages = [
            {"text": "Hey, testing Ghost Net!", "sent": False, "y": content_y + 50},
            {"text": "Works great! 🔒", "sent": True, "y": content_y + 200},
            {"text": "Sending you a file...", "sent": False, "y": content_y + 350},
            {"file": "document.pdf", "sent": False, "y": content_y + 500},
        ]
        
        font_msg = self._get_font(42)
        font_time = self._get_font(30)
        
        for msg in messages:
            y_pos = msg["y"]
            
            if "text" in msg:
                # Text message bubble
                text = msg["text"]
                # Estimate text width (simplified)
                text_width = len(text) * 24
                bubble_width = min(text_width + 80, self.CANVAS_WIDTH - 200)
                bubble_height = 100
                
                if msg["sent"]:
                    # Sent message (right aligned, accent color)
                    x1 = self.CANVAS_WIDTH - self.PADDING - bubble_width
                    x2 = self.CANVAS_WIDTH - self.PADDING
                    self._draw_rounded_rect(draw, (x1, y_pos, x2, y_pos + bubble_height),
                                          radius=30, fill=self.ACCENT_COLOR)
                    draw.text((x1 + 40, y_pos + bubble_height//2), text, 
                             fill=self._hex_to_rgb("#000000"), 
                             font=font_msg, anchor="lm")
                else:
                    # Received message (left aligned, surface color)
                    x1 = self.PADDING
                    x2 = self.PADDING + bubble_width
                    self._draw_rounded_rect(draw, (x1, y_pos, x2, y_pos + bubble_height),
                                          radius=30, fill=self.SURFACE_COLOR)
                    draw.text((x1 + 40, y_pos + bubble_height//2), text, 
                             fill=self._hex_to_rgb(self.TEXT_PRIMARY), 
                             font=font_msg, anchor="lm")
            
            elif "file" in msg:
                # File attachment bubble
                filename = msg["file"]
                bubble_width = 600
                bubble_height = 140
                
                x1 = self.PADDING
                x2 = self.PADDING + bubble_width
                self._draw_rounded_rect(draw, (x1, y_pos, x2, y_pos + bubble_height),
                                      radius=30, fill=self.SURFACE_COLOR)
                
                # File icon (simplified)
                icon_x = x1 + 50
                icon_y = y_pos + bubble_height // 2
                draw.rectangle([icon_x - 30, icon_y - 40, icon_x + 30, icon_y + 40],
                             fill=self._hex_to_rgb(self.ACCENT_COLOR))
                
                # Filename
                draw.text((icon_x + 80, icon_y - 20), filename, 
                         fill=self._hex_to_rgb(self.TEXT_PRIMARY), 
                         font=font_msg, anchor="lm")
                
                # File size
                draw.text((icon_x + 80, icon_y + 25), "1.2 MB • PDF", 
                         fill=self._hex_to_rgb(self.TEXT_SECONDARY), 
                         font=font_time, anchor="lm")
        
        # Input bar at bottom (above bottom nav)
        input_y = content_bottom - 100
        self._draw_rounded_rect(draw, 
                              (self.PADDING, input_y, 
                               self.CANVAS_WIDTH - self.PADDING, input_y + 100),
                              radius=50, fill=self.SURFACE_COLOR)
        
        input_font = self._get_font(40)
        draw.text((self.PADDING + 60, input_y + 50), "Type a message...", 
                 fill=self._hex_to_rgb(self.TEXT_SECONDARY), 
                 font=input_font, anchor="lm")
        
        # Save
        output_path = os.path.join(self.output_dir, "screenshot_chat.png")
        img.save(output_path)
        print(f"✅ Saved: {output_path}")
    
    def generate_settings_screen(self):
        """Generate Settings screen mockup"""
        print("⚙️ Generating Settings screen mockup...")
        
        # Create canvas
        img = Image.new('RGB', (self.CANVAS_WIDTH, self.CANVAS_HEIGHT), 
                       self._hex_to_rgb(self.BG_COLOR))
        draw = ImageDraw.Draw(img)
        
        # Draw UI chrome
        self._draw_statusbar(draw)
        self._draw_appbar(draw, "⚙️ Settings")
        self._draw_bottom_nav(draw, active_index=2)
        
        # Content area
        content_y = self.STATUSBAR_HEIGHT + self.APPBAR_HEIGHT + self.PADDING
        
        # Settings sections
        sections = [
            {
                "title": "Identity",
                "items": [
                    {"label": "Username", "value": "Ghost_User_7F3A"},
                ]
            },
            {
                "title": "Privacy",
                "items": [
                    {"label": "Auto-delete messages", "value": "Enabled"},
                    {"label": "Delete after", "value": "24 hours"},
                ]
            },
            {
                "title": "Security",
                "items": [
                    {"label": "🚨 Panic Mode", "value": "ACTIVATE"},
                ]
            },
            {
                "title": "Localization",
                "items": [
                    {"label": "Language", "value": "English"},
                ]
            },
        ]
        
        font_section = self._get_font(40, bold=True)
        font_label = self._get_font(44)
        font_value = self._get_font(40)
        
        current_y = content_y
        
        for section in sections:
            # Section header
            draw.text((self.PADDING, current_y), section["title"], 
                     fill=self._hex_to_rgb(self.ACCENT_COLOR), 
                     font=font_section, anchor="lm")
            current_y += 80
            
            # Section items
            for item in section["items"]:
                # Item card
                card_height = 120
                self._draw_rounded_rect(draw, 
                                      (self.PADDING, current_y, 
                                       self.CANVAS_WIDTH - self.PADDING, current_y + card_height),
                                      radius=20, fill=self.SURFACE_COLOR)
                
                # Label (left)
                draw.text((self.PADDING + 40, current_y + card_height//2), item["label"], 
                         fill=self._hex_to_rgb(self.TEXT_PRIMARY), 
                         font=font_label, anchor="lm")
                
                # Value (right)
                value_color = self.ACCENT_COLOR if "ACTIVATE" in item["value"] else self.TEXT_SECONDARY
                draw.text((self.CANVAS_WIDTH - self.PADDING - 40, current_y + card_height//2), 
                         item["value"], 
                         fill=self._hex_to_rgb(value_color), 
                         font=font_value, anchor="rm")
                
                current_y += card_height + 30
            
            current_y += 40  # Space between sections
        
        # Save
        output_path = os.path.join(self.output_dir, "screenshot_settings.png")
        img.save(output_path)
        print(f"✅ Saved: {output_path}")
    
    def generate_promo_composite(self):
        """Generate promotional composite with two phones side-by-side"""
        print("🎨 Generating promotional composite...")
        
        # Create wider canvas for two phones
        promo_width = 2400
        promo_height = 2200
        
        img = Image.new('RGB', (promo_width, promo_height), 
                       self._hex_to_rgb("#0A0A0A"))
        
        # Load previous screenshots
        try:
            radar_img = Image.open(os.path.join(self.output_dir, "screenshot_radar.png"))
            chat_img = Image.open(os.path.join(self.output_dir, "screenshot_chat.png"))
            
            # Resize slightly to fit
            phone_width = 900
            phone_height = int(phone_width * (self.CANVAS_HEIGHT / self.CANVAS_WIDTH))
            
            radar_resized = radar_img.resize((phone_width, phone_height), Image.Resampling.LANCZOS)
            chat_resized = chat_img.resize((phone_width, phone_height), Image.Resampling.LANCZOS)
            
            # Calculate positions (centered with spacing)
            spacing = 200
            left_x = (promo_width - (phone_width * 2 + spacing)) // 2
            right_x = left_x + phone_width + spacing
            y_pos = (promo_height - phone_height) // 2
            
            # Add subtle shadow/glow effect
            for offset in range(20, 0, -4):
                shadow_alpha = int(255 * (offset / 20) * 0.3)
                temp_img = Image.new('RGBA', (promo_width, promo_height), (0, 0, 0, 0))
                temp_draw = ImageDraw.Draw(temp_img)
                
                # Left phone shadow
                temp_draw.rounded_rectangle(
                    [left_x - offset, y_pos - offset, 
                     left_x + phone_width + offset, y_pos + phone_height + offset],
                    radius=40,
                    fill=(76, 175, 80, shadow_alpha // 2)
                )
                
                # Right phone shadow
                temp_draw.rounded_rectangle(
                    [right_x - offset, y_pos - offset, 
                     right_x + phone_width + offset, y_pos + phone_height + offset],
                    radius=40,
                    fill=(76, 175, 80, shadow_alpha // 2)
                )
                
                img.paste(temp_img, (0, 0), temp_img)
            
            # Paste screenshots
            img.paste(radar_resized, (left_x, y_pos))
            img.paste(chat_resized, (right_x, y_pos))
            
            # Add title text above
            draw = ImageDraw.Draw(img)
            title_font = self._get_font(100, bold=True)
            subtitle_font = self._get_font(60)
            
            draw.text((promo_width // 2, 150), "👻 Ghost Net", 
                     fill=self._hex_to_rgb(self.ACCENT_COLOR), 
                     font=title_font, anchor="mm")
            
            draw.text((promo_width // 2, 280), "Surveillance-Free P2P Messaging", 
                     fill=self._hex_to_rgb(self.TEXT_SECONDARY), 
                     font=subtitle_font, anchor="mm")
            
            # Save
            output_path = os.path.join(self.output_dir, "screenshot_promo.png")
            img.save(output_path)
            print(f"✅ Saved: {output_path}")
            
        except FileNotFoundError as e:
            print(f"❌ Error: Could not find previous screenshots. Generate them first.")
            print(f"   Details: {e}")
    
    def generate_all(self):
        """Generate all mockups"""
        print("\n" + "="*60)
        print("👻 Ghost Net - Mockup Generator")
        print("="*60 + "\n")
        
        self.generate_radar_screen()
        self.generate_chat_screen()
        self.generate_settings_screen()
        self.generate_promo_composite()
        
        print("\n" + "="*60)
        print("✅ All mockups generated successfully!")
        print(f"📁 Output directory: {self.output_dir}/")
        print("="*60 + "\n")
        
        print("Generated files:")
        print("  • screenshot_radar.png - Peer discovery radar")
        print("  • screenshot_chat.png - Encrypted messaging")
        print("  • screenshot_settings.png - Privacy controls")
        print("  • screenshot_promo.png - Promotional composite")
        print("\n💡 Use these in README.md and social media posts!")


if __name__ == "__main__":
    generator = MockupGenerator()
    generator.generate_all()
