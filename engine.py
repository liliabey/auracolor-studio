"""Pipeline Paint-by-Number orchestré en asyncio. Étapes CPU-bound -> ProcessPool ; I/O (LLM) -> threads ;
placement des numéros -> pool local + nœuds distants (sockets TCP)."""
import asyncio, base64, io, os, time, zlib
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
import brain, dist, scenes

SAFE = ("Ce que tu écris semble très lourd, et ta sécurité compte plus que n'importe quel coloriage. "
        "Si tu penses à te faire du mal, parle dès maintenant à une personne de confiance ou appelle les urgences "
        "(Tunisie : SAMU 190 · Europe : 112 · France : 3114). Tu n'as pas à porter ça en silence.")


def png(a):
    b = io.BytesIO(); Image.fromarray(a).save(b, "PNG", compress_level=3)
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def kmeans(arr, k, iters=10, seed=0):
    px = arr.reshape(-1, 3).astype(np.float32); r = np.random.default_rng(seed)
    s = px[r.choice(len(px), min(30000, len(px)), replace=False)]
    c = s[r.choice(len(s), k, replace=False)]
    for _ in range(iters):
        a = ((s[:, None] - c[None]) ** 2).sum(-1).argmin(1)
        for j in range(k):
            if (a == j).any(): c[j] = s[a == j].mean(0)
    return c


def strip_task(t):
    """Processus worker : attribution des couleurs + filtre majoritaire sur une bande (avec marge)."""
    img, c, top, rows, size = t
    lab = ((img[:, :, None, :].astype(np.float32) - c[None, None]) ** 2).sum(-1).argmin(-1)
    best, out = np.full(lab.shape, -1, np.float32), np.zeros(lab.shape, np.uint8)
    for j in range(len(c)):
        f = ndi.uniform_filter((lab == j).astype(np.float32), size)
        m = f > best; best[m] = f[m]; out[m] = j
    return out[top:top + rows], os.getpid()


def label_regions(lab, k):
    ids, off = np.zeros(lab.shape, np.int32), 0
    for j in range(k):
        cc, n = ndi.label(lab == j); m = cc > 0; ids[m] = cc[m] + off; off += n
    return ids, off


def regions(lab, k, min_area):
    for _ in range(2):   # fusion des micro-zones dans la voisine la plus proche
        ids, n = label_regions(lab, k)
        small = np.bincount(ids.ravel(), minlength=n + 1)[ids] < min_area
        if not small.any() or small.all(): break
        iy, ix = ndi.distance_transform_edt(small, return_distances=False, return_indices=True)
        lab = lab[iy, ix]
    ids, n = label_regions(lab, k)
    return lab, ids.astype(np.uint16), n


