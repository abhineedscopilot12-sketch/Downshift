"""Downshift: which of your LLM calls can run on a cheaper Nemotron tier?"""
import asyncio, json, os, random, re, sys, time
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from openai import AsyncOpenAI

load_dotenv()
BASE = os.getenv("TF_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
TIERS = [  # cheapest first. Run `python downshift.py models` and fix IDs/prices in .env if needed
    dict(key="nano", label="The Intern", model=os.getenv("NANO_MODEL", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"), pin=.06, pout=.24),
    dict(key="super", label="The Manager", model=os.getenv("SUPER_MODEL", "nvidia/Nemotron-3-Super-120B-A12B"), pin=.30, pout=.90),
    dict(key="ultra", label="The CEO", model=os.getenv("ULTRA_MODEL", "nvidia/Nemotron-3-Ultra-550B-A55B"), pin=1.0, pout=3.0),
]
LABEL = {t["key"]: t["label"] for t in TIERS}
SYS = "Follow the requested output format exactly. Be brief."

# ---------- objective checks (no LLM judge) ----------
def parse_json(s):
    m = re.search(r"\{.*\}", s or "", re.S)
    try: return json.loads(m.group(0)) if m else None
    except Exception: return None

def canon(r, out):
    """Normalised answer, or None if the format is invalid."""
    t = r["task"]
    if t == "classify":
        v = (out or "").strip().lower().strip(".'\"`")
        return v if v in r["allowed"] else None
    if t == "extract":
        j = parse_json(out)
        if not j or not all(k in j for k in r["expected"]): return None
        return json.dumps({k: str(j[k]).strip().lower() for k in r["expected"]}, sort_keys=True)
    m = re.findall(r"ANSWER:\s*\$?(-?[\d,]*\.?\d+)", out or "")
    return float(m[-1].replace(",", "")) if m else None

def gold(r, out):
    c = canon(r, out)
    if c is None: return False
    if r["task"] == "classify": return c == r["expected"]
    if r["task"] == "extract": return json.loads(c) == {k: str(v).strip().lower() for k, v in r["expected"].items()}
    return abs(c - r["expected"]) < 1e-6

# ---------- replay every request on every tier ----------
async def call(cli, sem, model, prompt, temp):
    async with sem:
        for i in range(4):
            try:
                t0 = time.time()
                r = await cli.chat.completions.create(model=model, temperature=temp, max_tokens=1024,
                    messages=[{"role": "system", "content": SYS}, {"role": "user", "content": prompt}])
                return r.choices[0].message.content or "", r.usage.prompt_tokens, r.usage.completion_tokens, time.time() - t0
            except Exception as e:
                if i == 3: print("API error:", repr(e)[:200], file=sys.stderr); return "", 0, 0, 0.0
                await asyncio.sleep(2 ** i)

async def replay(rows):
    cli = AsyncOpenAI(base_url=BASE, api_key=os.environ["TF_API_KEY"])
    sem = asyncio.Semaphore(int(os.getenv("CONCURRENCY", "16"))); done = [0]
    async def one(r):
        t = {}
        for i, tr in enumerate(TIERS):
            last = i == len(TIERS) - 1
            jobs = [call(cli, sem, tr["model"], r["prompt"], 0)] + ([] if last else [call(cli, sem, tr["model"], r["prompt"], .8)])
            (o, pi, po, lat), *rest = await asyncio.gather(*jobs)
            cost = (pi * tr["pin"] + po * tr["pout"]) / 1e6; gcost = 0; gate = True
            if rest:  # confidence gate: valid format AND second sample agrees. Never peeks at the gold answer.
                o2, pi2, po2, l2 = rest[0]; gcost = (pi2 * tr["pin"] + po2 * tr["pout"]) / 1e6; lat = max(lat, l2)
                gate = canon(r, o) is not None and canon(r, o) == canon(r, o2)
            t[tr["key"]] = dict(ok=gold(r, o), gate=gate, cost=cost, gcost=gcost, lat=lat, pi=pi, po=po)
        done[0] += 1
        if done[0] % 20 == 0: print(f"  {done[0]}/{len(rows)} requests judged. The Intern is sweating.", flush=True)
        return dict(id=r["id"], task=r["task"], t=t)
    return await asyncio.gather(*[one(r) for r in rows])

# ---------- cascade + report ----------
def cascade(r):
    cost = lat = 0; path = []
    for i, tr in enumerate(TIERS):
        x = r["t"][tr["key"]]; cost += x["cost"] + x["gcost"]; lat += x["lat"]; path.append(tr["key"])
        if x["gate"] or i == len(TIERS) - 1: return tr["key"], x["ok"], cost, lat, path

def pct(a, p):
    a = sorted(a); return a[min(len(a) - 1, int(p * len(a)))] if a else 0

def build(res, base):
    n = len(res); cs = [cascade(r) for r in res]; S = dict(n=n, tiers={})
    for tr in TIERS:
        xs = [r["t"][tr["key"]] for r in res]
        S["tiers"][tr["key"]] = dict(label=tr["label"], acc=sum(x["ok"] for x in xs) / n, cost=sum(x["cost"] for x in xs),
                                     p50=pct([x["lat"] for x in xs], .5), p95=pct([x["lat"] for x in xs], .95))
    S["cascade"] = dict(acc=sum(c[1] for c in cs) / n, cost=sum(c[2] for c in cs), p50=pct([c[3] for c in cs], .5), p95=pct([c[3] for c in cs], .95),
                        share={k: sum(c[0] == k for c in cs) / n for k in LABEL})
    top = S["tiers"][TIERS[-1]["key"]]["cost"]
    S["saving_pct"] = 100 * (1 - S["cascade"]["cost"] / top) if top else 0
    bp, bo = float(os.getenv("BASE_PIN", 0)), float(os.getenv("BASE_POUT", 0))
    u = TIERS[-1]["key"]; S["closed"] = sum(r["t"][u]["pi"] * bp + r["t"][u]["po"] * bo for r in res) / 1e6 if bp or bo else None
    S["by_task"] = {}
    for k in sorted({r["task"] for r in res}):
        z = [c for r, c in zip(res, cs) if r["task"] == k]
        S["by_task"][k] = dict(n=len(z), acc=sum(c[1] for c in z) / len(z), intern=sum(c[0] == TIERS[0]["key"] for c in z) / len(z))
    esc, ok1, wrong = [], [], []
    for r, c in zip(res, cs):
        k, ok, _, _, path = c; head = f"{r['id']} ({r['task']}): "
        if not ok: wrong.append(head + f"{LABEL[k]} answered with total confidence and was wrong ❌")
        elif len(path) > 1: esc.append(head + ", ".join(f"{LABEL[p]} wasn't sure" for p in path[:-1]) + f" → {LABEL[k]} nailed it ✅")
        else: ok1.append(head + f"{LABEL[k]} handled it ✅ The CEO stayed asleep.")
    return dict(summary=S, story=esc[:5] + ok1[:3] + wrong[:4], baseline=base)

async def baseline():  # Tavily runtime call: evidence for the closed-model price baseline
    k = os.getenv("TAVILY_API_KEY")
    if not k: return None
    q = os.getenv("BASELINE_QUERY", "GPT-4o API pricing per million tokens")
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = (await c.post("https://api.tavily.com/search", headers={"Authorization": f"Bearer {k}"}, json={"query": q, "max_results": 1})).json()
        x = r["results"][0]; return dict(query=q, title=x["title"], url=x["url"], snippet=x["content"][:300])
    except Exception as e:
        print("Tavily error:", repr(e)[:150], file=sys.stderr); return None

# ---------- synthetic dataset with known answers ----------
def gen(n=300, seed=7, path="data/sample.jsonl"):
    R = random.Random(seed); rows = []
    LAB = {"billing": ["I was charged twice this month", "my invoice amount looks wrong", "my refund never arrived"],
           "login": ["I can't sign in to my account", "the password reset email never arrives", "my 2FA code keeps failing"],
           "bug": ["the export button crashes the app", "the page freezes when I upload a file", "the dashboard shows a blank screen"],
           "feature": ["please add dark mode", "can you support CSV import", "we need an API for reports"]}
    fluff = ["Hi team,", "URGENT!!", "hello???", "Been a customer for 3 years.", "Not sure who to ask."]
    NAMES = ["Priya Nair", "Tom Becker", "Aiko Tanaka", "Luis Ortega", "Meera Rao"]; CITIES = ["Pune", "Berlin", "Osaka", "Lisbon", "Austin"]
    for i in range(n // 3):
        lab = R.choice(list(LAB)); t = R.choice(LAB[lab])
        if R.random() < .5: t = f"{R.choice(fluff)} {t}. {R.choice(fluff)} Also, nice weather today."
        rows.append(dict(id=f"c{i}", task="classify", allowed=list(LAB), expected=lab,
                         prompt=f"Classify this support ticket as one of {list(LAB)}. Reply with the label only.\n\n{t}"))
    for i in range(n // 3):
        nm, ct, amt = R.choice(NAMES), R.choice(CITIES), R.randrange(100, 9999)
        d1, d2 = (f"2026-{R.randint(1, 12):02d}-{R.randint(1, 28):02d}" for _ in "ab")
        t = (f"Invoice for {nm} ({ct}). Amount due: {amt} USD. Due: {d1}." if R.random() < .4 else
             f"{nm} of {ct} ordered on {d2}. The first quote of {amt + R.randint(50, 500)} USD was revised down; the final amount is {amt} USD, payable by {d1}.")
        rows.append(dict(id=f"e{i}", task="extract", expected=dict(name=nm, amount=str(amt), due_date=d1),
                         prompt=f"Extract the final amount due and due date as JSON with keys name, amount (digits only), due_date (YYYY-MM-DD).\n\n{t}\n\nReply with JSON only."))
    for i in range(n - 2 * (n // 3)):
        v = R.randint(5, 40); s = f"A shop starts with {v} crates."
        for _ in range(R.randint(2, 6)):
            op = R.choice("+-*/")
            if op == "+": a = R.randint(2, 30); v += a; s += f" It receives {a} more crates."
            elif op == "-": a = R.randint(1, max(1, v // 2)); v -= a; s += f" It sells {a} crates."
            elif op == "*": m = R.choice([2, 3]); v *= m; s += f" A promotion multiplies the stock by {m}."
            elif v % 2 == 0: v //= 2; s += " Half the crates move to a warehouse."
        p, c = R.randint(2, 9), R.randint(2, 5)
        s += f" The shop has 3 cashiers and opens at 9am. Each remaining crate holds {p} apples worth {c} dollars each. What is the total value of the apples in the shop, in dollars? Think briefly, then finish with 'ANSWER: <number>'."
        rows.append(dict(id=f"m{i}", task="math", expected=v * p * c, prompt=s))
    R.shuffle(rows); os.makedirs("data", exist_ok=True)
    open(path, "w").write("\n".join(json.dumps(r) for r in rows) + "\n"); print(f"Wrote {len(rows)} requests to {path}")

# ---------- web app ----------
app = FastAPI(); LIVE_MAX = 30; budget = [int(os.getenv("LIVE_BUDGET", "300"))]

@app.get("/")
def home(): return FileResponse("index.html")

@app.get("/api/results")
def results():
    if not os.path.exists("results.json"): raise HTTPException(404, "Run: python downshift.py run data/sample.jsonl")
    return json.load(open("results.json"))

def valid(r): return isinstance(r, dict) and {"id", "task", "prompt", "expected"} <= set(r) and r["task"] in ("classify", "extract", "math") and (r["task"] != "classify" or "allowed" in r)

@app.post("/api/run")
async def live(body: dict):
    try: rows = [json.loads(l) for l in str(body.get("jsonl", "")).splitlines() if l.strip()][:LIVE_MAX]
    except Exception: raise HTTPException(400, "Not valid JSONL.")
    if not rows or not all(valid(r) for r in rows): raise HTTPException(400, "Each line needs id, task (classify|extract|math), prompt, expected (+allowed for classify).")
    if budget[0] < len(rows): raise HTTPException(429, "Live demo budget used up. Run it locally.")
    budget[0] -= len(rows)
    return build(await replay(rows), None)

def main():
    c = sys.argv[1] if len(sys.argv) > 1 else ""
    if c == "models":
        async def m():
            for x in (await AsyncOpenAI(base_url=BASE, api_key=os.environ["TF_API_KEY"]).models.list()).data:
                if "nemotron" in x.id.lower(): print(x.id)
        asyncio.run(m())
    elif c == "gen": gen()
    elif c == "run":
        rows = [json.loads(l) for l in open(sys.argv[2]) if l.strip()][:int(sys.argv[3]) if len(sys.argv) > 3 else None]
        async def go():
            print(f"The Intern, Manager and CEO are clocking in for {len(rows)} requests...")
            out = build(await replay(rows), await baseline()); json.dump(out, open("results.json", "w"), indent=1)
            s = out["summary"]; print(f"Saved {s['saving_pct']:.0f}% | accuracy {s['cascade']['acc']:.1%} | shares {s['cascade']['share']} -> results.json")
        asyncio.run(go())
    elif c == "serve":
        import uvicorn; uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
    else: print("usage: python downshift.py models | gen | run <file> [limit] | serve")

if __name__ == "__main__": main()
