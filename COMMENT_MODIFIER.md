# Modifier Em Jobs

Tout se fait depuis le site GitHub, sans rien installer. Après chaque
modification enregistrée (« Commit changes »), le site se reconstruit tout
seul en 5 à 10 minutes. Les tests vérifient d'abord tes fichiers : en cas
d'erreur, la publication s'arrête et **l'ancien site reste en ligne**.
L'onglet **Actions** montre l'avancement (pastille verte : publié ;
rouge : clique dessus pour lire le message d'erreur, en français).

## Ajouter une entreprise

1. Ouvre la page carrière de l'entreprise et regarde l'adresse des offres :

   | L'adresse contient…                 | `ats`             | `slug` à copier                                   |
   |-------------------------------------|-------------------|---------------------------------------------------|
   | `job-boards.greenhouse.io/NOM`      | `greenhouse`      | `NOM`                                             |
   | `jobs.lever.co/NOM`                 | `lever`           | `NOM`                                             |
   | `jobs.ashbyhq.com/NOM`              | `ashby`           | `NOM`                                             |
   | `jobs.smartrecruiters.com/NOM`      | `smartrecruiters` | `NOM`                                             |
   | `NOM.teamtailor.com`                | `teamtailor`      | `NOM`                                             |
   | `apply.workable.com/NOM`            | `workable`        | `NOM`                                             |
   | `NOM.recruitee.com`                 | `recruitee`       | `NOM`                                             |
   | `HÔTE.myworkdayjobs.com/SITE`       | `workday`         | `HÔTE.myworkdayjobs.com/TENANT/SITE` (voir plus bas) |
   | `….oraclecloud.com/…/sites/SITE/…`  | `oracle`          | `HÔTE.oraclecloud.com/SITE`                       |

   Astuce : sur la page d'une offre, le bouton « Postuler » mène souvent à
   l'une de ces adresses.

2. Dans GitHub, ouvre `config/sources.toml`, clique sur le crayon ✏️ et
   copie un bloc existant à la fin du fichier :

   ```toml
   [[source]]
   nom = "Hugging Face"
   ats = "workable"
   slug = "huggingface"
   secteur = "IA"
   domaine = "huggingface.co"
   ia = true
   ```

   - `secteur` : texte libre, il crée automatiquement un filtre sur le site ;
   - `domaine` : sert à afficher le logo ;
   - `ia = true` : ajoute le badge ✦ IA et fait légèrement remonter ses offres.

3. « Commit changes ». C'est tout.

Pour Workday, le `TENANT` est le premier mot de l'hôte : pour
`nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite`, le slug est
`nvidia.wd5.myworkdayjobs.com/nvidia/NVIDIAExternalCareerSite`.

Pour mettre une entreprise en pause sans la supprimer : ajoute `actif = false`.

## Changer les critères

Tout est dans `config/criteres.toml`, avec des commentaires :

- **Métiers** (`[[metier]]`) : ajoute une expression à la liste pour attraper
  plus d'intitulés, par exemple `"product ops"`. Le premier métier trouvé dans
  l'intitulé l'emporte ; `poids` règle le tri par pertinence.
- **Exclusions** : `seniorite` (Senior, Lead…), `metiers` (faux amis comme
  « Product Security Engineer ») et `contrats`. Pour voir aussi les
  **alternances**, retire `"alternance"`, `"alternant"`, `"alternante"`,
  `"apprenti"`, `"apprentie"`, `"apprentice"` et `"apprenticeship"` de
  `contrats`.
- **Lieux** (`[[lieu]]`) : pour ajouter Berlin, copie un bloc `[[lieu]]`.
- **Junior** : `annees_max` est l'expérience maximale demandée pour qu'un
  poste sans mot « junior » soit quand même retenu.

Les expressions ignorent majuscules et accents et se comparent en mots
entiers. Une expression en MAJUSCULES (comme `VIE`) doit apparaître en
majuscules dans l'intitulé.

## Changer l'apparence

- Textes de la page : `site/index.html` ;
- couleurs : en bas de `site/site.css`, section « Em Jobs universe »
  (`--accent`, `--spark`, `--brand-gradient`) ;
- logo : `site/em-logo.svg`. Après l'avoir changé, regénère les icônes avec
  `python scripts/render_brand.py`, ou demande-le à Claude.

## Relancer une collecte tout de suite

Onglet **Actions** → « Collecter et publier les offres » → **Run workflow**.
Sinon, la collecte tourne toute seule toutes les 2 heures, de 6 h à 22 h.

## Travailler avec Claude

Tu peux ouvrir ce dépôt dans Claude Code (ou un Codespace GitHub) et
demander par exemple : « ajoute Hugging Face aux sources » ou « affiche aussi
les alternances ». Lance les tests avec `python -m pytest -q`.
