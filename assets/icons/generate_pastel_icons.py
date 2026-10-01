import os
import math
import cv2
import numpy as np
from PIL import Image, ImageDraw

ICONS_DIR = os.path.dirname(os.path.abspath(__file__))
PURE_TEX_PATH = os.path.join(ICONS_DIR, 'pure_watercolor.png')
USER_REF_PATH = r'C:\Users\DARSHONBRO\.gemini\antigravity-ide\brain\7ccd2d66-401a-4ab5-aab0-ffec6c44cff3\.user_uploaded\media_1790706056102.png'

# Canvas size 1024x1024 for supersampling
W, H = 1024, 1024
CARD_W, CARD_H = 880, 660
CARD_X0 = (W - CARD_W) // 2
CARD_Y0 = (H - CARD_H) // 2
CARD_X1 = CARD_X0 + CARD_W
CARD_Y1 = CARD_Y0 + CARD_H
CORNER_RADIUS = 120

# Load pure watercolor texture
tex_raw = Image.open(PURE_TEX_PATH).convert('RGBA')
tex_resized = tex_raw.resize((CARD_W, CARD_H), Image.Resampling.BICUBIC)

def get_base_card():
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    mask = Image.new('L', (W, H), 0)
    d_m = ImageDraw.Draw(mask)
    d_m.rounded_rectangle([CARD_X0, CARD_Y0, CARD_X1, CARD_Y1], radius=CORNER_RADIUS, fill=255)
    
    im.paste(tex_resized, (CARD_X0, CARD_Y0))
    im.putalpha(mask)
    
    # Outer subtle glossy border
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([CARD_X0, CARD_Y0, CARD_X1, CARD_Y1], radius=CORNER_RADIUS, 
                        outline=(255, 238, 245, 180), width=6)
    return im

def draw_capsule_line(d, p1, p2, width, fill='white'):
    x1, y1 = p1
    x2, y2 = p2
    d.line([p1, p2], fill=fill, width=width)
    r = width // 2
    d.ellipse([x1 - r, y1 - r, x1 + r, y1 + r], fill=fill)
    d.ellipse([x2 - r, y2 - r, x2 + r, y2 + r], fill=fill)

def save_icon(im_1024, filename):
    # 512x512
    im_512 = im_1024.resize((512, 512), Image.Resampling.LANCZOS)
    path_512 = os.path.join(ICONS_DIR, filename)
    im_512.save(path_512, format='PNG')
    
    # 128x128
    im_128 = im_1024.resize((128, 128), Image.Resampling.LANCZOS)
    emoji_dir = os.path.join(ICONS_DIR, '128x128')
    os.makedirs(emoji_dir, exist_ok=True)
    im_128.save(os.path.join(emoji_dir, filename), format='PNG')
    print(f"Generated {filename}")

# ==========================================
# 1. vc_lock (Locked)
# ==========================================
def gen_lock():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Shackle arc & legs
    d.arc([400, 270, 624, 490], start=180, end=0, fill='white', width=44)
    draw_capsule_line(d, (400, 380), (400, 488), 44)
    draw_capsule_line(d, (624, 380), (624, 488), 44)
    # Lock body
    d.rounded_rectangle([340, 468, 684, 736], radius=56, outline='white', width=44)
    # Keyhole
    d.ellipse([488, 545, 536, 593], fill='white')
    d.polygon([(498, 588), (526, 588), (522, 650), (502, 650)], fill='white')
    save_icon(im, 'vc_lock.png')

# ==========================================
# 2. vc_unlock (Unlocked)
# ==========================================
def gen_unlock():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Lifted and opened shackle
    d.arc([440, 220, 664, 440], start=180, end=0, fill='white', width=44)
    draw_capsule_line(d, (440, 330), (440, 488), 44)
    draw_capsule_line(d, (664, 330), (664, 390), 44)
    # Lock body
    d.rounded_rectangle([340, 468, 684, 736], radius=56, outline='white', width=44)
    # Keyhole
    d.ellipse([488, 545, 536, 593], fill='white')
    d.polygon([(498, 588), (526, 588), (522, 650), (502, 650)], fill='white')
    save_icon(im, 'vc_unlock.png')

