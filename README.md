# AuraColor Studio

Atelier interactif de peinture par numéros généré à partir d'un récit libre, d'une émotion ou d'une photo personnelle, avec suivi du ressenti avant/après et adaptation des teintes.

## Lancement rapide

Installer les dépendances :


```bash
pip install -r requirements.txt
```


## Concepts utilisés et JUSTIFIÉS

| Concept | Où | Pourquoi |
| :--- | :--- | :--- |
| Flask (serveur web multi-thread) | `app.py` | Servir l'interface web, exposer les routes REST/SSE et traiter plusieurs requêtes sans bloquer le serveur |
| Server-Sent Events (SSE) | `app.py` (`/api/stream/<jid>`), `templates/index.html` | Envoyer l'avancement de chaque étape en temps réel vers le navigateur |
| Boucle `asyncio` dédiée + `run_coroutine_threadsafe` | `app.py` | Lancer le pipeline asynchrone (`engine.pipeline`) depuis les routes synchrones Flask sans bloquer le thread web |
| Threading + `queue.Queue` + `threading.Lock` | `app.py` | Protéger l'accès à l'historique (`HIST`) et écrire `history.json` en arrière-plan (`_writer`) sans ralentir les requêtes |
| Bandit epsilon-greedy & tendance émotionnelle | `app.py` (`choose_style`, `trend`) | Adapter le style de palette selon l'écart de ressenti (`after - before`) et alléger le canevas si la valence récente est négative |
| Analyse sémantique & garde-fou détresse | `brain.py` | Comprendre le texte via Ollama en local avec repli par embeddings et banque statique, tout en filtrant les situations de détresse |
| Génération procédurale & traitement d'image | `scenes.py`, `engine.py` | Composer des scènes `720x900` avec effet pinceau ou traiter une photo utilisateur, quantifier les couleurs (`K-Means`) et regrouper les petites zones |
| Multiprocessing (`ProcessPoolExecutor`) | `engine.py` (`strip_task`) | Exploiter plusieurs cœurs CPU sur les traitements lourds (attribution des couleurs, filtre majoritaire par bandes) |
| Sockets TCP + flux binaires NumPy | `dist.py` (`remote_place`, `Handler`) | Répartir le calcul des positions de numéros (`distance_transform_edt`) sur des nœuds distants avec en-tête JSON et octets bruts |
| Canvas HTML5 + `ImageData` | `templates/index.html` | Permettre le coloriage interactif, l'aide par couleur, la comparaison avec l'aperçu final et le téléchargement PNG |
| Benchmark reproductible | `bench.py` | Mesurer l'effet du nombre de processus et des nœuds distants sur les temps de quantification et de placement |
