# vizer_web — la PWA Vizer

Interface de consultation des prédictions Vizer (Hockey 🏒 NHL + Basket 🏀 NBA),
construite d'après la maquette **Vizer v2** (`Vizer v2.dc.html`).

**Vite + React + TypeScript. Aucune ressource externe** : pas de CDN, pas de
Google Fonts, pas de librairie de graphes, pas d'API serveur.

```bash
cd vizer_web
npm install
VITE_USE_MOCK=1 npm run dev     # démo immédiate sur les échantillons
npm run test                    # 44 contrôles sur la couche d'intégration
```

---

## 1. D'où viennent les données

La PWA ne parle à aucun backend. Elle lit les JSON statiques publiés par
[`vizer_daily_predictions.yml`](../.github/workflows/vizer_daily_predictions.yml)
sur la branche `models-artifacts` :

```
predictions/latest/nhl.json             ← dernier run
predictions/latest/nba.json
predictions/archive/YYYY-MM-DD/*.json   ← archives
results/latest.json                     ← scores finaux, 7 derniers jours
results/YYYY-MM-DD.json                 ← un fichier par jour
models/registry.json                    ← métriques des modèles (écran Admin)
models/history/YYYY-MM-DD.json          ← historique des métriques
```

URL de base configurable par `VITE_DATA_BASE`. Stratégie **réseau d'abord,
cache `localStorage` en repli** : le bouton ↻ et le pull-to-refresh sont des
re-fetch, jamais un recalcul.

### Les deux sports n'ont pas le même schéma

C'est le piège principal de l'intégration, encapsulé dans
[`src/types/normalize.ts`](src/types/normalize.ts) — aucun écran ne lit le JSON brut :

| | NHL | NBA |
|---|---|---|
| Prédictions | `predictions[market] = {probabilities, expected_value, confidence}` | `predictions = {win, total, talent, home_team_total, …}` |
| Value bet | `predicted_proba`, `kelly_stake` | mêmes noms (unifiés) ; les archives antérieures gardent `predicted_probability` / `kelly_stake_fraction`, toujours acceptées |
| Cotes | toujours présentes | `has_odds: false` possible |
| Erreurs | par marché : `{"error": "…"}` | pour tout le match : `predictions.error` |

Le normaliseur aplatit tout en `Game` / `MarketView` / `ValueBet`. Ajouter un
marché backend ne casse rien : il s'affiche en fin de liste avec un libellé
dérivé de sa clé — lui donner un vrai libellé dans
[`src/data/markets.ts`](src/data/markets.ts).

### Enrichissements publiés par le backend

Quatre champs ont été ajoutés au contrat pour alimenter la maquette v2 sans
rien inventer :

| Champ | Source | Écran |
|---|---|---|
| `form` | `all_teams.csv` (NHL, lignes `situation == 'all'`) · `NBA_GAMES.csv` | Forme récente · 5 derniers |
| `h2h` | idem | Confrontations directes |
| `factors` | contributions **SHAP** du booster XGBoost (`vizer_core/explain.py`) | Pourquoi cette prédiction |
| `books` | cotes par bookmaker déjà récupérées par l'Odds API | Comparatif dans « Pourquoi ? » |
| `models_trained_at` / `model_version` | métadonnées du registre | Méta de fraîcheur · écran Admin |
| `results/latest.json` | scoreboard ESPN via `scripts/publish_results.py` | Clôture automatique des paris |

Deux précisions qui comptent :

- **La forme NHL ne vient pas du dataset de features.** Celui-ci est en
  5-contre-5 : un 3-2 réel y apparaît 0-0. On lit donc `all_teams.csv`.
- **Un « N » en forme NHL signifie « décidé aux tirs au but »** : les données
  Moneypuck s'arrêtent à la prolongation.

La carte « Pourquoi cette prédiction » utilise les contributions SHAP exactes
du booster (`pred_contribs=True`), pas une heuristique. Elle disparaît si le
marché n'est pas un modèle XGBoost.

---

## 2. Commandes

| Commande | Effet |
|---|---|
| `npm run dev` | serveur de développement |
| `npm run build` | `tsc -b` puis build Vite → `dist/` |
| `npm run preview` | sert `dist/` |
| `npm run typecheck` | TypeScript seul |
| `npm run test` | auto-test de la couche d'intégration (esbuild + Node, sans dépendance) |
| `npm run icons` | régénère les icônes PWA (nécessite Pillow) |

### Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `VITE_DATA_BASE` | branche `models-artifacts` de ce dépôt | racine des prédictions ; `results/` et `models/` en sont déduits |
| `VITE_GITHUB_REPO` | `NOX-Theteenager/Vizer_pronostics` | dépôt interrogé par l'écran Admin |
| `VITE_USE_MOCK` | `0` | `1` pour lire `public/mock/` |

Sur Vercel, `VITE_DATA_BASE` vaut `/api/data/predictions` : les JSON passent
alors par le proxy Edge du dépôt (voir §7) au lieu de
`raw.githubusercontent.com`.

