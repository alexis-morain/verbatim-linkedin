# Journal

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
