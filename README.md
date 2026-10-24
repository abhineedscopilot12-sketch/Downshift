# Downshift: your AI bill, itemized

Replays LLM requests on NVIDIA Nemotron Nano, Super and Ultra via **Nebius Token Factory**, scores answers with objective checks (JSON schema, exact label, final number), and builds a cascade router: the cheap model answers first and escalates only when its confidence gate fails (invalid format, or a second sample disagrees). The gate never sees the gold answer. Reports accuracy, cost per 1,000 requests, latency and who did the work.

**Nemotron / Token Factory:** all inference runs through Token Factory's OpenAI-compatible API; parallel replay across three Nemotron tiers is what makes the benchmark cheap and fast. **Tavily:** one runtime search fetches the closed-model price source shown in the report.

## Run
```
pip install -r requirements.txt
cp .env.example .env        # add TF_API_KEY, TAVILY_API_KEY
python downshift.py models  # copy Nemotron IDs into .env
python downshift.py gen     # 300 synthetic requests with known answers
python downshift.py run data/sample.jsonl 30   # smoke test, then drop the 30
python downshift.py serve   # open http://localhost:8000
```
Input format (JSONL): `id, task (classify|extract|math), prompt, expected` (+ `allowed` for classify).
