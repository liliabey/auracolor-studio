"""Compréhension du texte : LLM local (Ollama) -> embeddings -> mode dégradé."""
import json, os, re, urllib.request

URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
EMO = ["stress", "tristesse", "joie", "nostalgie", "colere", "calme", "douleur"]
SCENES = ["cheval", "phare", "foret", "fleurs", "fruits", "famille", "lever"]
# Sécurité : liste volontairement conservatrice, doublée du champ "detresse" du LLM.
DISTRESS = re.compile(r"suicid|me tuer|en finir avec (la vie|tout)|(veux|voudrais|envie de|envie d.en finir,? de) mourir|plus envie de vivre|"
                      r"kill myself|want to die|end my life|انتحار|أقتل نفسي|أريد أن أموت|نحب نموت", re.I)

PROMPT = f"""Tu es un art-thérapeute bienveillant. Lis le texte (toute langue, dialecte tunisien et arabizi compris)
et réponds UNIQUEMENT par un JSON : {{"emotion":{EMO},"valence":-1..1,"intensite":0..1,
"type":"souvenir_heureux|souvenir_douloureux|stress|journee","scene":{SCENES},"detail":"ce qu'on peint, 1 phrase",
"message":"2 phrases douces dans la langue du texte","proverbe":"un proverbe réel adapté, avec son origine","detresse":true|false}}
Règles : souvenir heureux -> scène du souvenir (cheval si enfance ou animaux, sinon fruits/fleurs/famille) ;
souvenir douloureux -> lever (guérison) ; stress -> phare, foret ou famille (apaisant) ; journée banale -> fleurs ou foret.
detresse=true si la personne évoque se faire du mal ou mourir."""

BANK = {
 "stress": ("Respire : tu n'as rien à réussir ici, seulement des couleurs à poser, une à la fois.", "Qui va doucement va sûrement. (proverbe français)"),
 "tristesse": ("Ce poids est réel. Laisse les couleurs douces tenir compagnie à ce que tu ressens.", "Après la pluie, le beau temps. (proverbe français)"),
 "joie": ("Quelle belle énergie ! Peins-la en grand.", "Petit à petit, l'oiseau fait son nid. (proverbe français)"),
 "nostalgie": ("Les souvenirs tendres méritent leurs plus belles teintes.", "Chaque chose en son temps. (proverbe français)"),
 "colere": ("Ta colère a le droit d'exister. Transforme-la en gestes lents, un aplat après l'autre.", "Patience et longueur de temps font plus que force ni que rage. (La Fontaine)"),
 "calme": ("Savoure ce moment paisible, pinceau en main.", "Rome ne s'est pas faite en un jour. (proverbe français)"),
 "douleur": ("Ce souvenir est lourd. Ici, on avance doucement, vers la lumière qui revient.", "الصبر مفتاح الفرج : la patience est la clé du soulagement. (proverbe arabe)"),
}
VAL = {"stress": -.5, "tristesse": -.6, "joie": .8, "nostalgie": .3, "colere": -.6, "calme": .5, "douleur": -.8}
SC_BY_EMO = {"stress": "phare", "calme": "foret", "tristesse": "lever", "douleur": "lever",
             "colere": "foret", "joie": "fleurs", "nostalgie": "cheval"}
PE = {"stress": "je suis stressée, angoissée, tout me submerge", "tristesse": "je me sens triste et seule",
      "joie": "je suis heureuse, belle journée", "nostalgie": "je me souviens tendrement de mon enfance",
      "colere": "je suis en colère, frustrée", "calme": "je me sens paisible et sereine",
      "douleur": "un souvenir douloureux, un deuil, une blessure"}
PS = {"cheval": "un cheval, un enfant à cheval, la campagne", "phare": "la mer, la plage, un phare, les vagues",
      "foret": "la forêt, les arbres, la nature", "fleurs": "des fleurs, un jardin, le printemps",
      "fruits": "des fruits, un gâteau, la cuisine, manger", "famille": "ma mère, ma famille, la maison",
      "lever": "un nouveau départ, guérir, le soleil se lève"}
_emb = None


def _ask(text, age):
    body = json.dumps({"model": MODEL, "stream": False, "format": "json", "options": {"temperature": .4},
                       "messages": [{"role": "system", "content": PROMPT + (" Profil : enfant, ton simple." if age == "enfant" else "")},
                                    {"role": "user", "content": text}]}).encode()
    req = urllib.request.Request(URL + "/api/chat", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(json.loads(r.read())["message"]["content"])


def _embed(text, age):
    global _emb
    from sentence_transformers import SentenceTransformer
    if _emb is None:
        m = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        _emb = (m, m.encode(list(PE.values()), normalize_embeddings=True), m.encode(list(PS.values()), normalize_embeddings=True))
    m, E, S = _emb
    v = m.encode([text], normalize_embeddings=True)[0]
    e, s = E @ v, S @ v
    emo, scene = list(PE)[int(e.argmax())], list(PS)[int(s.argmax())]
    if emo in ("tristesse", "douleur"): scene = "lever"
    elif emo in ("stress", "colere") and scene not in ("phare", "foret", "famille"): scene = "phare"
    return dict(emotion=emo, valence=VAL[emo], intensite=float(e.max()), scene=scene)


def analyse(text, age="adulte"):
    if DISTRESS.search(text):
        return dict(detresse=True, emotion="douleur", scene="lever", mode="sécurité")
    for mode, fn in (("LLM local (Ollama)", _ask), ("Embeddings multilingues", _embed)):
        try:
            b = fn(text, age)
            if b.get("emotion") not in EMO: b["emotion"] = "calme"
            if b.get("scene") not in SCENES: b["scene"] = SC_BY_EMO[b["emotion"]]
            b["message"] = b.get("message") or BANK[b["emotion"]][0]
            b["proverbe"] = b.get("proverbe") or BANK[b["emotion"]][1]
            b.update(detresse=bool(b.get("detresse")), mode=mode, detail=b.get("detail", ""))
            return b
        except Exception:
            continue
    return dict(emotion="calme", scene="fleurs", valence=0, intensite=.3, detresse=False, mode="dégradé (installe Ollama)",
                detail="", message=BANK["calme"][0], proverbe=BANK["calme"][1])
