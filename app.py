"""Serveur Flask (threads) + boucle asyncio dédiée + ProcessPool + nœuds sockets."""
import asyncio, json, os, queue, random, threading, time, uuid
from concurrent.futures import ProcessPoolExecutor
from flask import Flask, Response, jsonify, render_template, request
import engine, scenes

app = Flask(__name__)
WORKERS = min(8, int(os.getenv("AURA_WORKERS", os.cpu_count() or 2)))
REMOTES = [x for x in os.getenv("AURA_NODES", "").split(",") if x]   # ex: 192.168.1.20:9001,127.0.0.1:9001
HFILE = "history.json"
HIST, JOBS, LOCK, SAVEQ = {}, {}, threading.Lock(), queue.Queue()
EXEC = LOOP = None


def _writer():   # thread dédié à la persistance (n'attend pas les requêtes web)
    while True:
        SAVEQ.get()
        with LOCK:
            data = json.dumps(HIST)
        with open(HFILE, "w", encoding="utf-8") as f:
            f.write(data)


def reward(e):
    """Récompense d'une toile = progrès de ressenti (après - avant, sur 10). None si pas de check-in."""
    if e.get("before") and e.get("after"):
        return (e["after"] - e["before"]) / 5
    return None


def choose_style(uid):
    """Bandit epsilon-greedy : apprend quel style de palette améliore le ressenti de CETTE personne."""
    with LOCK:
        done = [(e["style"], reward(e)) for e in HIST.get(uid, []) if reward(e) is not None]
    if random.random() < .3 or not done:
        return random.choice(scenes.STYLES)   # 30 % d'exploration
    avg = {s: [r for st, r in done if st == s] for s in scenes.STYLES}
    return max(scenes.STYLES, key=lambda s: sum(avg[s]) / len(avg[s]) if avg[s] else 0)   # exploitation


def trend(uid):
    with LOCK:
        v = [e["valence"] for e in HIST.get(uid, [])[-3:]]
    return len(v) >= 2 and sum(v) / len(v) < -.3


def clamp(v):
    try:
        return max(1, min(10, int(v)))
    except (TypeError, ValueError):
        return None


async def run_job(job, text, age, uid, before, photo=None):
    try:
        tr, style = trend(uid), choose_style(uid)
        res = await engine.pipeline(
            text, age, EXEC, job["q"].put,
            workers=WORKERS, style=style, trend=tr, remotes=REMOTES, photo=photo
        )
        if not res.get("safety"):
            b = res["brief"]
            eid = uuid.uuid4().hex[:8]
            res["entry_id"] = eid
            if tr:
                b["message"] += " Je remarque que les derniers jours sont lourds : j'ai allégé ce canevas pour toi."
            with LOCK:
                HIST.setdefault(uid, []).append(dict(
                    id=eid,
                    ts=time.time(),
                    emotion=b["emotion"],
                    valence=b["valence"] or 0,
                    scene="photo" if photo else b["scene"],
                    style=style,
                    before=before,
                    after=None,
                ))
            SAVEQ.put(1)
        job["result"] = res
        job["q"].put({"done": True})
    except Exception as e:
        job["q"].put({"error": f"{type(e).__name__}: {e}"})


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/generate")
def generate():
    b = request.form if request.form else (request.get_json(silent=True) or {})
    f = request.files.get("photo")
    photo = f.read(8_000_001) if (f and f.filename) else None
    if photo and len(photo) > 8_000_000:
        return jsonify(error="Photo trop lourde (8 Mo max)."), 400
    text = (b.get("text") or "").strip()[:4000]
    if len(text) < 3:
        return jsonify(error="Écris quelques mots."), 400
    jid = uuid.uuid4().hex[:10]
    job = {"q": queue.Queue(), "result": None}
    JOBS[jid] = job
    asyncio.run_coroutine_threadsafe(
        run_job(
            job,
            text,
            "enfant" if b.get("age") == "enfant" else "adulte",
            b.get("uid", "anon"),
            clamp(b.get("before")),
            photo,
        ),
        LOOP,
    )
    return jsonify(job=jid)


@app.get("/api/stream/<jid>")
def stream(jid):
    def gen():
        q = JOBS[jid]["q"]
        while True:
            ev = q.get()
            yield f"data: {json.dumps(ev)}\n\n"
            if ev.get("done") or ev.get("error"):
                break
    return Response(gen(), mimetype="text/event-stream")


@app.get("/api/result/<jid>")
def result(jid):
    return jsonify(JOBS.pop(jid)["result"])


@app.post("/api/checkin")
def checkin():
    b = request.get_json(force=True) or {}
    after, delta = clamp(b.get("after")), None
    with LOCK:
        for e in HIST.get(b.get("uid"), []):
            if e["id"] == b.get("id") and after:
                e["after"] = after
                delta = after - e["before"] if e.get("before") else None
    SAVEQ.put(1)
    return jsonify(ok=True, delta=delta)


@app.get("/api/history")
def history():
    with LOCK:
        return jsonify(HIST.get(request.args.get("uid"), [])[-14:])


def main():
    global EXEC, LOOP
    EXEC = ProcessPoolExecutor(WORKERS)
    LOOP = asyncio.new_event_loop()
    threading.Thread(target=LOOP.run_forever, daemon=True).start()
    threading.Thread(target=_writer, daemon=True).start()
    if os.path.exists(HFILE):
        with open(HFILE, encoding="utf-8") as f:
            HIST.update(json.load(f))
    print(f"AuraColor : {WORKERS} processus, nœuds distants : {REMOTES or 'aucun'}  ->  http://127.0.0.1:5000")
    app.run(threaded=True, port=5000)


if __name__ == "__main__":
    main()