p = "downshift.py"; s = open(p).read()
a = s.index("def gen("); b = s.index("# ---------- web app")
new = r'''def gen(n=300, seed=7, path="data/sample.jsonl"):
    R = random.Random(seed); rows = []
    MON = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    def fmt(d, st):
        y, m, dd = d
        return [f"{y}-{m:02d}-{dd:02d}", f"{MON[m-1]} {dd}, {y}", f"{dd} {MON[m-1][:3]} {y}", f"{dd:02d}/{m:02d}/{y % 100:02d} (DD/MM/YY)"][st]
    LAB = {"billing": ["I was charged twice this month", "my invoice amount looks wrong", "my refund never arrived"],
           "login": ["I can't sign in to my account", "the password reset email never arrives", "my 2FA code keeps failing"],
           "bug": ["the export button crashes the app", "the page freezes when I upload a file", "the dashboard shows a blank screen"],
           "feature": ["please add dark mode", "can you support CSV import", "we need an API for reports"]}
    fluff = ["Hi team,", "URGENT!!", "hello???", "Been a customer for 3 years.", "Not sure who to ask."]
    NAMES = ["Priya Nair", "Tom Becker", "Aiko Tanaka", "Luis Ortega", "Meera Rao"]; CITIES = ["Pune", "Berlin", "Osaka", "Lisbon", "Austin"]
    for i in range(n // 3):
        lab = R.choice(list(LAB)); t = R.choice(LAB[lab])
        if R.random() < .5:
            o = R.choice([l for l in LAB if l != lab])
            t = f"{R.choice(fluff)} Earlier {R.choice(LAB[o])}, but that is sorted now. What is blocking me today: {t}. {R.choice(fluff)}"
        elif R.random() < .5: t = f"{R.choice(fluff)} {t}. {R.choice(fluff)} Also, nice weather today."
        rows.append(dict(id=f"c{i}", task="classify", allowed=list(LAB), expected=lab,
                         prompt=f"Classify the customer's CURRENT unresolved issue as one of {list(LAB)}. Reply with the label only.\n\n{t}"))
    for i in range(n // 3):
        nm, ct, hard = R.choice(NAMES), R.choice(CITIES), R.random() < .5
        sub = R.randrange(500, 9000); dep = R.randrange(100, sub // 2) if hard else 0
        due = (2026, R.randint(1, 12), R.randint(1, 28)); oth = (2026, R.randint(1, 12), R.randint(1, 28))
        if hard:
            t = (f"{nm} of {ct} ordered on {fmt(oth, R.randrange(4))}. The first quote of {sub + R.randint(50, 500)} USD was revised. "
                 f"Final subtotal: {sub} USD. A deposit of {dep} USD was already paid. Amount due is the subtotal minus the deposit, payable by {fmt(due, R.randrange(4))}.")
        else: t = f"Invoice for {nm} ({ct}). Amount due: {sub} USD. Due: {fmt(due, 0)}."
        rows.append(dict(id=f"e{i}", task="extract", expected=dict(name=nm, amount=str(sub - dep), due_date=fmt(due, 0)),
                         prompt=f"Extract JSON with keys name (person's name only, no city), amount (digits only, the amount still due), due_date (YYYY-MM-DD).\n\n{t}\n\nReply with JSON only."))
    for i in range(n - 2 * (n // 3)):
        hard = R.random() < .5; v = R.randint(5, 40); s = f"A shop starts with {v} crates."
        for _ in range(R.randint(9, 14) if hard else R.randint(2, 4)):
            op = R.choice("+-*/")
            if op == "+": a = R.randint(2, 60 if hard else 30); v += a; s += f" It receives {a} more crates."
            elif op == "-": a = R.randint(1, max(1, v // 2)); v -= a; s += f" It sells {a} crates."
            elif op == "*": m = R.choice([2, 3, 5, 7] if hard else [2, 3]); v *= m; s += f" A promotion multiplies the stock by {m}."
            elif v % 2 == 0: v //= 2; s += " Half the crates move to a warehouse."
        p, c = (R.randint(12, 97), R.randint(13, 48)) if hard else (R.randint(2, 9), R.randint(2, 5))
        s += f" The shop has 3 cashiers and opens at 9am. Each remaining crate holds {p} apples worth {c} dollars each. What is the total value of the apples in the shop, in dollars? Think briefly, then finish with 'ANSWER: <number>'."
        rows.append(dict(id=f"m{i}", task="math", expected=v * p * c, prompt=s))
    R.shuffle(rows); os.makedirs("data", exist_ok=True)
    open(path, "w").write("\n".join(json.dumps(r) for r in rows) + "\n"); print(f"Wrote {len(rows)} requests to {path} (half easy, half hard)")

'''
open(p, "w").write(s[:a] + new + s[b:])
print("Patched gen(). Now run: python downshift.py gen")