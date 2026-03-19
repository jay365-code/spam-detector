import os
import sys

sys.path.append(os.path.dirname(__file__))

from app.agents.ibse_agent.candidate import CandidateGenerator

msg1 = "(광고)  3월 새로운곳 새로운시작~ 많은응원부탁드려요^^   연▶우      무료거부0801395051"
msg2 = "(광고)가게이전했습니다! 연락감사합니다!  #류준열#   ☎010-6851-2285    무료거부 0808700874"

def test_extract():
    extractor = CandidateGenerator()
    res1_40 = extractor.generate(msg1.replace(" ", ""), msg1, 40, 30)
    res2_40 = extractor.generate(msg2.replace(" ", ""), msg2, 40, 30)
    
    with open("test_out_utf8.txt", "w", encoding="utf-8") as f:
        f.write("=== MSG 1 ===\n")
        f.write("Top 30 (40 bytes):\n")
        for c in res1_40:
            f.write(f"[{c.score}] {c.text_original} -> tags: {c.anchor_tags}\n")
            
        f.write("\n=== MSG 2 ===\n")
        f.write("Top 30 (40 bytes):\n")
        for c in res2_40:
            f.write(f"[{c.score}] {c.text_original} -> tags: {c.anchor_tags}\n")

if __name__ == "__main__":
    test_extract()
