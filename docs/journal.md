# Journal

## 2026-08-28. Gate levé par Alexis, étape 4 livrée : le socle applicatif

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
