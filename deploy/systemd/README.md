# Préparation des datasets — passage de cron à systemd

## Pourquoi

Les deux fournisseurs de données bloquent les IP de datacenter : `stats.nba.com`
bloque GitHub Actions *et* Kaggle, `moneypuck.com` bloque `all_teams.csv` depuis
Kaggle. Cette machine a une IP résidentielle — elle est le seul point d'accès
possible, et tout le pipeline en dépend.

Le mécanisme était un cron du dimanche soir. Son propre commentaire énonçait le
risque : « un cron ne rattrape pas une exécution manquée : PC éteint le dimanche
soir = rien ne se passe, et rien ne prévient. »

C'est arrivé. Relevé le 26 octobre 2026 :

| dataset | dernière donnée | retard |
|---|---|---|
| NHL | 13 octobre | 13 jours |
| NBA | 27 mai | 196 jours — aucun match de la saison en cours |

Pendant ce temps la NHL est passée de 6,10 à 6,43 buts par match et le modèle de
5,73 à 5,75 : il ne pouvait pas suivre. Les paris proposés sur la période gelée
ont rendu **−27,2 %**, contre −6,8 % sur la période fraîche. Et tout en aval
restait vert — le job quotidien publiait, la barrière de qualité passait (elle
évalue sur les mêmes données gelées), et l'AUC de test ne bougeait pas d'un
réentraînement à l'autre, à la quatrième décimale près.

## Ce que ça change

| | cron | systemd |
|---|---|---|
| exécution manquée | perdue, rendez-vous dans 7 jours | rattrapée au démarrage (`Persistent=true`) |
| cadence | hebdomadaire | quotidienne — un oubli coûte un jour |
| machine éteinte sans session | — | tourne quand même (`enable-linger`) |

Les scripts ne publient que s'il existe des matchs plus récents : hors saison,
une exécution quotidienne ne fait rien.

## Installation

```sh
REPO=/home/noxtheteenager/Documents/Projets/Vizer_pronostics

# 1. Les unités
mkdir -p ~/.config/systemd/user
cp "$REPO"/deploy/systemd/vizer-dataset-*.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now vizer-dataset-nhl.timer vizer-dataset-nba.timer

# 2. Tourner même sans session ouverte. Sans ça, un timer utilisateur ne
#    s'exécute que pendant qu'on est connecté — ce qui annulerait l'essentiel
#    du bénéfice.
loginctl enable-linger "$USER"

# 3. Retirer les deux lignes de cron, sinon tout tourne deux fois (20 min
#    d'upload NHL et jusqu'à une heure de fetch NBA, pour rien).
crontab -e      # commenter les deux lignes `push_dataset_to_kaggle.py`
```

## Vérification

```sh
systemctl --user list-timers 'vizer-*'        # prochaine et dernière exécution
systemctl --user status vizer-dataset-nhl     # résultat du dernier run
tail -40 vizer_nhl/logs/push_dataset.log      # même journal que la version cron

# Rattrapage immédiat, sans attendre l'heure :
systemctl --user start vizer-dataset-nhl vizer-dataset-nba
```

## Le filet qui ne dépend pas de cette machine

Un timer local ne peut pas signaler une machine éteinte. Deux contrôles vivent
donc dans le cloud :

- `scripts/check_data_freshness.py`, dans le job quotidien, compare la dernière
  date du dataset au dernier match **effectivement joué** d'après ESPN — pas au
  calendrier, pour qu'un écart de treize jours en pleine saison soit une panne
  et le même écart en juillet rien du tout. Il publie son verdict dans
  `performance/freshness.json` et rend le run rouge sans bloquer la publication.
- le cron Vercel (`api/push/send.ts`) lit ce verdict et, tant que le retard
  dure, pousse une notification **au lieu** du value bet du jour. Ce n'est pas
  un choix de priorité : c'est le seul message honnête, puisque les paris du
  jour sont calculés sur un état du championnat dépassé.