Les échantillons de `public/mock/` sont les données réelles du brief ; leurs
dates sont **recalées sur aujourd'hui** au chargement pour que la démo ne
vieillisse pas.

---

## 3. Structure

```
src/
├── types/
│   ├── raw.ts          formes JSON backend (les deux schémas)
│   ├── model.ts        modèle de vue unifié
│   ├── bankroll.ts     paris suivis, mouvements, ticket combiné
│   └── normalize.ts    raw → modèle de vue  ← le cœur de l'intégration
├── data/
│   ├── teams.ts        couleurs, villes et surnoms
│   └── markets.ts      libellés, ordre, marchés non pariables, familles
├── lib/
│   ├── api.ts          fetch + cache + archives
│   ├── currency.ts     FCFA / EUR / USD (montants stockés en FCFA)
│   ├── format.ts       formatage fr-FR
│   ├── contrast.ts     lisibilité des couleurs d'équipe (WCAG)
│   ├── follow.ts       options « suivre un pari » d'un match
│   ├── stats.ts        ROI, réussite, répartitions, courbe
│   └── storage.ts      localStorage défensif + export CSV
├── context/            Settings · Toast · Bankroll · Data
├── hooks/              useAlerts · usePullToRefresh
├── components/         primitives, cartes, et overlays/ (10 feuilles et plein-écrans)
├── screens/            Today · MatchDetail · ValueBets · History · Bankroll · Settings
└── styles/             tokens · base · app
```

`tokens.css` reprend **à l'identique** les objets `DARK` / `LIGHT` de la
maquette ; le thème clair est la déclinaison chaude « Claude ».

---

## 4. Ce que l'app fait

- **Splash** animé (orbite 4 ballons) puis **onboarding** en 4 étapes :
  présentation, devise, bankroll de départ, sport favori.
- **Aujourd'hui** : onglets Hockey/Basket, rail de value bets, cartes match
  « arène » aux couleurs des deux équipes, pastille de fraîcheur, hors-saison.
- **Détail match** : arène XL, favori + meilleur edge, tous les marchés du
  sport (barres, grand chiffre, totaux par équipe, talent effectif). Le total
  NHL porte « Indicatif — non pariable » (`enabled: false` dans `vizer_nhl/config.yaml`).
- **Value bets** : NHL + NBA fusionnés, filtres sport / marché / confiance /
  tri, slider d'edge minimum, panneau « Pourquoi ? ».
- **Suivre un pari** : choix du marché et de la sélection, cote et mise
  ajustables, ou ajout au **ticket combiné** (cote multipliée).
- **Historique** : verdict de rentabilité, rappels « match terminé — règle ton
  pari », courbe de bankroll survolable, filtres, clôture ✓/✗ réversible,
  performance par marché et par ligue, export CSV.
- **Bankroll** : dépôts, retraits, objectif, stop-loss, mouvements éditables,
  export CSV.
- **Recherche** globale (équipe, ligue, marché) avec **saisie vocale**.
- **Alertes** : notification système une fois par value bet, jamais pendant la
  plage silencieuse (23 h – 8 h), centre d'alertes, aperçu de notification,
  prompt de permission.
- **Réglages** : devise, sport par défaut, format des probabilités, thème,
  seuil d'alerte, cache, installation.

### Règles du domaine bankroll

- Suivre un pari ne débite rien ; **seule la clôture bouge la bankroll**.
- Gagné → `mise × (cote − 1)` ; perdu → `− mise`.
- Chaque clôture crée un **mouvement lié** (`betId`) : la somme des mouvements
  explique toujours exactement l'écart avec la bankroll de départ, donc la
  courbe ne ment jamais. Rouvrir un pari supprime son mouvement.
- Les montants sont stockés en **FCFA** ; EUR et USD sont des conversions
  d'affichage à taux fixe.

### PWA

`public/manifest.webmanifest` + `public/sw.js` écrit à la main (sans Workbox) :
shell en cache-first, prédictions en network-first avec repli cache. Icônes
générées par `scripts/gen_icons.py` à partir du même tracé que `<VizerMark>`.

Routing en **hash** (`#/match/…`) : liens profonds fonctionnels sur GitHub
Pages et hors-ligne, sans rewrite serveur.

---

## 5. Écarts assumés avec la maquette

- **Pas de châssis de téléphone.** La maquette dessine un iPhone (bezel, encoche,
  barre d'état, horloge figée) pour la présentation. L'app occupe tout l'écran,
  avec les safe-areas iOS.
- **Les cartes du rail n'ont pas de boutons d'action**, comme dans la maquette :
  on décide depuis le détail du match ou l'écran Value bets.
- **Le sélecteur d'états de démo** des réglages (Normal / Périmé / Hors ligne /
  Erreur / …) servait à présenter le prototype. Il est remplacé par un bouton
  « Données de démo » ; les vrais états se déclenchent d'eux-mêmes.
- **Le logo** est redessiné en SVG (`<VizerMark>`) plutôt qu'en PNG, pour suivre
  le thème et tenir la contrainte « aucune ressource externe ». Même géométrie :
  une lame verte, une lame argentée.

---

## 6. Accessibilité