# ==========================================
# 3. vc_ghost (Invisible / Hidden)
# ==========================================
def gen_ghost():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Ghost dome
    d.arc([350, 270, 674, 594], start=180, end=0, fill='white', width=44)
    # Body sides
    draw_capsule_line(d, (350, 432), (350, 680), 44)
    draw_capsule_line(d, (674, 432), (674, 680), 44)
    # Wavy bottom waves
    d.arc([350, 640, 458, 720], start=0, end=180, fill='white', width=44)
    d.arc([458, 640, 566, 720], start=0, end=180, fill='white', width=44)
    d.arc([566, 640, 674, 720], start=0, end=180, fill='white', width=44)
    # Cute oval eyes
    d.rounded_rectangle([424, 420, 468, 490], radius=22, fill='white')
    d.rounded_rectangle([556, 420, 600, 490], radius=22, fill='white')
    save_icon(im, 'vc_ghost.png')

# ==========================================
# 4. vc_reveal (Visible / Eye)
# ==========================================
def gen_reveal():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Eye contour
    d.arc([230, 270, 794, 754], start=210, end=330, fill='white', width=44)
    d.arc([230, 270, 794, 754], start=30, end=150, fill='white', width=44)
    # Iris
    d.ellipse([424, 424, 600, 600], outline='white', width=44)
    # Pupil
    d.ellipse([484, 484, 540, 540], fill='white')
    save_icon(im, 'vc_reveal.png')

