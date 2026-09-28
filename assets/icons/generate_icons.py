import os
from PIL import Image, ImageDraw

ICONS_DIR = os.path.dirname(os.path.abspath(__file__))

def create_base():
    # 256x256 supersampled for crisp antialiasing, will resize to 128x128
    im = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    return im, d

def finalize(im, filename):
    out = im.resize((128, 128), Image.Resampling.LANCZOS)
    path = os.path.join(ICONS_DIR, filename)
    out.save(path, format='PNG')
    print(f"Generated {filename}")

# 1. vc_lock
im, d = create_base()
d.arc([72, 32, 184, 144], start=180, end=0, fill='white', width=20)
d.line([(72, 88), (72, 110)], fill='white', width=20)
d.line([(184, 88), (184, 110)], fill='white', width=20)
d.rounded_rectangle([52, 104, 204, 224], radius=32, fill='white')
d.ellipse([116, 140, 140, 164], fill=(20, 20, 25))
d.polygon([(120, 160), (136, 160), (132, 192), (124, 192)], fill=(20, 20, 25))
finalize(im, "vc_lock.png")

# 2. vc_unlock
im, d = create_base()
d.arc([92, 16, 204, 128], start=180, end=0, fill='white', width=20)
d.line([(92, 72), (92, 110)], fill='white', width=20)
d.rounded_rectangle([52, 104, 204, 224], radius=32, fill='white')
d.ellipse([116, 140, 140, 164], fill=(20, 20, 25))
d.polygon([(120, 160), (136, 160), (132, 192), (124, 192)], fill=(20, 20, 25))
finalize(im, "vc_unlock.png")

# 3. vc_ghost
im, d = create_base()
d.ellipse([64, 32, 192, 160], fill='white')
d.rectangle([64, 96, 192, 200], fill='white')
# scalloped bottom
for x in [64, 96, 128, 160]:
    d.pieslice([x, 180, x + 32, 220], start=0, end=180, fill='white')
# eyes
d.ellipse([92, 96, 116, 124], fill=(20, 20, 25))
d.ellipse([140, 96, 164, 124], fill=(20, 20, 25))
finalize(im, "vc_ghost.png")

# 4. vc_reveal
im, d = create_base()
# eye contour
d.arc([32, 56, 224, 200], start=195, end=345, fill='white', width=18)
d.arc([32, 56, 224, 200], start=15, end=165, fill='white', width=18)
d.ellipse([96, 96, 160, 160], fill='white')
d.ellipse([112, 112, 144, 144], fill=(20, 20, 25))
d.ellipse([124, 118, 134, 128], fill='white')
finalize(im, "vc_reveal.png")

# 5. vc_rename
im, d = create_base()
# diagonal pencil body
d.polygon([(60, 196), (170, 86), (196, 112), (86, 222)], fill='white')
# tip
d.polygon([(36, 220), (60, 196), (86, 222)], fill='white')
d.polygon([(36, 220), (46, 210), (56, 220)], fill=(20, 20, 25))
# eraser cap
d.polygon([(170, 86), (196, 60), (222, 86), (196, 112)], fill='white')
finalize(im, "vc_rename.png")

# 6. vc_limit
im, d = create_base()
# center user
d.ellipse([100, 36, 156, 92], fill='white')
d.pieslice([68, 100, 188, 220], start=180, end=0, fill='white')
# right user
d.ellipse([160, 56, 204, 100], fill='white')
d.pieslice([140, 110, 236, 206], start=180, end=0, fill='white')
# left user
d.ellipse([52, 56, 96, 100], fill='white')
d.pieslice([20, 110, 116, 206], start=180, end=0, fill='white')
finalize(im, "vc_limit.png")

# 7. vc_mute
im, d = create_base()
# mic capsule
d.rounded_rectangle([100, 40, 156, 124], radius=28, fill='white')
d.arc([80, 72, 176, 148], start=0, end=180, fill='white', width=16)
d.line([(128, 148), (128, 196)], fill='white', width=16)
d.line([(96, 196), (160, 196)], fill='white', width=16)
# slash
d.line([(44, 44), (212, 212)], fill=(240, 70, 70), width=20)
finalize(im, "vc_mute.png")

# 8. vc_unmute
im, d = create_base()
d.rounded_rectangle([100, 40, 156, 124], radius=28, fill='white')
d.arc([80, 72, 176, 148], start=0, end=180, fill='white', width=16)
d.line([(128, 148), (128, 196)], fill='white', width=16)
d.line([(96, 196), (160, 196)], fill='white', width=16)
# sound waves
d.arc([168, 64, 216, 132], start=300, end=60, fill='white', width=14)
d.arc([40, 64, 88, 132], start=120, end=240, fill='white', width=14)
finalize(im, "vc_unmute.png")