- confiance signalée par **forme + couleur + mot**, jamais la couleur seule ;
- barres de probabilité toujours doublées de la valeur chiffrée ;
- couleurs d'équipe remontées au contraste AA quand elles servent de texte
  (`readableAccent`) — sinon DEN, WPG ou TBL tombent sous 2:1 ;
- monogrammes en noir ou blanc selon la luminance du fond ;
- zones tactiles ≥ 44 px, focus visible, `lang="fr"` ;
- `prefers-reduced-motion` désactive toutes les animations.

---

## 7. Déploiement

### Vercel (référence)

Importer ce dépôt dans Vercel avec **Root Directory : `vizer_web`**. Il n'y a
rien d'autre à régler : `vercel.json` porte le framework, la commande de build
et les variables de build. Chaque push sur `main` publie en production, chaque
branche a son aperçu.

`api/data.ts` relaie les fichiers de la branche `models-artifacts` sur la même
origine que l'app. Trois raisons :

- `raw.githubusercontent.com` impose un cache CDN de 5 minutes qu'on ne pilote
  pas ; ici les prédictions ont `s-maxage=60` et `stale-while-revalidate` ;
- le quota `raw` est par IP, donc partagé par tous les abonnés d'un même
  opérateur mobile ; le proxy le transforme en un seul appel par POP ;
- le chemin est filtré (`predictions/`, `results/`, `models/` uniquement), donc
  le proxy ne relaie pas n'importe quoi du dépôt.

Si le proxy tombe, la PWA réessaie sur `raw.githubusercontent.com` : une
fonction en panne dégrade le cache, elle ne coupe pas l'application.

### Trois pièges rencontrés en déployant

Ils ont tous la même forme — le build reste vert et la fonction disparaît :

1. **Vercel type-vérifie `api/` avant d'émettre.** `process` n'est pas dans les
   types DOM du projet : la compilation échouait, la fonction était écartée, et
   `/api/data` répondait 404 sans que le build le signale. `tsconfig.api.json`
   est maintenant dans les références, donc `npm run build` reproduit l'erreur
   localement.
2. **`export default` est traité comme `(req, res) => void`.** Un `Response`
   retourné y est ignoré et la requête part en timeout. La forme attendue est
   `export function GET(request)`.
3. **La route attrape-tout ne s'enregistrait pas.** `api/data/[...path].ts`
   renvoyait 404 sur tout, pendant qu'une fonction voisine sans segment
   dynamique répondait 200. D'où la réécriture de `vercel.json`, qui fait la
   même chose en configuration explicite :
   `/api/data/:path*` → `/api/data?path=:path*`.

Si le dépôt devenait privé, définir `VIZER_GITHUB_TOKEN` : le proxy bascule
alors sur l'API contenus de GitHub. `VIZER_REPO` et `VIZER_BRANCH` permettent
de déplacer la source sans rebuild.

### Notifications hors application

Les alertes de `useAlerts` ne partent que si l'app est ouverte. Le push, lui,
part du serveur :

| Route | Rôle |
|---|---|
| `GET /api/push/vapid` | clé publique + `ready`, pour que le client ne propose l'option que si le serveur sait vraiment envoyer |
| `POST /api/push/subscribe` | ajoute ou retire un abonnement, dédoublonné par endpoint |
| `GET /api/push/send` | cron à 7h10 UTC, dix minutes après la publication des prédictions |

Variables requises sur le projet : `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`,
`VAPID_SUBJECT`, un store (`KV_REST_API_URL` + `KV_REST_API_TOKEN`, ou les
équivalents Upstash) et `CRON_SECRET`. `GET /api/health` répond par des
booléens — présence d'une clé, jamais sa valeur — pour vérifier sans rien
exposer.

**Au plus une notification par abonné et par jour**, sur son meilleur pari
au-dessus de son seuil. Chaque couple (abonné, pari) est marqué 20 h dans le
store : un second appel du cron ne renotifie personne, ce qui protège aussi
une URL publiquement joignable. Les abonnements expirés (404/410) sont retirés
au lieu d'être réessayés indéfiniment.

### Le logo

`assets/VizerLogo.png` est la source unique. `npm run icons` en tire la marque
de l'app (`src/assets/vizer-logo.png`) et les cinq icônes PWA : **remplacer ce
fichier et relancer la commande suffit à changer le logo partout.**

Le fond gris opaque du rendu d'origine est retiré par estimation — flou large
pour modéliser le fond, puis écart à ce fond — et non par seuil sur une
couleur : la lame argentée est claire et peu saturée, le ballon sombre et
neutre, chacun ressemble au fond sur un critère isolé. La lueur est de la
lumière *sur* du gris, donc elle est décomposée pour retrouver sa vraie
couleur ; sans ça elle laissait un voile gris sur le thème clair.

### GitHub Pages (repli)

[`vizer_web_deploy.yml`](../.github/workflows/vizer_web_deploy.yml), déclenché à
la main. Nécessite *Settings > Pages > Source : GitHub Actions*. Même build,
sans proxy : la PWA lit `raw.githubusercontent.com` directement.