# ==========================================
# 5. vc_rename (Authentic reference)
# ==========================================
def gen_rename():
    # Load user's reference image
    ref = Image.open(USER_REF_PATH).convert('RGBA')
    # Place on 1024x1024 canvas centered
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    scale = min(W / ref.width, H / ref.height) * 0.98
    nw, nh = int(ref.width * scale), int(ref.height * scale)
    ref_resized = ref.resize((nw, nh), Image.Resampling.LANCZOS)
    im.paste(ref_resized, ((W - nw) // 2, (H - nh) // 2), mask=ref_resized)
    save_icon(im, 'vc_rename.png')

# ==========================================
# 6. vc_limit (User Limit: Silhouette + # Hash)
# ==========================================
def gen_limit():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # User silhouette (left)
    d.ellipse([310, 320, 430, 440], outline='white', width=38)
    d.arc([240, 460, 500, 680], start=180, end=0, fill='white', width=38)
    draw_capsule_line(d, (240, 570), (240, 690), 38)
    draw_capsule_line(d, (500, 570), (500, 690), 38)
    # Number / Hash symbol '#' on right
    # Vertical bars
    draw_capsule_line(d, (610, 360), (590, 650), 36)
    draw_capsule_line(d, (710, 360), (690, 650), 36)
    # Horizontal bars
    draw_capsule_line(d, (540, 440), (760, 440), 36)
    draw_capsule_line(d, (530, 560), (750, 560), 36)
    save_icon(im, 'vc_limit.png')

# ==========================================
# 7. vc_mute (Mute)
# ==========================================
def gen_mute():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Mic capsule
    d.rounded_rectangle([456, 280, 568, 470], radius=56, outline='white', width=40)
    # Cradle
    d.arc([406, 360, 618, 530], start=0, end=180, fill='white', width=40)
    # Stand & base
    draw_capsule_line(d, (512, 530), (512, 640), 40)
    draw_capsule_line(d, (430, 640), (594, 640), 40)
    # Diagonal strike
    draw_capsule_line(d, (330, 310), (694, 674), 44)
    save_icon(im, 'vc_mute.png')

# ==========================================
# 8. vc_unmute (Unmute)
# ==========================================
def gen_unmute():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Mic capsule
    d.rounded_rectangle([456, 280, 568, 470], radius=56, outline='white', width=40)
    # Cradle
    d.arc([406, 360, 618, 530], start=0, end=180, fill='white', width=40)
    # Stand & base
    draw_capsule_line(d, (512, 530), (512, 640), 40)
    draw_capsule_line(d, (430, 640), (594, 640), 40)
    # Sound wave arcs left & right
    d.arc([630, 310, 710, 490], start=300, end=60, fill='white', width=36)
    d.arc([690, 260, 790, 540], start=300, end=60, fill='white', width=36)
    d.arc([314, 310, 394, 490], start=120, end=240, fill='white', width=36)
    d.arc([234, 260, 334, 540], start=120, end=240, fill='white', width=36)
    save_icon(im, 'vc_unmute.png')

def draw_clean_shield(d, x0=340, y0=310, x1=684, y1=720, width=42):
    # Shield shape points
    y_turn = y0 + 190
    pts = [(x0, y0), (x1, y0), (x1, y_turn), (512, y1), (x0, y_turn)]
    for i in range(len(pts)):
        p_a = pts[i]
        p_b = pts[(i + 1) % len(pts)]
        draw_capsule_line(d, p_a, p_b, width)

# ==========================================
# 9. vc_trust (Trust Member)
# ==========================================
def gen_trust():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    draw_clean_shield(d)
    # Crisp checkmark inside
    draw_capsule_line(d, (424, 490), (484, 550), 42)
    draw_capsule_line(d, (484, 550), (600, 420), 42)
    save_icon(im, 'vc_trust.png')

# ==========================================
# 10. vc_untrust (Untrust Member)
# ==========================================
def gen_untrust():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    draw_clean_shield(d)
    # Crisp minus bar inside
    draw_capsule_line(d, (420, 490), (604, 490), 44)
    save_icon(im, 'vc_untrust.png')

# ==========================================
# 11. vc_invite (Invite / Add)
# ==========================================
def gen_invite():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Envelope body
    d.rounded_rectangle([290, 360, 690, 670], radius=36, outline='white', width=40)
    draw_capsule_line(d, (300, 380), (490, 520), 38)
    draw_capsule_line(d, (680, 380), (490, 520), 38)
    # Plus badge: solid white circle with soft pink plus symbol
    d.ellipse([640, 270, 770, 400], fill='white')
    draw_capsule_line(d, (705, 305), (705, 365), 26, fill=(240, 150, 180))
    draw_capsule_line(d, (675, 335), (735, 335), 26, fill=(240, 150, 180))
    save_icon(im, 'vc_invite.png')

# ==========================================
# 12. vc_kick (Kick Member: User + Exit Arrow)
# ==========================================
def gen_kick():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # User silhouette (left)
    d.ellipse([320, 330, 440, 450], outline='white', width=38)
    d.arc([250, 470, 510, 690], start=180, end=0, fill='white', width=38)
    draw_capsule_line(d, (250, 580), (250, 690), 38)
    draw_capsule_line(d, (510, 580), (510, 690), 38)
    # Exit arrow pointing right
    draw_capsule_line(d, (570, 512), (730, 512), 40)
    d.polygon([(690, 450), (770, 512), (690, 574)], fill='white')
    # Vertical exit portal / door bracket on right
    draw_capsule_line(d, (790, 360), (790, 660), 36)
    save_icon(im, 'vc_kick.png')

# ==========================================
# 13. vc_block (Block / Ban)
# ==========================================
def gen_block():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Prohibition circle
    d.ellipse([320, 320, 704, 704], outline='white', width=44)
    # Slash
    draw_capsule_line(d, (380, 380), (644, 644), 44)
    save_icon(im, 'vc_block.png')

# ==========================================
# 14. vc_unblock (Unblock)
# ==========================================
def gen_unblock():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Circle
    d.ellipse([320, 320, 704, 704], outline='white', width=44)
    # Checkmark inside
    draw_capsule_line(d, (410, 512), (480, 582), 44)
    draw_capsule_line(d, (480, 582), (614, 430), 44)
    save_icon(im, 'vc_unblock.png')

# ==========================================
# 15. vc_knock (Knock / Door)
# ==========================================
def gen_knock():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Door frame
    d.rounded_rectangle([320, 280, 560, 720], radius=32, outline='white', width=40)
    # Door knob
    d.ellipse([500, 490, 532, 522], fill='white')
    # Knock ripples on right
    d.arc([540, 400, 680, 600], start=300, end=60, fill='white', width=36)
    d.arc([580, 330, 770, 670], start=300, end=60, fill='white', width=36)
    save_icon(im, 'vc_knock.png')

# ==========================================
# 16. vc_claim (Claim Ownership / Crown)
# ==========================================
def gen_claim():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Crown peaks
    peaks = [(310, 410), (410, 480), (512, 340), (614, 480), (714, 410), (690, 630), (334, 630)]
    d.polygon(peaks, outline='white', width=40)
    # Jewel pearls on tips
    for px, py in [(310, 410), (512, 340), (714, 410)]:
        d.ellipse([px - 22, py - 22, px + 22, py + 22], fill='white')
    # Crown headband band
    draw_capsule_line(d, (320, 670), (704, 670), 38)
    save_icon(im, 'vc_claim.png')

# ==========================================
# 17. vc_transfer (Transfer Ownership)
# ==========================================
def gen_transfer():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Top arrow (pointing right)
    draw_capsule_line(d, (330, 430), (640, 430), 40)
    d.polygon([(620, 370), (700, 430), (620, 490)], fill='white')
    # Bottom arrow (pointing left)
    draw_capsule_line(d, (384, 570), (694, 570), 40)
    d.polygon([(404, 510), (324, 570), (404, 630)], fill='white')
    save_icon(im, 'vc_transfer.png')

# ==========================================
# 18. vc_info (Info)
# ==========================================
def gen_info():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Circle
    d.ellipse([320, 320, 704, 704], outline='white', width=44)
    # 'i' dot
    d.ellipse([488, 400, 536, 448], fill='white')
    # 'i' stem
    draw_capsule_line(d, (512, 490), (512, 620), 44)
    save_icon(im, 'vc_info.png')

# ==========================================
# 19. vc_delete (Delete / Trash)
# ==========================================
def gen_delete():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Handle on lid
    d.arc([460, 270, 564, 360], start=180, end=0, fill='white', width=36)
    # Lid
    draw_capsule_line(d, (330, 360), (694, 360), 44)
    # Tapered can outline
    d.polygon([(364, 400), (404, 700), (620, 700), (660, 400)], outline='white', width=38)
    # Vertical slats inside
    draw_capsule_line(d, (460, 450), (476, 650), 32)
    draw_capsule_line(d, (512, 450), (512, 650), 32)
    draw_capsule_line(d, (564, 450), (548, 650), 32)
    save_icon(im, 'vc_delete.png')

# ==========================================
# 20. vc_privacy (Privacy Category)
# ==========================================
def gen_privacy():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    draw_clean_shield(d)
    # Keyhole emblem in center
    d.ellipse([484, 440, 540, 496], fill='white')
    d.polygon([(496, 490), (528, 490), (524, 560), (500, 560)], fill='white')
    save_icon(im, 'vc_privacy.png')

# ==========================================
# 21. vc_settings (Settings Category)
# ==========================================
def gen_settings():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    cx, cy = 512, 512
    # 8-tooth gear
    teeth = 8
    outer_r = 190
    inner_r = 145
    d.ellipse([cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r], outline='white', width=40)
    for i in range(teeth):
        angle = i * (2 * math.pi / teeth)
        tx = cx + math.cos(angle) * (outer_r + 20)
        ty = cy + math.sin(angle) * (outer_r + 20)
        sx = cx + math.cos(angle) * inner_r
        sy = cy + math.sin(angle) * inner_r
        draw_capsule_line(d, (int(sx), int(sy)), (int(tx), int(ty)), 44)
    # Central hole
    d.ellipse([cx - 55, cy - 55, cx + 55, cy + 55], outline='white', width=38)
    save_icon(im, 'vc_settings.png')

# ==========================================
# 22. vc_region (Region Category)
# ==========================================
def gen_region():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Globe outer circle
    d.ellipse([320, 320, 704, 704], outline='white', width=42)
    # Equator line
    draw_capsule_line(d, (320, 512), (704, 512), 38)
    # Latitude arcs
    d.arc([320, 380, 704, 644], start=0, end=180, fill='white', width=36)
    d.arc([320, 380, 704, 644], start=180, end=0, fill='white', width=36)
    # Vertical meridian ellipse
    d.ellipse([412, 320, 612, 704], outline='white', width=38)
    save_icon(im, 'vc_region.png')

# ==========================================
# 23. vc_members (Members Category)
# ==========================================
def gen_members():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # User 1 (Center)
    d.ellipse([452, 280, 572, 400], outline='white', width=40)
    d.arc([380, 420, 644, 640], start=180, end=0, fill='white', width=40)
    draw_capsule_line(d, (380, 530), (380, 700), 40)
    draw_capsule_line(d, (644, 530), (644, 700), 40)
    # User 2 (Right shoulder)
    d.ellipse([640, 340, 740, 440], outline='white', width=34)
    d.arc([590, 460, 790, 640], start=180, end=0, fill='white', width=34)
    # User 3 (Left shoulder)
    d.ellipse([284, 340, 384, 440], outline='white', width=34)
    d.arc([234, 460, 434, 640], start=180, end=0, fill='white', width=34)
    save_icon(im, 'vc_members.png')

# ==========================================
# ==========================================
# 24. vc_host (Host Category)
# ==========================================
def gen_host():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    peaks = [(310, 430), (410, 490), (512, 350), (614, 490), (714, 430), (690, 640), (334, 640)]
    d.polygon(peaks, outline='white', width=42)
    for px, py in [(310, 430), (512, 350), (714, 430)]:
        d.ellipse([px - 22, py - 22, px + 22, py + 22], fill='white')
    draw_capsule_line(d, (320, 680), (704, 680), 40)
    draw_capsule_line(d, (512, 240), (512, 310), 32)
    draw_capsule_line(d, (477, 275), (547, 275), 32)
    save_icon(im, 'vc_host.png')

# ==========================================
# 25. vc_setup (Setup Wizard - Crossed Tools)
# ==========================================
def gen_setup():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Wrench diagonal (top-left to bottom-right)
    draw_capsule_line(d, (350, 350), (674, 674), 44)
    # Wrench open jaw on top-left
    d.arc([270, 270, 430, 430], start=135, end=315, fill='white', width=44)
    # Screwdriver diagonal (top-right to bottom-left)
    draw_capsule_line(d, (674, 350), (350, 674), 44)
    # Screwdriver handle (bottom-left)
    d.rounded_rectangle([300, 620, 400, 720], radius=24, outline='white', width=40)
    # Screwdriver tip (top-right)
    draw_capsule_line(d, (650, 330), (690, 370), 44)
    # Decorative sparkle
    draw_capsule_line(d, (512, 260), (512, 320), 28)
    draw_capsule_line(d, (482, 290), (542, 290), 28)
    save_icon(im, 'vc_setup.png')

# ==========================================
# 26. vc_hubs (Themed Hubs - Price / Tag)
# ==========================================
def gen_hubs():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Slanted tag shape
    # Points for a tag pointing down-left, clipped top
    pts = [(450, 260), (680, 260), (760, 340), (760, 580), (620, 720), (380, 720), (380, 480), (450, 410)]
    # Simplified upright tag
    tag_pts = [(420, 280), (604, 280), (684, 360), (684, 700), (340, 700), (340, 360)]
    d.polygon(tag_pts, outline='white', width=44)
    # Tag hole
    d.ellipse([488, 360, 536, 408], fill='white')
    # Cord loop from hole
    d.arc([460, 230, 564, 370], start=180, end=0, fill='white', width=34)
    # Star / hashtag detail inside tag
    draw_capsule_line(d, (512, 470), (512, 590), 38)
    draw_capsule_line(d, (452, 530), (572, 530), 38)
    save_icon(im, 'vc_hubs.png')

# ==========================================
# 27. vc_permanent (Permanent / Presets - Floppy Disk)
# ==========================================
def gen_permanent():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Outer floppy shape with beveled top-right corner
    pts = [(340, 300), (634, 300), (684, 350), (684, 720), (340, 720)]
    d.polygon(pts, outline='white', width=42)
    # Metal slider on top
    d.rounded_rectangle([404, 300, 620, 450], radius=16, outline='white', width=38)
    # Slider cutout hole
    d.rounded_rectangle([444, 330, 484, 410], radius=8, fill='white')
    # Big label paper area on bottom
    d.rounded_rectangle([390, 500, 634, 700], radius=20, outline='white', width=36)
    # Lines on label
    draw_capsule_line(d, (424, 560), (600, 560), 28)
    draw_capsule_line(d, (424, 620), (560, 620), 28)
    save_icon(im, 'vc_permanent.png')

# ==========================================
# 28. vc_maintenance (Maintenance & Logs - Audit Clipboard)
# ==========================================
def gen_maintenance():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Clipboard board
    d.rounded_rectangle([340, 310, 684, 720], radius=36, outline='white', width=42)
    # Clip on top
    d.rounded_rectangle([434, 250, 590, 330], radius=20, outline='white', width=38)
    d.ellipse([492, 280, 532, 320], fill='white')
    # Checklist checkmark 1
    draw_capsule_line(d, (390, 420), (420, 450), 32)
    draw_capsule_line(d, (420, 450), (460, 390), 32)
    draw_capsule_line(d, (490, 420), (630, 420), 32)
    # Checklist checkmark 2
    draw_capsule_line(d, (390, 520), (420, 550), 32)
    draw_capsule_line(d, (420, 550), (460, 490), 32)
    draw_capsule_line(d, (490, 520), (630, 520), 32)
    # Line 3
    draw_capsule_line(d, (390, 620), (600, 620), 32)
    save_icon(im, 'vc_maintenance.png')

# ==========================================
# 29. vc_interface (Voice Interface & Gaming - Controller)
# ==========================================
def gen_interface():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Gamepad main body pill
    d.rounded_rectangle([290, 360, 734, 660], radius=110, outline='white', width=44)
    # D-pad (left side)
    draw_capsule_line(d, (410, 450), (410, 570), 34)
    draw_capsule_line(d, (350, 510), (470, 510), 34)
    # 4 Action buttons (right side)
    d.ellipse([584, 450, 614, 480], fill='white')  # Top (Y)
    d.ellipse([584, 540, 614, 570], fill='white')  # Bottom (A)
    d.ellipse([539, 495, 569, 525], fill='white')  # Left (X)
    d.ellipse([629, 495, 659, 525], fill='white')  # Right (B)
    # Center menu pills
    draw_capsule_line(d, (490, 510), (510, 510), 24)
    draw_capsule_line(d, (518, 510), (538, 510), 24)
    save_icon(im, 'vc_interface.png')

# ==========================================
# 30. vc_overview (System Overview - Sparkle Globe)
# ==========================================
def gen_overview():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Globe sphere
    d.ellipse([340, 330, 684, 674], outline='white', width=42)
    # Equator line
    draw_capsule_line(d, (340, 502), (684, 502), 38)
    # Latitude arcs
    d.arc([340, 390, 684, 614], start=0, end=180, fill='white', width=34)
    d.arc([340, 390, 684, 614], start=180, end=0, fill='white', width=34)
    # Meridian vertical ellipse
    d.ellipse([424, 330, 600, 674], outline='white', width=38)
    # Radiating sparkle star top-right
    draw_capsule_line(d, (710, 260), (710, 340), 30)
    draw_capsule_line(d, (670, 300), (750, 300), 30)
    save_icon(im, 'vc_overview.png')

# ==========================================
# 31. vc_leaderboard (Leaderboard / Trophy)
# ==========================================
def gen_leaderboard():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Cup body
    pts = [(380, 300), (644, 300), (614, 520), (512, 580), (410, 520)]
    d.polygon(pts, outline='white', width=40)
    # Left handle
    d.arc([300, 330, 420, 470], start=90, end=270, fill='white', width=36)
    # Right handle
    d.arc([604, 330, 724, 470], start=270, end=90, fill='white', width=36)
    # Stem & base
    draw_capsule_line(d, (512, 580), (512, 650), 40)
    draw_capsule_line(d, (410, 660), (614, 660), 40)
    draw_capsule_line(d, (380, 700), (644, 700), 38)
    # Star emblem in cup center
    draw_capsule_line(d, (512, 380), (512, 450), 32)
    draw_capsule_line(d, (477, 415), (547, 415), 32)
    save_icon(im, 'vc_leaderboard.png')

# ==========================================
# 32. vc_bitrate (Audio Bitrate - Speaker & Waves)
# ==========================================
def gen_bitrate():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Speaker box + cone
    speaker_pts = [(320, 420), (410, 420), (500, 320), (500, 704), (410, 604), (320, 604)]
    d.polygon(speaker_pts, outline='white', width=42)
    # Expanding soundwave arcs
    d.arc([470, 420, 590, 604], start=300, end=60, fill='white', width=38)
    d.arc([510, 350, 680, 674], start=300, end=60, fill='white', width=38)
    d.arc([550, 280, 770, 744], start=300, end=60, fill='white', width=38)
    save_icon(im, 'vc_bitrate.png')

# ==========================================
# 33. vc_soundboard (Soundboard - Musical Notes)
# ==========================================
def gen_soundboard():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Left note head
    d.ellipse([340, 560, 430, 650], fill='white')
    # Right note head
    d.ellipse([540, 490, 630, 580], fill='white')
    # Stems
    draw_capsule_line(d, (420, 600), (420, 340), 38)
    draw_capsule_line(d, (620, 530), (620, 270), 38)
    # Connecting beam
    d.polygon([(400, 340), (640, 270), (640, 330), (400, 400)], fill='white')
    save_icon(im, 'vc_soundboard.png')

# ==========================================
# 34. vc_video (Video & Screen Share)
# ==========================================
def gen_video():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Camera body
    d.rounded_rectangle([310, 360, 590, 660], radius=44, outline='white', width=42)
    # Lens trapezoid on right
    lens_pts = [(590, 450), (714, 380), (714, 640), (590, 570)]
    d.polygon(lens_pts, outline='white', width=40)
    # Small record circle light
    d.ellipse([360, 410, 400, 450], fill='white')
    save_icon(im, 'vc_video.png')


def main():
    print("Generating all 34 custom VoiceClaw pastel watercolor icons...")
    gen_lock()
    gen_unlock()
    gen_ghost()
    gen_reveal()
    gen_rename()
    gen_limit()
    gen_mute()
    gen_unmute()
    gen_trust()
    gen_untrust()
    gen_invite()
    gen_kick()
    gen_block()
    gen_unblock()
    gen_knock()
    gen_claim()
    gen_transfer()
# ==========================================
# 35. vc_activity (Discord Games & Activities - Gamepad)
# ==========================================
def gen_activity():
    im = get_base_card()
    d = ImageDraw.Draw(im)
    # Controller outline / body
    d.rounded_rectangle([290, 390, 734, 634], radius=110, outline='white', width=42)
    # Left D-pad
    draw_capsule_line(d, (370, 512), (450, 512), 34)
    draw_capsule_line(d, (410, 472), (410, 552), 34)
    # Right action buttons
    d.ellipse([615, 450, 655, 490], fill='white')
    d.ellipse([615, 534, 655, 574], fill='white')
    d.ellipse([573, 492, 613, 532], fill='white')
    d.ellipse([657, 492, 697, 532], fill='white')
    # Center select / start pills
    draw_capsule_line(d, (490, 512), (506, 512), 16)
    draw_capsule_line(d, (518, 512), (534, 512), 16)
    save_icon(im, 'vc_activity.png')


def main():
    gen_lock()
    gen_unlock()
    gen_ghost()
    gen_reveal()
    gen_claim()
    gen_transfer()
    gen_block()
    gen_unblock()
    gen_kick()
    gen_mute()
    gen_unmute()
    gen_trust()
    gen_untrust()
    gen_limit()
    gen_rename()
    gen_knock()
    gen_invite()
    gen_info()
    gen_delete()
    gen_privacy()
    gen_settings()
    gen_region()
    gen_members()
    gen_host()
    # New system & guide icons
    gen_setup()
    gen_hubs()
    gen_permanent()
    gen_maintenance()
    gen_interface()
    gen_overview()
    gen_leaderboard()
    gen_bitrate()
    gen_soundboard()
    gen_video()
    gen_activity()
    print("All 35 icons successfully generated in assets/icons/ and assets/icons/128x128/!")


if __name__ == '__main__':
    main()

