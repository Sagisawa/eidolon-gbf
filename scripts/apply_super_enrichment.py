# -*- coding: utf-8 -*-
import sys
from pathlib import Path

# Add current dir to sys.path
sys.path.insert(0, str(Path("scripts").resolve()))

from super_enrich_facts_part1 import FACTS as P1
from super_enrich_facts_part2 import SIX_DRAGONS as P2
from super_enrich_facts_part3 import SIX_DRAGONS_2 as P3
from super_enrich_facts_part4 import PRIMAL_BEASTS as P4

all_facts = {}
all_facts.update(P1)
all_facts.update(P2)
all_facts.update(P3)
all_facts.update(P4)

print(f"Total characters to enrich: {len(all_facts)}")

for cid, content in all_facts.items():
    file_path = Path("characters/facts") / f"{cid}.md"
    file_path.write_text(content.strip() + "\n", encoding="utf-8")
    lines = len(content.strip().splitlines())
    print(f"[{cid}] updated: {lines} lines")

print("All facts written successfully.")