async def pipeline(text, age, ex, emit, workers=4, style="doux", trend=False, remotes=(), brief=None, photo=None):
    loop, T, last = asyncio.get_running_loop(), {}, [time.perf_counter()]

    def lap(name):
        now = time.perf_counter(); T[name] = round(now - last[0], 2); last[0] = now

    emit(dict(stage="analyse", pct=5, msg="Lecture de ton texte, pendant que les processus de calcul démarrent…"))
    warm = asyncio.gather(*[loop.run_in_executor(ex, os.getpid) for _ in range(workers)])   # I/O LLM ‖ démarrage du pool
    if brief is None: brief, _ = await asyncio.gather(loop.run_in_executor(None, brain.analyse, text, age), warm)
    else: await warm
    lap("analyse")
    if brief["detresse"]: return {"safety": True, "message": SAFE}

    child = age == "enfant"; k, size, min_a = (8, 15, 1800) if child else (18, 7, 180)
    if trend or brief["emotion"] in ("stress", "colere"): k, min_a = max(6, int(k * .7)), int(min_a * 1.6)   # moins de pression

    if photo: min_a = int(min_a * 1.5)   # une photo a plus de détails : on fusionne davantage
    emit(dict(stage="scene", pct=20, msg="Préparation de ta photo…" if photo else f"Composition de la scène « {brief['scene']} » (style {style})…"))
    if photo: arr = await loop.run_in_executor(ex, scenes.load_photo, photo)
    else: arr = await loop.run_in_executor(ex, scenes.render, brief["scene"], brief["emotion"], style, zlib.crc32(text.encode()))
    lap("scene"); H, W = arr.shape[:2]

    emit(dict(stage="quantize", pct=40, msg=f"Réduction à {k} couleurs, bande par bande sur {workers} processus…"))
    cents = await loop.run_in_executor(None, kmeans, arr, k)
    b = np.linspace(0, H, workers * 2 + 1).astype(int); jobs = []
    for y0, y1 in zip(b[:-1], b[1:]):
        a0, a1 = max(0, y0 - size), min(H, y1 + size); jobs.append((arr[a0:a1], cents, y0 - a0, y1 - y0, size))
    outs = await asyncio.gather(*[loop.run_in_executor(ex, strip_task, j) for j in jobs])
    lab = np.vstack([o[0] for o in outs]); pids = {o[1] for o in outs}; lap("quantize")

    emit(dict(stage="regions", pct=60, msg="Découpage en zones à peindre…"))
    lab, ids, nreg = await loop.run_in_executor(None, regions, lab, k, min_a); lap("regions")

    emit(dict(stage="numeros", pct=75, msg=f"Placement des numéros ({nreg} zones) : pool local + {len(remotes)} nœud(s) distant(s)…"))
    items = [(i + 1, s[0].start, s[0].stop, s[1].start, s[1].stop) for i, s in enumerate(ndi.find_objects(ids)) if s]
    nodes, used = [None, *remotes], set()
    chunks = [items[i::max(4, (workers + len(remotes)) * 2)] for i in range(max(4, (workers + len(remotes)) * 2))]

    async def run(i, ch):
        if nodes[i % len(nodes)]:
            try:
                o = await dist.remote_place(nodes[i % len(nodes)], ids, ch); used.add(o["who"]); return o["res"]
            except Exception: pass   # nœud tombé : repli sur le pool local
        return await loop.run_in_executor(ex, dist.place_chunk, ids, ch)

    placed = [p for part in await asyncio.gather(*[run(i, c) for i, c in enumerate(chunks)]) for p in part]; lap("numeros")

    emit(dict(stage="export", pct=92, msg="Mise en toile…"))
    used_c = np.unique(lab); C = np.clip(cents, 0, 255).astype(np.uint8)
    order = used_c[np.argsort(C[used_c] @ np.array([.299, .587, .114]))]
    numof = np.zeros(k, int); numof[order] = np.arange(1, len(order) + 1)
    u, ix = np.unique(ids, return_index=True)
    rc = np.zeros(nreg + 1, int); rc[u] = lab.ravel()[ix]; regnum = numof[rc]; regnum[0] = 0
    e = np.zeros(ids.shape, bool); e[:, 1:] |= ids[:, 1:] != ids[:, :-1]; e[1:, :] |= ids[1:, :] != ids[:-1, :]
    line = np.zeros((H, W, 4), np.uint8); line[e] = (95, 85, 80, 255)
    idimg = np.dstack([ids >> 8, ids & 255, np.zeros_like(ids)]).astype(np.uint8)
    lap("export")
    return dict(w=W, h=H, regions=nreg, colors=len(order), regnum=regnum.tolist(),
                legend=[{"n": int(numof[c]), "hex": "#%02x%02x%02x" % tuple(C[c])} for c in order],
                numbers=[[x, y, round(r, 1), i] for i, x, y, r in placed if r >= 5],
                outline=png(line), idmap=png(idimg), preview=png(C[lab]),
                brief={x: brief.get(x) for x in ("emotion", "scene", "detail", "message", "proverbe", "mode", "valence")},
                telemetry=dict(workers=workers, pids=len(pids), remotes=sorted(used), timings=T, total=round(sum(T.values()), 2), style=style))
