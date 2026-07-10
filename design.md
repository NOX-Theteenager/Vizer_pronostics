# Vizer — Brief de design de l'application web (PWA)

> **Document autonome destiné à Claude pour produire les maquettes de l'application.**
> Tout ce qu'il faut savoir est dans ce fichier : produit, direction artistique, écrans,
> composants, données réelles d'exemple, états et contraintes. Aucun accès au code
> backend n'est nécessaire.

---

## 0. La mission

Produire des **maquettes visuelles cliquables** (prototype HTML/CSS autonome) de
l'application, **avant** toute implémentation fonctionnelle :

- **Mobile-first** : maquetter en frames de ~390 px de large (iPhone), avec un aperçu
  de l'adaptation desktop (≥ 768 px) pour l'écran principal au minimum.
- **Tous les écrans du §4**, peuplés avec les **données d'exemple du §6** — ne pas
  inventer d'autres données, elles reflètent le vrai backend.
- **Thème sombre par défaut** (l'app se consulte le soir avant les matchs).
- Prototype **100 % self-contained** : pas de CDN, pas d'images externes, pas de
  logos officiels des ligues (droits) — les équipes sont représentées par des
  pastilles monogrammes (§5.5) aux couleurs fournies (§6.4).
- Couvrir aussi les **états vides / erreur / hors-saison** (§7) — ce ne sont pas des
  détails, certains sont l'état majoritaire de l'app.

---

## 1. Le produit en une phrase

**Vizer** est un assistant personnel de pronostics sportifs (NHL 🏒 + NBA 🏀) : des
modèles ML entraînés chaque semaine prédisent les issues des matchs du jour, croisent
ces probabilités avec les cotes réelles des bookmakers et remontent les **value bets**
— les paris où la probabilité prédite dépasse la probabilité implicite de la cote —
avec une mise recommandée (critère de Kelly fractionné).

### L'utilisateur

- **Une seule personne** (app personnelle, pas de comptes, pas d'onboarding).
- Consulte **sur mobile**, le matin (café) et le soir avant les matchs.
- Comprend les paris sportifs : cote décimale, edge, Kelly — ne pas vulgariser,
  mais **hiérarchiser** : *les value bets d'abord, le détail des marchés ensuite*.
- Interface en **français**. Cotes **décimales européennes** (`2.15`), probabilités
  en pourcentage 1 décimale (`54.7 %`), edge signé (`+8.2 %`), heures locales `fr-FR`.

### Ce que l'app N'est PAS

- Pas de prise de paris réelle (aucun compte bookmaker connecté).
- Pas de live score pendant les matchs — tout est **pré-match**.
- Pas de réseau social, pas de partage.

---

## 2. D'où viennent les données (contexte, pas à maquetter)

Deux pipelines GitHub Actions alimentent une branche GitHub (`models-artifacts`) que
la PWA consomme en statique (fetch HTTP simple, pas d'API serveur) :

- **Hebdomadaire** (lundi) : réentraînement des modèles sur Kaggle.
- **Quotidien** (7h UTC) : génération des prédictions du jour, publiées sous
  `predictions/latest/nhl.json` et `predictions/latest/nba.json` (+ archives
  quotidiennes `predictions/archive/YYYY-MM-DD/*.json` pour l'écran Historique).
  Chaque JSON contient un champ `generated_at` (ISO 8601 UTC).

Conséquences pour le design :

- Les données ont un **horodatage de génération** : l'afficher partout où c'est utile
  (« Prédictions générées il y a 2 h ») et prévoir la bannière « données périmées ».
- L'app doit être **entièrement consultable hors-ligne** avec les dernières données
  en cache (bannière « Hors ligne » discrète).
- Le rafraîchissement est un « re-fetch », pas un recalcul : bouton/pull-to-refresh
  avec état de chargement bref.

---

## 3. Direction artistique — « Sportif énergique »

L'ambiance : une **app de sport moderne** (référence : theScore, SofaScore, ESPN) —
vivante, colorée par les équipes, avec de **gros chiffres assumés** — mais au service
d'un produit de données : jamais criard, jamais « casino en ligne ». L'énergie vient
des couleurs d'équipes et de la typographie display, pas d'animations gadget.

### 3.1 Principes

1. **Les équipes colorent l'interface.** Chaque carte match tire un liseré, un dégradé
   subtil ou ses pastilles des couleurs des deux équipes (§6.4). C'est la signature
   visuelle de l'app.
2. **Les chiffres sont des héros.** Probabilités, cotes et edges en corps display
   (28-40 px sur les éléments clés), chiffres tabulaires, graisse forte.
3. **Le value bet est l'événement.** Quand il y en a un, il doit sauter aux yeux
   (accent vif, icône ⚡/💰, position en tête) ; quand il n'y en a pas, l'app reste
   belle et calme — pas de FOMO artificiel.
4. **Sombre énergique, pas sombre austère.** Fond très foncé mais chaud, surfaces en
   relief, accents saturés qui « éclairent » le noir.

### 3.2 Tokens couleur (thème sombre, défaut)

```css
:root {
  --bg: #0b0e14;              /* fond app, quasi-noir bleuté */
  --surface: #141926;         /* cartes */
  --surface-2: #1c2333;       /* éléments imbriqués */
  --border: #2a3247;
  --text: #f2f4f8;
  --text-muted: #93a0b4;

  --accent: #3d7bff;          /* actions, onglet actif */
  --value: #22d07e;           /* value bets, edges positifs — LE vert Vizer */
  --value-hot: #ffd542;       /* edge ≥ 8 % : surcouche « hot » or */
  --warning: #f5a623;         /* données périmées, confiance medium */
  --danger: #ff5d5d;          /* erreurs techniques uniquement */

  --nhl: #53c8f0;             /* accent d'onglet NHL (glace) */
  --nba: #ff7a45;             /* accent d'onglet NBA (ballon) */

  --bar-track: #232b3d;       /* piste des barres de probabilité */
}
[data-theme="light"] {
  --bg: #f4f6fa; --surface: #ffffff; --surface-2: #eaeef5;
  --border: #d7dde8; --text: #10151f; --text-muted: #5b667a;
  --bar-track: #e3e8f1;
}
```

> Le thème clair existe (réglage), mais **toutes les maquettes se font en sombre** ;
> une seule frame en clair suffit pour valider la déclinaison.

### 3.3 Typographie

- **Display (chiffres héros, titres d'écran)** : une grotesque condensée et musclée —
  `Archivo` / `Barlow Condensed` / équivalent system. Majuscules autorisées pour les
  labels de marché (`MONEYLINE`, `VALUE BET`).
- **UI/corps** : `Inter` ou stack système. Interligne 1.45.
- **Tous les chiffres** : `font-variant-numeric: tabular-nums` (alignement des colonnes).
- Échelle indicative : 12 (méta) / 15 (corps) / 18 (titre carte) / 28-40 (héros).
- Polices self-hostées ou système — **pas de Google Fonts CDN**.

### 3.4 Formes & matières

- Cartes : radius 14-16, padding 16, ombre portée douce + liseré 1 px.
- Dégradés d'équipes : très basse opacité (8-15 %) en fond de carte, du coin de
  l'équipe home vers celui de l'équipe away — de l'énergie, pas du bruit.
- Grille 4 px. Gap de liste 12. Largeur max desktop 960 px.
- Barre d'onglets **en bas** sur mobile : Aujourd'hui · Value bets · Historique · Réglages.

### 3.5 Mouvement

- Transitions 150-200 ms ease-out (opacité/transform seulement).
- Un seul moment signature : les **barres de probabilité qui se remplissent**
  à l'apparition (scale-x 300 ms) et les compteurs d'edge qui « claquent ».
- `prefers-reduced-motion` : tout désactiver.

---

## 4. Écrans à maquetter

### 4.1 Aujourd'hui `/` — l'écran principal

- **Sélecteur sport** en tête : 🏒 NHL / 🏀 NBA (segmented control, badge nombre de
  matchs, accent `--nhl`/`--nba` selon l'onglet).
- **Rail « VALUE BETS DU JOUR »** juste dessous : cartes value bet (§5.3) en scroll
  horizontal, triées par edge décroissant, tous matchs confondus. C'est LA raison
  d'ouvrir l'app. Zéro value bet → bandeau calme : « Aucun value bet aujourd'hui —
  les cotes sont efficientes. »
- **Liste des matchs** : cartes match (§5.1) triées par heure.
- **Méta bas de liste** : « Prédictions générées il y a 2 h · modèles du lun. 6 juil. ».

### 4.2 Détail match `/match/...`

- **Header immersif** : dégradé des couleurs des deux équipes, grosses pastilles,
  noms complets, heure locale, badge « domicile » côté home.
- **Duel de probabilité** : les deux probas moneyline en très gros, barre bicolore.
- **Section value bets du match** (si présents).
- **Marchés** en cartes/accordéons (§5.2). Ordre NHL : Vainqueur, Total buts, BTTS,
  1ʳᵉ période (vainqueur, total, BTTS), Intervalles de buts, Score exact (top 5 + « autres »).
  Ordre NBA : Vainqueur, Total points, Totaux par équipe, Talent effectif.

### 4.3 Value bets `/value-bets`

- NHL + NBA fusionnés, tri par edge ou par heure.
- Filtres en chips : sport, marché, confiance, slider « edge min » (défaut 4 %).
- Ligne/carte → détail du match.

### 4.4 Historique `/historique`

Suivi des performances passées du modèle et de la bankroll :

- **En-tête statistique** : 3 tuiles — ROI global (`+6.4 %`), taux de réussite des
  value bets (`54 %`), évolution bankroll (`500 € → 531 €`).
- **Courbe de bankroll** (aire/ligne, 30 derniers jours) — sobre, une seule série,
  le `--value` en couleur.
- **Liste des paris passés** : date, match, sélection, cote, résultat ✓/✗, P&L signé
  et coloré. Filtres : sport, marché, période.
- Chaque prédiction passée est vérifiable : issue prédite vs résultat réel.

### 4.5 Réglages `/reglages`

Stockage local uniquement. Groupes :
- **Bankroll** (€) — active l'affichage des mises en euros sur les value bets.
- **Alertes** : master switch notifications push + seuil d'edge déclencheur
  (slider, défaut 8 %) + plage horaire silencieuse.
- **Affichage** : sport par défaut, edge minimum affiché, probas en `%` ou en cote
  équivalente, thème auto/clair/sombre.
- **À propos / données** : horodatage des modèles, bouton « vider le cache ».

### 4.6 Notification push (à maquetter comme composant)

- **Notification système** : titre « ⚡ Value bet +9.4 % », corps « MTL Canadiens @ 2.15
  · Moneyline · ce soir 19:00 », tap → détail du match.
- **Centre d'alertes in-app** : pastille sur l'icône, feuille listant les alertes
  du jour (même carte que §5.3 en compact).
- **Prompt de permission** : écran doux expliquant la valeur (« Sois prévenu quand le
  modèle détecte un gros edge ») avec Activer / Plus tard — jamais de popup à froid.

---

## 5. Composants clés

### 5.1 Carte match (liste)

```
┌──────────────────────────────────────────────┐
│ ▍19:00 · ce soir                    ⚡ 2 VB  │  ← ▍teinté équipes · badge VB en --value
│                                              │
│  (TOR) Maple Leafs        45.3 %             │
│  (MTL) Canadiens          54.7 %  ◀ favori   │
│  ████████████░░░░░░░░░░░░░░░░░               │  ← barre bicolore home/away
│                                              │
│  E[buts] 5.9 · BTTS 88 %                     │  ← max 2 stats secondaires
└──────────────────────────────────────────────┘
```
Carte entière cliquable (zone ≥ 44 px), fond dégradé équipes très léger.

### 5.2 Carte marché (détail match)

- Label majuscules display (`MONEYLINE`) + badge confiance (§5.4).
- Issues en **barres horizontales** avec valeur chiffrée — jamais de camembert.
- 3+ issues (1ʳᵉ période, intervalles) : barres empilées, la plus probable mise en avant.
- Valeur attendue si présente, en stat héro : « E[buts] **5.87** ».
- NHL « Total buts » : afficher la prédiction avec mention « Indicatif — non pariable »
  (marché désactivé côté paris, ROI historique négatif).

### 5.3 Carte value bet — le composant signature

```
┌──────────────────────────────────────────────┐
│ ⚡ MONEYLINE · MTL Canadiens        ▣ medium │
│                                              │
│   +8.2 %              @ 2.15                 │  ← edge en display 32-40px, --value
│   ─────────────────────────────              │
│   Modèle 54.7 %   ·   Implicite 46.5 %       │
│   Mise Kelly 2.2 %  ·  11 € / 500 €          │  ← € seulement si bankroll saisie
│   TOR – MTL · ce soir 19:00                  │
└──────────────────────────────────────────────┘
```
- L'**edge est la donnée héros**. Edge ≥ 8 % : variante « hot » (liseré `--value-hot`,
  fond légèrement doré, icône ⚡ pleine).
- « Implicite » = 1 ÷ cote (petite ligne d'aide au premier affichage).

### 5.4 Badge confiance

`high` / `medium` / `low` — différenciés par **forme ET couleur** (accessibilité) :
plein ▰ / contour ▢ / pointillé ⬚, avec libellé texte (« élevée / moyenne / faible »).

### 5.5 Pastille équipe

Cercle 36-44 px, monogramme 3 lettres en display bold, fond = couleur d'équipe (§6.4),
texte blanc ou noir selon contraste. **Aucun logo officiel.**

### 5.6 Squelettes & bannières

- Skeleton loaders sur les cartes match pendant le fetch.
- Bannière ambre si données > 12 h : « Données du 09/07 · les cotes ont pu bouger ».
- Bannière grise hors-ligne : « Hors ligne — dernières prédictions en cache ».

---

## 6. Données réelles pour peupler les maquettes

### 6.1 Échantillon NHL (3 matchs — utiliser tel quel)

| Match | Heure | P(home) | P(away) | E[buts] | BTTS oui | Value bets |
|---|---|---|---|---|---|---|
| TOR Maple Leafs vs MTL Canadiens | 19:00 | 45.3 % | 54.7 % | 5.87 | 88.4 % | ⚡ Moneyline MTL @ 2.15, edge +8.2 %, Kelly 2.2 %, confiance medium |
| BOS Bruins vs NYR Rangers | 19:30 | 58.1 % | 41.9 % | 5.42 | 81.0 % | ⚡ Moneyline BOS @ 1.95, edge +6.8 %, Kelly 1.8 %, medium · ⚡ BTTS oui @ 1.70, edge +12.1 %, Kelly 3.1 %, high |
| COL Avalanche vs VGK Golden Knights | 21:00 | 51.0 % | 49.0 % | 6.10 | 85.2 % | — aucun |

Détail marchés du match TOR–MTL (pour l'écran détail) :

- Vainqueur : TOR 45.3 % / MTL 54.7 % — confiance faible
- Total buts O/U 5.5 : over 49.6 % / under 50.4 % · E[buts] 5.87 — *indicatif, non pariable*
- BTTS : oui 88.4 % / non 11.6 % — confiance élevée
- 1ʳᵉ période — vainqueur : TOR mène 32.2 % / nul 34.1 % / MTL mène 33.7 %
- 1ʳᵉ période — total O/U 1.5 : over 50.5 % / under 49.5 %
- 1ʳᵉ période — BTTS : oui 32.6 % / non 67.4 %
- Intervalles de buts : 0-2 → 8.0 % · 3-4 → 25.6 % · **5-6 → 32.8 %** · 7-8 → 21.9 % · 9+ → 11.7 %
- Score exact (top 5) : 2-2 → 12.7 % · 2-3 → 12.2 % · 3-2 → 11.8 % · 3-3 → 11.3 % · 2-4 → 6.9 %

### 6.2 Échantillon NBA (2 matchs)

| Match | Heure | P(home) | P(away) | Total prédit | Totaux équipes | Value bets |
|---|---|---|---|---|---|---|
| LAL Lakers vs BOS Celtics | 02:30 | 48.2 % | 51.8 % | 223.5 pts | LAL 109.9 (O 112.5 : 41.4 %) · BOS 113.0 (O 110.5 : 58.2 %) | ⚡ Total BOS over 110.5 @ 1.91, edge +5.9 %, Kelly 1.5 %, medium |
| GSW Warriors vs DEN Nuggets | 04:00 | 55.4 % | 44.6 % | 231.2 pts | GSW 118.1 · DEN 113.1 | — cotes indisponibles (`has_odds: false`) |

NBA affiche aussi un **ratio de talent effectif** (blessures) : LAL 1.00 · BOS 1.00
(1.00 = effectif complet ; < 1 = joueurs majeurs absents → petite jauge discrète).

### 6.3 Échantillon Historique

- Tuiles : ROI **+6.4 %** · Réussite **54 %** (27/50) · Bankroll **500 € → 531,80 €**
- Derniers paris : 08/07 ✓ BTTS oui BOS-NYR @ 1.70 (+7,10 €) · 07/07 ✗ Moneyline MTL
  @ 2.15 (−10,00 €) · 06/07 ✓ Over 110.5 BOS @ 1.91 (+6,80 €) · 05/07 ✓ Moneyline COL
  @ 1.88 (+8,40 €) · 04/07 ✗ BTTS oui TOR-FLA @ 1.75 (−9,20 €)

### 6.4 Couleurs d'équipes (pastilles & dégradés)

> Couleur principale par équipe. Texte du monogramme : blanc ou noir selon contraste.

**NHL** : ANA `#F47A38` · ARI `#8C2633` · BOS `#FFB81C` · BUF `#003087` · CAR `#CC0000` ·
CBJ `#002654` · CGY `#D2001C` · CHI `#CF0A2C` · COL `#6F263D` · DAL `#006847` ·
DET `#CE1126` · EDM `#FF4C00` · FLA `#C8102E` · LAK `#A2AAAD` · MIN `#154734` ·
MTL `#AF1E2D` · NJD `#CE1126` · NSH `#FFB81C` · NYI `#00539B` · NYR `#0038A8` ·
OTT `#C52032` · PHI `#F74902` · PIT `#FCB514` · SEA `#99D9D9` · SJS `#006D75` ·
STL `#002F87` · TBL `#002868` · TOR `#00205B` · VAN `#00843D` · VGK `#B4975A` ·
WPG `#041E42` · WSH `#C8102E`

**NBA** : ATL `#E03A3E` · BKN `#1a1a1a` · BOS `#007A33` · CHA `#1D1160` · CHI `#CE1141` ·
CLE `#860038` · DAL `#00538C` · DEN `#0E2240` · DET `#C8102E` · GSW `#1D428A` ·
HOU `#CE1141` · IND `#002D62` · LAC `#C8102E` · LAL `#552583` · MEM `#5D76A9` ·
MIA `#98002E` · MIL `#00471B` · MIN `#0C2340` · NOP `#85714D` · NYK `#006BB6` ·
OKC `#007AC1` · ORL `#0077C0` · PHI `#006BB6` · PHX `#E56020` · POR `#E03A3E` ·
SAC `#5A2D81` · SAS `#C4CED4` · TOR `#CE1141` · UTA `#002B5C` · WAS `#002B5C`

### 6.5 Format JSON source (pour information)

La PWA consommera ces structures (générées par le backend) — utile pour comprendre ce
qui existe ou pas, **ne pas afficher de champ qui n'y figure pas** :

```jsonc
// Un match NHL
{
  "home": "TOR", "away": "MTL",
  "commence_time": "2026-10-15T23:00:00Z",
  "predictions": {
    "moneyline":  { "probabilities": {"home": 0.453, "away": 0.547}, "confidence": "low" },
    "total":      { "probabilities": {"over_5.5": 0.496, "under_5.5": 0.504}, "expected_value": 5.87, "confidence": "low" },
    "btts":       { "probabilities": {"yes": 0.884, "no": 0.116}, "confidence": "high" }
    // + p1_winner, p1_total, p1_btts, exact_score, goal_intervals — mêmes formes
    // ⚠️ un marché peut valoir {"error": "..."} → carte « Indisponible »
  },
  "value_bets": [{
    "market": "moneyline", "selection": "away",
    "predicted_proba": 0.547, "bookmaker_odds": 2.15,
    "edge": 0.0819, "kelly_stake": 0.022, "confidence": "medium"
  }]
}
// Un match NBA (schéma différent : prédictions ponctuelles)
{
  "home": "LAL", "away": "BOS", "commence_time": "…", "has_odds": true,
  "predictions": {
    "win":   { "home_win_proba": 0.482, "away_win_proba": 0.518 },
    "total": { "prediction": 223.5 },
    "talent": { "home_ratio": 1.0, "away_ratio": 1.0 },
    "home_team_total": { "prediction": 109.9, "line_default": 112.5, "over_default_proba": 0.414 },
    "away_team_total": { "prediction": 113.0, "line_default": 110.5, "over_default_proba": 0.582 }
  },
  "value_bets": [ /* même format que NHL */ ]
}
// Hors-saison : { "games": [], "message": "no games" }
```

Sémantique : `edge` = proba modèle − proba implicite (1/cote) ; un value bet affiché a
toujours ≥ 4-5 % d'edge (seuil backend) ; `kelly_stake` = fraction de bankroll **déjà**
fractionnée (× 0.25) ; `confidence` ∈ high/medium/low.

---

## 7. États & cas limites (chacun mérite une frame ou une variante)

1. **Hors-saison** (état fréquent, juin → septembre !) : illustration légère aux
   couleurs du sport + « Pas de match NHL aujourd'hui · Reprise en octobre » +
   redirection douce vers l'autre sport s'il est actif.
2. **Match sans value bet** : la carte match reste attrayante, pas de vide anxiogène.
3. **`has_odds: false`** (NBA) : prédictions affichées, section value bets remplacée
   par « Cotes indisponibles pour ce match ».
4. **Marché en erreur** : carte grisée « Indisponible pour ce match », le reste s'affiche.
5. **Match commencé** (`commence_time` passé) : carte atténuée + badge « Commencé »
   (la prédiction pré-match est caduque).
6. **Données périmées** (> 12 h) : bannière ambre.
7. **Hors-ligne avec cache** : bannière grise, tout reste consultable.
8. **Hors-ligne sans cache / erreur de fetch** : écran d'erreur chaleureux + bouton
   « Réessayer ».
9. **Historique vide** (premier lancement) : état explicatif « Tes paris suivis
   apparaîtront ici ».

---

## 8. Contraintes techniques à respecter dans les maquettes

- **PWA installable** : prévoir l'icône app (monogramme « V » énergique, fond `--bg`,
  déclinaisons 192/512/maskable), splash sombre, et le rendu **standalone**
  (pas de chrome navigateur, safe-areas iOS pour la barre d'onglets basse).
- Prototype et future app **sans aucune ressource externe** (fonts, images, scripts).
- Le futur code sera **Vite + React + TypeScript** dans `vizer_web/` — les maquettes
  doivent donc rester décomposables en composants (cartes, badges, barres réutilisés
  partout, pas de one-off par écran).

## 9. Accessibilité (non négociable, même en maquette)

- Contraste AA (4.5:1 texte, 3:1 UI) — y compris sur les fonds teintés équipe.
- Confiance et « favori » signalés par **forme + texte**, jamais couleur seule.
- Barres de probabilité toujours doublées de la valeur chiffrée.
- Zones tactiles ≥ 44 px ; focus visible ; `lang="fr"`.

---

## 10. Checklist de livraison des maquettes

- [ ] Aujourd'hui (NHL actif, avec les 3 matchs du §6.1 et le rail value bets)
- [ ] Aujourd'hui — variante NBA (2 matchs du §6.2, dont un sans cotes)
- [ ] Aujourd'hui — état hors-saison
- [ ] Détail match TOR–MTL (tous les marchés NHL du §6.1)
- [ ] Détail match LAL–BOS (marchés NBA + jauge talent)
- [ ] Value bets (liste transversale avec filtres)
- [ ] Historique (tuiles + courbe + liste de paris du §6.3)
- [ ] Réglages (bankroll, alertes, affichage, thème)
- [ ] Notification push + centre d'alertes + prompt de permission
- [ ] Une frame en thème clair (Aujourd'hui suffit)
- [ ] États : offline, données périmées, erreur, skeleton
