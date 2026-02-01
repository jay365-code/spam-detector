
import unicodedata

text = "dⓢlp①③7⑤.cc"
normalized = unicodedata.normalize('NFKC', text)
print(f"Original: {text}")
print(f"Normalized: {normalized}")

if normalized == "dslp1375.cc":
    print("SUCCESS: NFKC handles it.")
else:
    print("FAIL: NFKC produced " + normalized)
