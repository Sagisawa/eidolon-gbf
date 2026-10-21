from pathlib import Path

p = Path("characters/characters.toml")
text = p.read_text(encoding="utf-8")
text = text.replace(
    'photo_appearance = "1girl, solo, draph horns, blindfold, purple hair, katana, kimono, cleavage"',
    'photo_appearance = "1girl, solo, draph horns, blindfold, purple hair, purple eyes, katana, kimono, cleavage"',
)
text = text.replace(
    'photo_appearance = "1girl, solo, blonde hair, tan skin, visor hat, bikini top, gyaru fashion, bright smile"',
    'photo_appearance = "1girl, solo, blonde hair, brown eyes, tan skin, visor hat, bikini top, gyaru fashion, bright smile"',
)
text = text.replace(
    'photo_appearance = "1girl, solo, blue hair, crying smile, rainbow bow, colorful dress, beret"',
    'photo_appearance = "1girl, solo, blue hair, blue eyes, crying smile, rainbow bow, colorful dress, beret"',
)
p.write_text(text, encoding="utf-8")
print("Updated characters.toml successfully")
