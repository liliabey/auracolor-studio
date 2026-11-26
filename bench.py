"""Benchmark : python bench.py [--remote 127.0.0.1:9001]   -> tableau pour les slides."""
import asyncio, sys, time
from concurrent.futures import ProcessPoolExecutor
import engine

BRIEF = dict(emotion="nostalgie", scene="cheval", detail="", message="", proverbe="", detresse=False, mode="bench", valence=.5)


async def run(n, remotes):
    with ProcessPoolExecutor(n) as ex:
        go = lambda: engine.pipeline("bench", "adulte", ex, lambda e: None, workers=n, remotes=remotes, brief=dict(BRIEF))
        await go()   # échauffement (démarrage des processus)
        return (await go())["telemetry"]


if __name__ == "__main__":
    remotes = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--remote"]
    base = None
    print("processus | nœuds | total (s) | quantize | numeros | accélération")
    for n in (1, 2, 4):
        t = asyncio.run(run(n, remotes)); base = base or t["total"]
        print(f"{n:9} | {len(t['remotes']):5} | {t['total']:9} | {t['timings']['quantize']:8} | {t['timings']['numeros']:7} | x{base / t['total']:.2f}")
