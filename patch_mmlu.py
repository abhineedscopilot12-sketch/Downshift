p = "downshift.py"; s = open(p).read()
MCQ = '''    if t == "mcq":
        m = re.findall(r"ANSWER:\\s*\\(?([A-J])\\b", out or "")
        return m[-1] if m else None
'''
FN = '''def mmlu(n=120, seed=7, path="data/mmlu.jsonl"):
    """Pull hard public MMLU-Pro questions (MIT license) through the Hugging Face datasets-server API."""
    R = random.Random(seed); rows = []; per = 20
    with httpx.Client(timeout=60) as c:
        for o in R.sample(range(0, 12000, per), -(-n // per)):
            r = c.get("https://datasets-server.huggingface.co/rows", params=dict(dataset="TIGER-Lab/MMLU-Pro", config="default", split="test", offset=o, length=per))
            r.raise_for_status()
            for x in r.json()["rows"]:
                q = x["row"]; opts = "\\n".join(f"{'ABCDEFGHIJ'[i]}. {t}" for i, t in enumerate(q["options"]))
                rows.append(dict(id=f"q{q['question_id']}", task="mcq", expected=q["answer"],
                                 prompt=f"Answer this {q['category']} question.\\n\\n{q['question']}\\n\\n{opts}\\n\\nThink step by step, then finish with 'ANSWER: <letter>'."))
    R.shuffle(rows); rows = rows[:n]; os.makedirs("data", exist_ok=True)
    open(path, "w").write("\\n".join(json.dumps(r) for r in rows) + "\\n"); print(f"Wrote {len(rows)} MMLU-Pro questions to {path}")

'''
R = [('    m = re.findall(r"ANSWER:', MCQ + '    m = re.findall(r"ANSWER:'),
     ('if r["task"] == "classify": return c == r["expected"]', 'if r["task"] in ("classify", "mcq"): return c == r["expected"]'),
     ('r["task"] in ("classify", "extract", "math")', 'r["task"] in ("classify", "extract", "math", "mcq")'),
     ('    elif c == "gen": gen()', '    elif c == "gen": gen()\n    elif c == "mmlu": mmlu(int(sys.argv[2]) if len(sys.argv) > 2 else 120)'),
     ('# ---------- web app', FN + '# ---------- web app')]
for a, b in R:
    assert s.count(a) == 1, "anchor not found: " + a[:40]
    s = s.replace(a, b)
open(p, "w").write(s); print("Patched. Now run: python downshift.py mmlu 40")