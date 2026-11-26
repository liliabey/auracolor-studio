"""Nœuds de calcul distribués : protocole TCP (en-tête JSON + octets bruts, sans pickle).
Lancer un worker :  python dist.py --port 9001   (ajouter --host 0.0.0.0 pour un autre PC)"""
import argparse, asyncio, json, os, socket, socketserver, struct
import numpy as np
from scipy import ndimage as ndi


def place_chunk(idmap, items):
    """Pour chaque zone : point le plus 'profond' (transformée de distance) = emplacement du numéro."""
    out = []
    for i, y0, y1, x0, x1 in items:
        dt = ndi.distance_transform_edt(np.pad(idmap[y0:y1, x0:x1] == i, 1))
        y, x = np.unravel_index(dt.argmax(), dt.shape)
        out.append((i, int(x0 + x - 1), int(y0 + y - 1), float(dt[y, x])))
    return out


async def remote_place(addr, idmap, items):
    host, port = addr.rsplit(":", 1)
    r, w = await asyncio.wait_for(asyncio.open_connection(host, int(port)), 3)
    meta = json.dumps({"h": idmap.shape[0], "w": idmap.shape[1], "items": items}).encode()
    w.write(struct.pack(">Q", len(meta)) + meta + np.ascontiguousarray(idmap, np.uint16).tobytes())
    await w.drain()
    n = struct.unpack(">Q", await r.readexactly(8))[0]
    out = json.loads(await r.readexactly(n))
    w.close()
    return out


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        n = struct.unpack(">Q", self.rfile.read(8))[0]
        meta = json.loads(self.rfile.read(n))
        raw = self.rfile.read(meta["h"] * meta["w"] * 2)
        idmap = np.frombuffer(raw, np.uint16).reshape(meta["h"], meta["w"])
        res = place_chunk(idmap, meta["items"])
        out = json.dumps({"who": f"{socket.gethostname()}:{self.server.server_address[1]}/pid{os.getpid()}", "res": res}).encode()
        self.wfile.write(struct.pack(">Q", len(out)) + out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int, default=9001)
    a = ap.parse_args()
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    print(f"Worker AuraColor en écoute sur {a.host}:{a.port}")
    socketserver.ThreadingTCPServer((a.host, a.port), Handler).serve_forever()