# 9. vc_trust
im, d = create_base()
# shield
d.polygon([(128, 32), (208, 64), (208, 144), (128, 224), (48, 144), (48, 64)], fill='white')
# checkmark inside
d.line([(88, 132), (116, 160)], fill=(20, 20, 25), width=18)
d.line([(116, 160), (168, 96)], fill=(20, 20, 25), width=18)
finalize(im, "vc_trust.png")

# 10. vc_untrust
im, d = create_base()
d.polygon([(128, 32), (208, 64), (208, 144), (128, 224), (48, 144), (48, 64)], fill='white')
# minus symbol inside
d.rounded_rectangle([80, 118, 176, 138], radius=8, fill=(20, 20, 25))
finalize(im, "vc_untrust.png")

# 11. vc_invite
im, d = create_base()
# envelope
d.rounded_rectangle([36, 68, 200, 188], radius=16, outline='white', width=16)
d.line([(44, 76), (118, 132)], fill='white', width=14)
d.line([(192, 76), (118, 132)], fill='white', width=14)
# plus on top-right
d.ellipse([160, 36, 224, 100], fill=(20, 20, 25))
d.ellipse([164, 40, 220, 96], fill='white')
d.line([(192, 54), (192, 82)], fill=(20, 20, 25), width=8)
d.line([(178, 68), (206, 68)], fill=(20, 20, 25), width=8)
finalize(im, "vc_invite.png")

# 12. vc_kick
im, d = create_base()
# stylized boot/kick
d.polygon([(72, 48), (144, 48), (144, 128), (204, 160), (192, 196), (72, 196)], fill='white')
# dynamic motion lines
d.line([(40, 100), (60, 100)], fill='white', width=12)
d.line([(32, 136), (56, 136)], fill='white', width=12)
d.line([(40, 172), (60, 172)], fill='white', width=12)
finalize(im, "vc_kick.png")

# 13. vc_block
im, d = create_base()
# prohibition sign
d.ellipse([40, 40, 216, 216], outline='white', width=24)
d.line([(64, 64), (192, 192)], fill='white', width=24)
finalize(im, "vc_block.png")

# 14. vc_unblock
im, d = create_base()
d.ellipse([40, 40, 216, 216], outline='white', width=22)
d.line([(80, 128), (116, 164)], fill='white', width=20)
d.line([(116, 164), (176, 92)], fill='white', width=20)
finalize(im, "vc_unblock.png")

# 15. vc_knock
im, d = create_base()
# door
d.rounded_rectangle([64, 40, 156, 216], radius=12, fill='white')
d.ellipse([132, 124, 148, 140], fill=(20, 20, 25))
# sound/vibration waves
d.arc([144, 64, 204, 124], start=300, end=60, fill='white', width=12)
d.arc([144, 48, 224, 140], start=300, end=60, fill='white', width=12)
finalize(im, "vc_knock.png")

# 16. vc_claim
im, d = create_base()
# crown
d.polygon([(48, 184), (48, 88), (88, 128), (128, 64), (168, 128), (208, 88), (208, 184)], fill='white')
d.rounded_rectangle([40, 184, 216, 204], radius=6, fill='white')
d.ellipse([40, 76, 56, 92], fill='white')
d.ellipse([120, 52, 136, 68], fill='white')
d.ellipse([200, 76, 216, 92], fill='white')
finalize(im, "vc_claim.png")

# 17. vc_transfer
im, d = create_base()
# arrow 1 (top right)
d.line([(56, 96), (180, 96)], fill='white', width=20)
d.polygon([(160, 68), (208, 96), (160, 124)], fill='white')
# arrow 2 (bottom left)
d.line([(76, 160), (200, 160)], fill='white', width=20)
d.polygon([(96, 132), (48, 160), (96, 188)], fill='white')
finalize(im, "vc_transfer.png")

# 18. vc_info
im, d = create_base()
d.ellipse([40, 40, 216, 216], outline='white', width=20)
d.ellipse([116, 76, 140, 100], fill='white')
d.rounded_rectangle([116, 116, 140, 180], radius=8, fill='white')
finalize(im, "vc_info.png")

# 19. vc_delete
im, d = create_base()
# trash can lid
d.rounded_rectangle([52, 60, 204, 76], radius=6, fill='white')
d.rounded_rectangle([104, 40, 152, 60], radius=6, fill='white')
# can body
d.polygon([(64, 88), (76, 216), (180, 216), (192, 88)], fill='white')
# slots inside
d.rounded_rectangle([92, 108, 104, 196], radius=4, fill=(20, 20, 25))
d.rounded_rectangle([122, 108, 134, 196], radius=4, fill=(20, 20, 25))
d.rounded_rectangle([152, 108, 164, 196], radius=4, fill=(20, 20, 25))
finalize(im, "vc_delete.png")

print("All 19 custom VoiceClaw icons generated successfully!")
