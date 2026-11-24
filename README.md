# Em Jobs ✦ Road to Product

Stages, VIE, programmes graduate et premiers postes en **product** (management,
design, UX, ops, marketing produit) et **growth**, dans la tech et l'IA, à
**Paris** et **Londres**.

Le site est statique et hébergé sur GitHub Pages. Toutes les 2 heures, GitHub
Actions lit les offres publiques directement sur les sites carrière des
entreprises suivies, garde celles qui correspondent aux critères, puis publie
le site. Aucun compte, aucune clé d'API et aucune donnée personnelle.

**Pour ajouter une entreprise ou changer les critères : voir
[COMMENT_MODIFIER.md](COMMENT_MODIFIER.md).**

## Fonctionnement

| Élément | Rôle |
|---|---|
| `config/sources.toml` | entreprises suivies et leur outil de recrutement |
| `config/criteres.toml` | lieux, types de contrat, métiers, exclusions |
| `emjobs/connectors.py` | lecture des API publiques (Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Oracle, SuccessFactors, Teamtailor, Workable, Recruitee…) |
| `emjobs/classify.py` | décide si une offre est un poste produit débutant à Paris ou Londres |
| `emjobs/collect.py` | collecte toutes les entreprises ; une entreprise indisponible garde ses offres précédentes |
| `emjobs/build.py` | construit `_site/` (page, `offers.json`, `sources.json`) après contrôles de sécurité |
| `site/` | page, styles, scripts, logo et icônes |
| `.github/workflows/pages.yml` | tests, collecte et publication automatiques |

Le tri « Pertinence » additionne : métier (jusqu'à 40 points), type de
contrat (30), employeur IA (10) et fraîcheur de l'offre (20).

## Sur son ordinateur

```bash
python -m pip install -r requirements.txt pytest
python -m pytest -q
python -m emjobs.build --collect --output _preview
python -m http.server -d _preview 8000   # puis http://localhost:8000
```

## Mise en service

1. Créer le dépôt public sur GitHub et y pousser ce dossier.
2. Settings → Pages → Source : **GitHub Actions**.
3. Actions → « Collecter et publier les offres » → **Run workflow**.

Le site sera publié à `https://<compte>.github.io/<dépôt>/`. GitHub suspend
les tâches planifiées d'un dépôt public après 60 jours sans commit : il suffit
alors de les réactiver dans l'onglet Actions.
