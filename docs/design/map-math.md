# Map math: a formulation of places, terrain and content

This note extends `map-terrain.md` into mathematics. That note names the parts: Places,
Ground, Layout, Identity, Borders, Paint, Reading. This note gives each part a space of
values, a distribution over that space, the corpus statistics that fix the distribution,
the constraints every sample must obey, and a sampler that runs inside the time budget.
It then does the same for content, and states how the two problems share one latent
structure.

The document contains no measurement and no experiment. Where a claim rests on a game
fact, the fact is named. Where a claim rests on a corpus number the study already
recorded, the number is quoted. Where a claim is a guess, the sentence says so.

Notation. $N = 72$ is the map side. $\mathcal{L} = \{0\}$ for a surface map and
$\{0, 1\}$ with an underground. $V = \{0, \dots, N-1\}^2 \times \mathcal{L}$ is the tile
set, $|V| = 5184$ per level. A tile is $u = (x, y, \ell)$. Two tiles are 4-adjacent when
they share a side, 8-adjacent when they share a side or a corner. $d_\infty$ is the
Chebyshev distance. A seeded stream is $\mathrm{rng}_k = \mathrm{Random}(h(s, k))$ for the
map seed $s$ and a fixed part label $k$.

## 1. Objects and spaces

### 1.1 Ground

The ground mask is a map $G : V \to \{\mathrm{land}, \mathrm{water}, \mathrm{rock}\}$.
Water and rock are the two barrier classes of Heroes III: a hero never stands on either
without a boat, and rock exists only underground. $\mathrm{Land} = G^{-1}(\mathrm{land})$.
The land terrains are $\mathcal{T} = \{\mathrm{dirt}, \mathrm{sand}, \mathrm{grass},
\mathrm{snow}, \mathrm{swamp}, \mathrm{rough}, \mathrm{subterranean}, \mathrm{lava}\}$.
Subterranean is the one base terrain of the lower level. Every faction has a native
terrain: grass for Castle, Rampart and Conflux, snow for Tower, swamp for Fortress, lava
for Inferno, subterranean for Dungeon, dirt for Necropolis, rough for Stronghold. Sand
has no native faction. Snow, swamp, rough and sand slow an army whose
creatures are not native to them. Dirt, grass, lava and subterranean slow nobody. Those
two rules are what make a palette a gameplay choice and not only a look.

### 1.2 Place graph

The place graph is $P = (\Pi, A, \rho, \sigma, \omega)$.

- $\Pi$ is a finite set of places, $n = |\Pi|$.
- $\rho : \Pi \to \mathcal{R}$ assigns a role. The role set is
  $\mathcal{R} = \{\mathrm{home}, \mathrm{middle}, \mathrm{treasure}, \mathrm{pass},
  \mathrm{pocket}, \mathrm{sea}\}$. A home is a player's start. A middle is contested
  ground with no owner. A treasure ground holds loot behind guards and no town. A pass is a
  thin place whose job is to connect two others. A pocket is a small place with one way
  in. Sea is a water place, present only when Ground makes one.
- $\sigma : \Pi \to \mathbb{R}_+$ is a target area in tiles, with
  $\sum_p \sigma_p = |\mathrm{Land}|$ per level.
- $\omega : \Pi \to \{1, \dots, k\} \cup \{\emptyset\}$ is the owner player, defined on
  homes only. $k$ is the player count.
- $A \subseteq \binom{\Pi}{2}$ is the adjacency set, with a kind
  $\kappa : A \to \{\mathrm{open}, \mathrm{gated}, \mathrm{closed}, \mathrm{gate\_pair}\}$.
  Open means a soft transition or a wide passage. Gated means a barrier with one or two
  passages, each a candidate for a guard or a Border Gate. Closed means a barrier with no
  passage. Gate pair means the two places lie on different levels and are joined by a
  Subterranean Gate pair, a two-object link H3 uses to move a hero between levels.

$(\Pi, A)$ is a graph. Its connected subgraph on $\kappa \neq \mathrm{closed}$ must be
connected. That is the graph form of reachability, stated in section 4.

Symmetry. Let $\Gamma$ be the symmetric group on the $k$ players. A plan is
$\Gamma$-fair when for every permutation $\gamma$ there is a graph automorphism
$\phi_\gamma$ of $(\Pi, A, \rho, \kappa)$ with $\omega \circ \phi_\gamma = \gamma \circ
\omega$ and $|\sigma \circ \phi_\gamma - \sigma| \le \epsilon_\sigma$. Exact fairness is a
template in disguise. Section 4 relaxes it to a tolerance on functionals.

### 1.3 Place map

The place map is $\zeta : \mathrm{Land} \to \Pi$. Its fibres $R_p = \zeta^{-1}(p)$ are the
regions. The invariant "every land tile belongs to exactly one place" is the statement
that $\zeta$ is a total function. $|R_p|$ is the realised area, and $\sigma_p$ is its
target.

A region has a boundary $\partial R_p = \{u \in R_p : \exists v \text{ 4-adjacent to } u,
v \notin R_p\}$. The realised adjacency is $\hat A(\zeta) = \{\{p, q\} : \exists u \in
R_p, v \in R_q, u \sim_4 v\}$. Layout must deliver $A \subseteq \hat A(\zeta)$. Extra
realised adjacencies are allowed and become closed borders.

### 1.4 Palettes

A palette is a distribution $\Theta_p \in \Delta(\mathcal{T})$ with a dominant terrain
$d_p = \arg\max_t \Theta_p(t)$ and an accent set $\{t : 0 < \Theta_p(t) < \Theta_p(d_p)\}$.
The invariant "dominant terrain covers most of the place" is $\Theta_p(d_p) \ge \theta_{\min}$
for a threshold learned from the corpus.

Palettes live on palette regions, not on places. The palette partition is a map
$\pi : \Pi \to \{1, \dots, K\}$ whose fibres $\Lambda_k = \pi^{-1}(k)$ are unions of whole
places, each connected on $\hat A(\zeta)$. $K$ is the palette region count. Places stay
about 26 per level, and $K$ follows the corpus count of terrain blobs, median 7 (q1 4, q3
10). Identity is the map $k \mapsto \Theta_k$, and a place reads its palette through its
region: $\Theta_p := \Theta_{\pi(p)}$ and $d_p := d_{\pi(p)}$. Two adjacent regions never
share a dominant, so a same-terrain border between places is a border inside one region.

The reason is the corpus. The macro terrain-blob adjacency table has no mass on $(t, t)$ by
construction, so pricing place borders with it makes a same-terrain border cost 11.8 nats
against 1.2 for dirt beside grass. A Potts reward for same-terrain borders does not fix
it: the corpus same-terrain share of 0.71 sits on the model's critical point, where a
coupling of 2 gives 0.42 to 0.55 and a coupling of 3 gives 0.90 to 1.00 with 2 or 3 blobs.
Conditioning on border kind buys nothing, since the share is 0.83 on open, 0.76 on gated
and 0.67 on closed borders. The macro pair table applies to the partition it was mined
on, the terrain blobs, and $\pi$ supplies that partition.

### 1.5 Borders

For each realised adjacency $\{p, q\}$ the border set is
$B_{pq} = \{(u, v) : u \in \partial R_p, v \in \partial R_q, u \sim_4 v\}$, a set of
tile pairs. Its length is $|B_{pq}|$. A border carries a kind
$b_{pq} \in \{\mathrm{barrier}, \mathrm{transition}\}$ and a passage set $\Psi_{pq}$.

- A barrier is a tile set $W_{pq} \subset R_p \cup R_q$ with $B_{pq}$ inside its
  4-closure, such that no 4-path from $R_p \setminus W_{pq}$ to $R_q \setminus W_{pq}$
  avoids $W_{pq} \cup \bigcup \Psi_{pq}$. Water and rock barriers come from Ground.
  Mountain and forest barriers are land tiles that vegetation will fill with blocking
  objects. Borders decides $W_{pq}$. It never names the object.
- A passage $\psi \in \Psi_{pq}$ is a 4-connected tile set of width at least $w_{\min} = 3$
  that meets both $R_p \setminus W_{pq}$ and $R_q \setminus W_{pq}$ and lies inside
  $W_{pq}$'s hull. Three is the width of the existing entrance band and of a town's front
  approach, and it is the smallest width through which a guard's zone of control does not
  seal the gap by itself.
- A transition is a band $Z_{pq} \subset R_p \cup R_q$ of depth $w_{pq}$ about $B_{pq}$
  with no barrier, in which Paint grades $d_p$ into $d_q$.

Kind follows adjacency: $\kappa = \mathrm{open}$ gives a transition or a barrier with a
wide passage, $\kappa = \mathrm{gated}$ gives a barrier with $|\Psi_{pq}| \in \{1, 2\}$,
$\kappa = \mathrm{closed}$ gives a barrier with $\Psi_{pq} = \emptyset$.

A barrier is placed by border kind, not by terrain change. Most corpus barriers separate
two places of the same dominant: 3534 closed borders join same-terrain places against
1750 that join different terrains. A barrier therefore often lies inside one palette
region. Today's generator does not yet place barriers this way.

The passable set is $\mathrm{Pass} = \mathrm{Land} \setminus \bigcup_{pq} W_{pq}$ before
content and $\mathrm{Pass} \setminus \mathrm{Blocked}(X)$ after, where
$\mathrm{Blocked}(X)$ is the union of blocking footprint cells.

### 1.6 Terrain field

The terrain field is $\tau : V \to \mathcal{T} \cup \{\mathrm{water}, \mathrm{rock}\}$ with
$\tau = G$ off land. Paint produces $\tau|_{\mathrm{Land}}$ from $(\zeta, \Theta, B)$. The
tile-level invariants are:

- base coat: $\frac{1}{|R_p|}|\{u \in R_p : \tau(u) = d_p\}| \ge \theta_{\min}$;
- accent locality: every 4-connected component of $\{u : \tau(u) = t \ne d_{\zeta(u)}\}$
  lies inside one $R_p$ and does not meet $\partial R_p$ except inside a transition band;
- no raw cut: for every $(u, v) \in B_{pq}$ with $d_p \ne d_q$, either $u$ or $v$ lies in
  $W_{pq}$, or both lie in $Z_{pq}$.

The raw-cut length of a map is $\mathrm{cut}(\tau) = |\{(u, v) : u \sim_4 v, \tau(u) \ne
\tau(v), \text{both land}, \text{neither in a barrier or a transition}\}|$. A hand-made
map has a small value. Today's generator has every border inside this set.

### 1.7 Content

Content is a marked point process $X = \{(u_i, m_i)\}_{i=1}^{M}$ on $V$ with marks
$m_i \in \mathcal{M}$. A mark carries a purpose $\pi(m) \in \mathcal{P}$, an identity
$\iota(m)$ drawn from the catalog, and a payload. The purposes that matter here are
$\{\mathrm{TOWN}, \mathrm{MINE}, \mathrm{DWELLING}, \mathrm{BANK}, \mathrm{GUARD},
\mathrm{RESOURCE\_PILE}, \mathrm{REWARD\_PICKUP}, \mathrm{VISIT}\}$ with $\mathrm{VISIT}$
the union of the visitable purposes. Identity, footprint mask and category come from the
catalog alone. The corpus informs where and how many. It never informs what an object is.

Each placed object has a footprint $F(m, u) \subset V$ split into blocking cells and
visitable cells, and an approach tile $a(m, u)$, the tile a hero stands on to use it. A
guard $g$ has a zone of control $\mathrm{ZOC}(g) = \{v : d_\infty(v, c) \le 1 \text{ for
some interactive cell } c \text{ of } g\}$. This is the H3 rule: a hero who steps onto a
tile adjacent to a monster fights it. A guard also has a strength
$s(g) \in \{1, \dots, 7\}$, the random monster level, or a fixed stack.

Two views of $X$ are used. The point-process view carries positions and pairwise terms.
The assignment view carries, per place, a count vector $n_p \in \mathbb{N}^{\mathcal{P}}$
and a total $n_p^{\mathrm{tot}}$. The assignment view is what the corpus rates fix. The
point-process view is what the sampler draws.

### 1.8 Roads and rivers

A road is a 4-connected tile set $\mathrm{Road} \subset \mathrm{Pass}$. A road network is a
forest of paths in the passable graph that joins a town's approach tile to the passages of
its place and, through them, to the next town. Rivers are tile sets with the same
geometry on either class of tile, and a river crossing is a passage. Roads are in scope
with regions because both are read by the judge from the same picture. The study's cue
profile put Roads at 44 of 53 and Region layout at 40, the two largest.

## 2. Generative model

### 2.1 Factorisation

The joint distribution of a map is

$$
p(P, G, \zeta, \Theta, B, \tau, X, \mathrm{Road})
= p(P) \, p(G \mid P) \, p(\zeta \mid P, G) \, p(\pi \mid P, \zeta) \,
p(\Theta \mid \pi, P) \, p(B \mid P, \zeta, \Theta) \, p(\tau \mid \zeta, \Theta, B) \,
p(X \mid P, \zeta, B, \tau) \, p(\mathrm{Road} \mid X, B, \tau).
$$

Each factor is one part. Each part is a role with swappable variants. Vegetation is not a
factor here: it is a given, a map from $(W, \tau, X)$ to blocking decor that fills every
barrier tile and dresses the rest.

Reading left to right:

1. $p(P)$, Places. Draw $n$, the roles, the sizes and the adjacency graph from corpus
   statistics indexed by player count and level set.
2. $p(G \mid P)$, Ground. Draw land, water and rock. Conditioning on $P$ lets a planned
   closed or water adjacency pull water to where the border will fall. Today's water mask
   is the unconditioned variant.
3. $p(\zeta \mid P, G)$, Layout. Place anchors, grow regions to size, deliver
   $A \subseteq \hat A(\zeta)$.
4. $p(\pi \mid P, \zeta) \, p(\Theta \mid \pi, P)$, Identity, with $d_p := d_{\pi(p)}$.
   - $p(\pi \mid P, \zeta)$, the palette partition. Draw $K$ from
     $p(K \mid n, |\mathrm{Land}|)$. Draw $K$ capacities from the macro terrain-blob
     areas, renormalised to the sum of place sizes. Seed the $K$ regions farthest-first
     on $\hat A$ by hop distance, one seed per connected component of $\hat A$ first.
     Grow by capacity-constrained BFS over places, so each region is a union of whole
     places connected on $\hat A$.
   - $p(\Theta \mid \pi, P)$, the region palettes. Draw one dominant per region with
     energy $E(d) = \sum_k \sum_{p \in \Lambda_k} c_{\rho_p}(d_k) + \sum_{k \sim l}
     -\log p_{\mathrm{macro}}(d_k, d_l)$, where $c_\rho$ is the role cost and
     $d_k \neq d_l$ is hard for adjacent regions. A region that holds a home draws from
     the town terrains only.
5. $p(B \mid P, \zeta, \Theta)$, Borders. For each realised adjacency draw a kind, a band
   depth, barrier tiles and passages.
6. $p(\tau \mid \zeta, \Theta, B)$, Paint. Base coat, accent patches, transition grading,
   then a texture variant inside each place. Markov is one texture variant.
7. $p(X \mid P, \zeta, B, \tau)$, Content. A marked point process whose intensity reads
   the role, the distance to passages and homes, and the openness.
8. $p(\mathrm{Road} \mid X, B, \tau)$, Roads. Shortest paths in the passable graph from
   towns through passages, with a learned stopping rule.

The order is a choice. Two other orders were considered and rejected in `map-terrain.md`:
terrain first with places read off paint, and content first with terrain fitted around it.
Section 6 gives the mathematical reason the first fails.

### 2.2 Randomness and determinism

Every draw in part $k$ comes from $\mathrm{rng}_k$. Within a part that iterates over
places, the stream for place $p$ is $\mathrm{Random}(h(s, k, p))$ so that adding a
variant to one part does not shift draws in another. A map is then a pure function
$\mathrm{Map}(s, \mathrm{config})$. The same seed gives the same map. No part reads the
clock, the file system order or an unseeded library call.

### 2.3 Roles and variants

| Part | Role | Variants named today |
|---|---|---|
| Places | plan source | corpus statistics per player count |
| Ground | ground sampler | thresholded value noise, cavern blobs with tunnels |
| Layout | region shape | capacity-constrained growth, watershed, frame warp |
| Identity | theme rule | role and faction table |
| Borders | border strategy per kind | water, rock, mountain, forest, river, transition |
| Paint | texture | Markov Gibbs inside a place, plain coat |
| Content | content sampler | sequential by purpose, birth-death Gibbs |
| Roads | road layer | none, gates, walks, turned, spine |

Each variant implements one method on one frozen input value and returns one frozen
output value. The assembly in `cli/steps.py` picks a variant by name, the way
`SAMPLERS` picks a vegetation sampler today.

## 3. What is learned from the corpus

### 3.1 The corpus is unlabelled

A corpus map is $(\tau^c, X^c, \mathrm{Road}^c, \mathrm{Players}^c)$. It has no place
graph, no place map, no palette and no border kind. Every statistic about places must be
defined through an inference $\hat\zeta(\tau^c, X^c)$ that produces a place map on a real
map. The inference is part of the design. A statistic is only as good as the inference
that defines it.

What the `.h3m` file does carry: the terrain per tile, every object with its type,
subtype and position, every town's owner, the player table with allowed factions and
main town, roads and rivers per tile, and for monsters either a fixed stack or a random
monster level 1 to 7. Guard strength is therefore observable at the level of a tier.
Fixed stacks give a count. Random monsters give a level.

### 3.2 Place inference on a real map

The inference uses passability, not terrain. On a hand-made map a region ends where a
hero cannot walk, not where the paint changes.

Define the walkable graph $\mathcal{W}^c$ on $\mathrm{Pass}^c = \mathrm{Land}^c \setminus
\mathrm{Blocked}(X^c)$ with 4-adjacency. Define the barrier field
$\beta(u) = 1$ on blocked land tiles, water and rock, $0$ otherwise. Define a soft
barrier strength $\bar\beta(u)$ as the fraction of blocked tiles in the $5 \times 5$
window about $u$. Chokepoints are the walkable tiles with openness at most 10 of 25,
which is the existing `chokepoints` definition.

Seeds. Every town is a seed. Every connected component of $\mathcal{W}^c$ with no town
and at least $\sigma_{\min} = 40$ tiles contributes one seed at its geodesic centre.
Guards define cuts: the inference removes every guard's zone of control from
$\mathcal{W}^c$ before growing seeds, because a guard on a hand-made map is placed where
the designer wanted a region to end.

Growth. $\hat\zeta$ is the geodesic Voronoi partition of $\mathcal{W}^c$ minus guard
zones, under the metric $d_\beta(u, v) = \min_{\text{paths}} \sum (1 + \lambda \bar\beta)$.
Tiles cut off by guards are assigned to the seed whose region they touch across the
guard. Tiles with no seed in their component are a pocket. Barrier tiles are assigned
to the nearest region, so $\hat\zeta$ is total on land.

Merging. Two regions whose shared border has no guard, no barrier and no terrain change
merge. This is the step that keeps an accent patch inside its place. Two regions merge
when the border between them has a cut fraction $\frac{|B_{pq} \cap \text{barrier}|}{|B_{pq}|}$
below a threshold and no guard.

Roles. A region holding a player's main town is a home with $\omega$ that player. A
region with a town and no owner is a middle. A region with no town, at least one guard
on every passage into it and total reward value above the map median is a treasure
ground. A region with one passage and area under 60 tiles is a pocket. A region whose
width, measured as $2 |R_p| / |\partial R_p|$, is under 6 and that joins two others is a
pass. The rest are middles. The thresholds 40, 60 and 6 are the existing
`MIN_ZONE_AREA`, `LOOT_ZONE_MAX_TILES` and twice the entrance width. They are
starting values, not measurements.

Adjacency and kind. $\hat A$ is the realised adjacency of $\hat\zeta$. The kind of
$\{p, q\}$ is read off $B_{pq}$: closed when no walkable tile pair crosses it, gated when
the crossings form at most two 4-connected clusters each of width under $2 w_{\min}$,
open otherwise.

Palette. $\hat\Theta_p$ is the empirical terrain histogram over $R_p$.

Border kind. Barrier when the fraction of $B_{pq}$ with a blocked tile on either side is
above one half, transition when the terrains differ and the fraction is below it, and a
raw cut otherwise. The corpus raw-cut rate per border is itself a statistic.

### 3.3 What inference cannot see

- Intent. The designer's order of play, which place is a decoy and which a reward, and
  the story a map tells. The inference sees a graph and sizes. A role is a label the
  inference assigns, not one the designer wrote.
- Symmetry. Hand-made maps are rarely mirror images. The inference measures fairness as
  a tolerance on functionals, section 4.4, and cannot recover a hidden symmetry group.
  This is a guess about the corpus, not a measurement.
- Fixed guard strength as a value. A fixed stack of 30 Pikemen has a known strength in
  H3 terms. The map that places it does not say what reward it was meant to protect.
  Guard strength against reward is therefore a correlation across maps, not a rule read
  from one.
- Payload of random objects. A random town, dwelling or artifact has no faction, level
  or tier until the game starts. Value functionals on the corpus use the expected value
  over the random class.
- Border depth as intended. A forest belt that is three tiles wide may be a barrier or a
  decoration the designer thickened. The inference reads width, not purpose.

### 3.4 The statistics

Each is a functional of $(\tau^c, X^c, \hat\zeta, \hat A)$, pooled over the learn split
of 59 maps and indexed where the sample allows by player count and level. The held-out
28 maps at $72 \times 72$ are never read for fitting.

Places.

- $p(n \mid k, |\mathrm{Land}|)$: place count per level. Today's `MacroStats.nzones` is
  the terrain-blob version. The place version counts $\hat\zeta$ regions.
- $p(\sigma / |\mathrm{Land}| \mid \rho)$: relative size by role.
- $p(\rho_p, \rho_q \mid \{p, q\} \in \hat A)$: role adjacency rates, a symmetric
  $|\mathcal{R}| \times |\mathcal{R}|$ table with a kind marginal $p(\kappa \mid \rho_p,
  \rho_q)$. `PlaceStats.adjacency` holds the counts behind both, keyed by the sorted role
  pair and the kind.
- $p(\deg p \mid \rho)$: degree by role.
- Home separation: $d_g(h_i, h_j) / N$ for home pairs, where $d_g$ is the geodesic
  distance on the walkable graph.

Layout.

- Compactness $c_p = |\partial R_p|^2 / |R_p|$ by role.
- Boundary roughness: the ratio of $|\partial R_p|$ to the perimeter of its convex hull.
- Straight coast fraction: the fraction of coast tiles whose coast runs straight for at
  least 6 tiles. The study measured 30 to 36% on control against 10% on hand-made maps.

Identity.

- $p(d_p \mid \rho_p, \omega_p \text{'s faction})$: dominant terrain by role and faction.
- $p(K \mid n, |\mathrm{Land}|)$: palette region count per level, the number of connected
  components of same-dominant inferred places on $\hat A$, stored with $n$ and
  $|\mathrm{Land}|$ and drawn the way the place count is drawn.
- Same share by role pair: the share of adjacent inferred places of roles
  $(\rho_p, \rho_q)$ that share a dominant. This is a reading, not an energy term.
- $p(\hat\Theta_p(d_p))$: dominant share, which sets $\theta_{\min}$ as a low quantile.
- Accent count and accent patch size per 100 tiles, by dominant terrain.
- Harsh share by distance to the nearest town. The study found this flat on hand-made
  maps: harsh terrain is not farther from towns there, and control surfaces carry 0.13 to
  0.21 more harsh terrain at every distance. The model therefore learns a harsh share per
  role, not a gradient.

Borders.

- $p(b_{pq} \mid \kappa, d_p = d_q)$: kind given adjacency and same dominant.
- Barrier depth $|W_{pq}| / |B_{pq}|$ by barrier class.
- $p(|\Psi_{pq}| \mid \kappa)$ and passage width.
- Vegetation mass fraction: the share of blocking vegetation in components of at least
  some size. The study measured 0.90 on hand-made surfaces against 0.70 on control. In
  this formulation that share is the share of vegetation that sits in barriers.

Paint.

- Pair terms $P(\tau(u) = a, \tau(v) = b)$ inside a place for 4-adjacent $(u, v)$. The
  existing `markov_0/1` tables are these, fitted map-wide. Fitting them inside inferred
  places removes border pairs from the texture model.
- Transition depth: the band width over which the terrain histogram moves from $d_p$ to
  $d_q$ across an open border.

Content. All indexed by $\rho$ and by level, with the existing per-terrain `TerrainStats`
retained as a fallback where the role sample is thin.

- Rate $\lambda_{\rho, \pi} = $ counted objects of purpose $\pi$ per tile in places of
  role $\rho$. Today's rate is per terrain, 3.1 to 3.5 per 100 tiles.
- Covariate effects $\theta_e, \theta_g, \theta_o$ as today: edge depth, passage
  distance, openness. Two new covariates: $\theta_h$ on the geodesic distance to the
  nearest home, binned, and $\theta_c$ on the place's role.
- Guard pairing: $P(\exists g : d_\infty(g, \text{mine}) \le 3)$, existing `guard_frac`.
- Guard at passage: $P(\text{a guard stands in } \psi \mid \kappa)$.
- Guard level against guarded value: the joint histogram of $s(g)$ and $\nu$ of the
  nearest reward, section 5.1.
- Value gradient: the slope of $\log \nu(R_p)$ against $d_g(\text{home}, p) / N$.
- Town position: distance from a home's town to the region's geodesic centre, in units
  of the region's radius $\sqrt{|R_p| / \pi}$.
- Valley rate: the fraction of levels with a region of at least 30 tiles, one guard and
  no town. The study measured 0.27 on hand-made surfaces and 0.35 underground against
  0.00 and 0.03 on control.

Roads.

- Road length per town, fraction of towns joined by road, and the share of objects
  within two tiles of a road. The study measured 0.41 of solid vegetation within two
  tiles of a road on hand-made surfaces against 0.17 on control.

## 4. Hard constraints and soft objectives

### 4.1 Hard constraints

A sample is rejected or repaired when any of these fails.

- C1, partition. $\zeta$ is total on $\mathrm{Land}$.
- C2, graph reachability. The subgraph of $(\Pi, A)$ on $\kappa \ne \mathrm{closed}$ is
  connected, and every gated or open adjacency has $|\Psi_{pq}| \ge 1$.
- C3, tile reachability. After content, every passable tile that is not inside a guard
  zone is reachable from every player town's approach tile in the graph on
  $\mathrm{Pass} \setminus \mathrm{Blocked}(X)$, where crossing a guard zone is allowed
  but counted. An island place is reachable by a shipyard or a boat on its coast.
  Underground places are reachable through at least one gate pair.
- C4, first town entry. For each player town $T$ with approach tile $a(T)$, no guard $g$
  has $a(T) \in \mathrm{ZOC}(g)$, and the start room
  $S(T) = $ the component of $a(T)$ in $\mathrm{Pass} \setminus \mathrm{Blocked}(X)
  \setminus \bigcup_g \mathrm{ZOC}(g)$ has $|S(T)| \ge 12$. These are the existing
  `StartRoomRule` numbers. A town itself may stand on barrier land that vegetation would
  have filled, so a town's footprint cells are removed from $W$ before C3 is checked.
- C5, legality. Every footprint lies on tiles its identity allows, by the catalog's
  `allowed_on`. Any two gameplay footprints keep a gap of at least 2 free tiles, the
  corpus 80% rule. No approach tile is covered by another object.
- C6, economy. Every one of the six basic mine resources appears at least once on the
  map. Gold mines number at most towns minus one.
- C7, determinism. $\mathrm{Map}(s, \mathrm{config})$ is a function.

### 4.2 Soft objectives

Let $\phi(\cdot)$ be the vector of statistics of section 3.4 computed on a generated map
with its own place map, and $\hat\phi$ the corpus distribution of the same vector. The
soft objective is a divergence
$J = \sum_j w_j D_j(\phi_j, \hat\phi_j)$, with $D_j$ a one-dimensional energy distance
for scalar statistics and a Kullback-Leibler term for tables. Each part minimises the
terms it owns, by sampling from the learned distribution directly where it can and by
accept-reject or local moves where it cannot. $J$ is also the Reading of section 8: a
map is read by the same functionals it was generated to match.

### 4.3 What is hard and what is soft, and why

Reachability and the first town entry are hard because a map that fails them is not
playable. Fairness is soft because the corpus is not symmetric and a judge reads exact
symmetry as a machine's work. This last claim is a guess that the study has not tested.
Every statistic is soft because the corpus is a sample of 59 maps and a hard match to a
small sample is a copy.

### 4.4 Fairness

For homes $h_i, h_j$ and a functional $f$, fairness is $|f(h_i) - f(h_j)| \le \epsilon_f$.
Three functionals are used.

- Reach to resources: $\min_{\text{mine of type } r} d_g(a(T_i), \text{mine})$ for each
  basic resource $r$, in tiles.
- Local value: $\sum_{p : d_g(h_i, p) \le D} \nu(R_p)$, the reward within $D$ tiles of the
  home.
- Guard load: the sum of $s(g)$ over guards on passages out of $h_i$.

$\epsilon_f$ is set from the corpus spread of the same functional between the homes of
one map. When a draw fails, Content resamples the place that breaks the tolerance, with a
bounded number of tries, then relaxes $\epsilon_f$ by a fixed factor.

## 5. The content problem

### 5.1 Intent as quantities

A designer's intent is written as four quantities. Each is learnable or is marked as not.

Value. Let $\nu : \mathcal{M} \to \mathbb{R}_+$ be a gold-equivalent value per mark. H3
pins some anchors: a gold mine yields 1000 gold a day, a sawmill or ore pit 2 units a
day, a rare mine 1 unit a day, a treasure chest offers 1000 to 2000 gold or the same in
experience, a resource pile holds a few units of one resource. The table for artifacts by
tier and for creature banks is a modelling choice with no exact game anchor, and this
note marks it as a guess to be fixed once and not learned. With $\nu$ fixed, the value
of a place is $\nu(R_p) = \sum_{u_i \in R_p} \nu(m_i)$. The value gradient is the
regression slope of $\log \nu(R_p)$ on $d_g(\text{nearest home}, p) / N$. Learnable:
yes, as a slope and a residual spread per role.

Guard strength against reward. For each guard $g$ define the guarded set $\mathcal{G}(g)$
as the objects whose approach tile is reachable from the guard side only through
$\mathrm{ZOC}(g)$, or that lie within $d_\infty \le 3$ when no such cut exists. Then
$\nu_g = \sum_{m \in \mathcal{G}(g)} \nu(m)$. The intent is a monotone link
$s(g) \approx \mathrm{round}(\alpha + \beta \log \nu_g)$. Learnable: the joint histogram of
$(s, \log \nu_g)$ is observable on every map where the guard is a random monster, which
gives a level, or a fixed stack, which gives a count that maps to a level by army
strength. The link's slope is learnable. Its residual tells how often designers break
the rule on purpose.

Choke points. A tile $u \in \mathrm{Pass}$ is a choke when its openness is at most 10
and its betweenness in the walkable graph, estimated between the place centres, is above
the place median. A passage $\psi$ is a choke by construction. The intent quantity is
$P(\text{guard on } \psi \mid \kappa, \rho_p, \rho_q)$ and $P(\text{guard on a choke
inside a place})$. Learnable: yes, directly, since guards and passages are both observable
after inference.

Pairing. A mine is paired when a guard stands within $d_\infty \le 3$. A dwelling is tied
to the town of its place. A bank stands away from the town. The intent quantities are
pairing rates by purpose and the distance distribution from each purpose to its place's
town, in units of the place radius. Learnable: yes, all are counts over observable pairs.

### 5.2 The content distribution

Content is a marked Gibbs point process on $\mathrm{Pass}$ with density

$$
p(X \mid P, \zeta, B, \tau) \propto
\mathbb{1}[\text{C3 to C6}] \,
\exp\Big( \sum_i U_1(u_i, m_i) + \sum_{i < j} U_2(u_i, m_i, u_j, m_j) \Big)
\prod_p \mathrm{Pois}\big(n_p^{\mathrm{tot}} ; \lambda_{\rho_p} |R_p|\big).
$$

The last factor is the assignment view: one total per place at the corpus rate for its
role. The forced objects of a place count inside its total. That rule exists today and
stays.

First-order term. For a tile $u$ in place $p$ with purpose $\pi$,

$$
U_1(u, m) = \theta_e[e(u)] + \theta_g[g(u)] + \theta_o[o(u)] + \theta_h[h(u)] +
\theta_c[\rho_p, \pi],
$$

with $e$ the edge depth, $g$ the 4-connected distance to the nearest passage of the
place, $o$ the openness in the $5 \times 5$ window, $h$ the geodesic distance to the
nearest home in bins of $N / 8$, and $\theta_c$ the role effect. The first three are the
existing log-linear fit with bins $6, 4, 4$ and the clip at $\pm 2$. The last two are new.
The Papangelou conditional intensity of adding $(u, m)$ to $X$ is
$\lambda(u, m \mid X) = \exp(U_1 + \sum_j U_2(u, m, u_j, m_j))$ times the constraint
indicator. The sampler reads $\lambda$ and nothing else.

Pair terms. Three families.

- Inhibition. $U_2 = -\infty$ when two gameplay footprints come within the gap of 2.
  This is C5 as an energy.
- Pairing. $U_2 = +\gamma_{\mathrm{mg}}$ for a guard within $d_\infty \le 3$ of a mine,
  $+\gamma_{\mathrm{dt}} \cdot k(d(u_i, u_j))$ for a dwelling and the town of its place
  with $k$ a learned kernel on distance in place radii, $-\gamma_{\mathrm{gg}}$ for two
  guards within the guard spacing of 2.
- Value link. For a guard $g$ and the set it guards,
  $U_2$ sums to $-\frac{(s(g) - \alpha - \beta \log \nu_g)^2}{2 \sigma_s^2}$. This pulls
  the guard's level toward the learned link.

Roads enter through the covariate $o$ and a final pair term that rewards objects within
two tiles of a road at the learned rate.

### 5.3 Sequential form

The joint density above is what the Reading measures. The sampler does not draw from it
with a chain. It draws in the order towns, mines, guards on passages, dwellings and
banks, visitables, treasure, piles, each from its conditional intensity given everything
placed so far. That is the existing step order, and it is a valid sampler of a different
distribution: the sequential product of conditionals, which equals the Gibbs density only
when the pair terms are symmetric and the order is random. The difference is accepted
because the sequential order encodes the designer's own order: the town first, then the
mines near it, then the guards on the way out. A birth-death chain is kept as a second
variant for the case where the sequential sampler leaves $J$ high on the pairing or
value-link terms.

Implementation note, a deviation forced by slice 4. The content plan is fixed in
`VegetationStep`, before any reward stands, so no guard has a guarded set $\mathcal{G}(g)$
when its level is drawn. The value link is therefore read as a table instead of
$\alpha + \beta \log \nu_g$: per level, the corpus value per tile and the mean random
monster level by role and by hop bin, each cell shrunk toward its hop bin and each hop bin
toward the level. Hop is the place-graph hop count from the nearest home, capped at 4,
not the geodesic distance in bins of $N / 8$, because the plan reads the place graph
before the ground is final. A passage guard takes the home's mean when one side is a home
and the stronger side's mean otherwise. Only random monster guards carry a level, so only
they enter the table. Mine guards keep their own link, and a pocket guard reads its level
off the value of the pocket it wards, as the pocket note below says. A home
town may lay its sprite overlay outside its place, while its blocking cells, entrance and
approach stay inside.

Implementation note, the ward rule. Every guard has a ward, the thing it protects: a reward
pickup, a resource pile, a mine, a dwelling, a bank, a town or a visitable within its reach,
or a passage into a place that holds one. A step decides the ward before it places the
guard, and a guard with an empty ward is never placed. A passage between two places of one
palette region $\pi$ takes no guard, and its border stays a passage. Two adjacent regions
never share a dominant, so the test is an equal planned dominant on both sides. A passage
guard counts the placed content of the place it leads into, the side more hops from home,
or both sides on a tie. The border step sees the towns, mines, dwellings, gated rooms and
treasure by then, and the planned content cannot mark a place empty, because every planned
place has a positive reward scale. A refused passage loses its entrance guard, its band
guards and its seals, because a seal beside a free entrance closes nothing. A closed border
keeps its seals, since they are barriers and not guards with a ward. Mine guards ward their
mine and pocket-cache guards ward a pocket that already has a free cache spot when the guard
is chosen. The rule lives in the content plan, so only the places model applies it and
markov maps stay unchanged.

Implementation note, the pocket rule. A pocket is a dead end behind a narrow mouth. The
finder reads the drawn pocket masks, and under the places model it also takes every
walkable region of at most 16 tiles that the map loses when one mouth tile is removed,
whatever its shape. Every found pocket is filled. A pocket is deep when it holds at least
3 tiles and reaches 2 steps in from its mouth, and shallow otherwise. Every deep pocket
takes a guard when one fits at its mouth. A per-place cap at the corpus random guard rate
was tried and dropped: it left 109 of 191 deep pockets on 10 seeds unguarded and held the
map at 1.09 guards per 100 land tiles against the corpus 1.43. A guarded pocket holds an artifact or a
Pandora's box at its deepest tile, its tier drawn around the place's mean guard level,
and up to 5 more resource piles or chests. The guard stands last, and its level follows
the gold value of everything in the pocket. A shallow pocket and a pocket whose guard
does not fit get up to 5 resource piles or chests, never an
artifact and never a Pandora's box. The rule reads the content plan, so markov maps keep
the old guarded caches.

### 5.4 Roads

Given towns and passages, a road network is a Steiner-like forest. The sampler builds it
greedily: for each home, Dijkstra from the town's approach tile on $\mathrm{Pass}
\setminus \mathrm{Blocked}(X)$ with edge cost 1 on the place's dominant terrain and a
learned penalty elsewhere, to the nearest passage of each gated adjacency out of the
home, then from each passage into the neighbour until a learned total length per town is
spent. Turns cost a small penalty so a road does not wiggle on open ground. The study's
spine variant S1r is the one variant whose panel moved roads off the top of the cue list.

Implementation note, the deviations of slice 6. `RoadsStep` lays the roads last, after
every object, on the land no blocking cell or gate covers. No later object can then cover
a road, and every road tile stays walkable. The cost is the road pair term of 5.2: no
object is drawn toward a road, so the rewards near a road come from the sites a road
seeks, not from the content sampler. The learned penalty is the odds ratio of a corpus
road tile on its place's dominant terrain against any land tile on it, floored at 1. The
turn penalty is a constant 0.5, not learned. The learned total length is the median
corpus road share of walkable land, over the levels with a home and a road, times the
walkable tiles, split evenly among the homes. A road crosses open borders as well as
gated ones, through the open front or a passage band, never a closed border. Each home's
crossings are taken best first, at the new tiles of the leg over the corpus crossing rate
of the pair's roles and kind. The first crossing is laid whatever the budget, so every
home reaches at least one neighbour. Inside each place it reaches, a road runs to a
player town first, then to each important site while the budget lasts, or to the place's
centre when the place has no site. A leg into a place another home's road already
reaches ends on that road and goes no further. A home whose road would stay one tile
gets a stub of at least 4 tiles inside its place. Every road of a map takes one surface,
drawn once from the corpus surface counts pooled over every level, so no map mixes dirt,
gravel and cobblestone.

## 6. How terrain and content couple

### 6.1 The shared latent

Both problems read the same three values: the place graph $P$, the place map $\zeta$
and the borders $B$. Terrain reads them to decide where a coat ends and a barrier begins.
Content reads them to decide where a home's town stands, which passage gets a guard, and
how much a place holds. Vegetation reads $B$ to know which tiles to fill. Roads read $B$
for passages and $X$ for towns.

In the factorisation of section 2.1, $\tau$ and $X$ are conditionally independent given
$(P, \zeta, B)$ except for one edge: content reads $\tau$ through `allowed_on` and
through the per-terrain fallback statistics. That edge is thin. The thick coupling is
through the latent.

### 6.2 Why terrain first is the wrong factorisation

Today's generator computes $\zeta = \mathrm{segment}(\tau)$: a place is a 4-connected
component of one terrain. Written as a model, that is

$$
p(\tau) \, \delta\big(\zeta - \mathrm{segment}(\tau)\big) \, p(X \mid \zeta, \tau).
$$

Three consequences follow from the equation, each one a judge's tell.

1. Places carry no role. $\zeta$ is a deterministic function of $\tau$ and $\tau$ was
   drawn without roles, so $I(\rho ; \zeta) = 0$: the mutual information between any
   role variable and the place map is zero because no role variable exists. Content's
   intensity can only read terrain and geometry. The valley rate on control was 0.00
   against 0.27 because a valley is a role, and the model had none.
2. Every border is a raw cut. By construction, $(u, v) \in B_{pq}$ implies $\tau(u) \ne
   \tau(v)$, so $\mathrm{cut}(\tau) = \sum_{pq} |B_{pq}|$. The no-raw-cut invariant
   cannot hold. Texture in a 2-tile band about each border changes the pair statistics
   inside the band and leaves the cut in place. The judges' "hard seam with noise" is
   this equation.
3. Accents become places. An accent patch is a terrain component, so it is a place, so it
   draws its own total, its own entrances and its own guards. Despeckle removes it to
   keep the place count in range, which is why control's land zone count already sits in
   the learned range while its places read wrong. The place-size distribution of
   $\mathrm{segment}(\tau)$ equals the terrain-blob-size distribution, and the corpus
   place-size distribution under $\hat\zeta$ is a different object.

The oracle confirms the direction. Real hand-made terrain under generated content closed
30% of the judge gap. Under terrain-first, that experiment gave content a real $\tau$ and
a $\zeta$ segmented from it, and still no $\rho$. Content stayed roleless, and the gap
stayed. In the place-first factorisation the oracle would have handed content a real
$\hat\zeta$ and real roles.

### 6.3 Why content first is also wrong

The reverse order $p(X) \, p(\tau \mid X)$ puts towns before land. A town needs a region
of at least 150 passable tiles around it, the existing `TOWN_MIN_AREA`, and a barrier
behind it. Fitting terrain to a scatter of towns is a constrained inverse problem with
many solutions and no guarantee that any is compact. Places first gives both sides a
region to work inside.

### 6.4 Feedback edges that remain

- Town footing. A town's footprint may stand on barrier land, so $W$ loses those tiles
  after content. Borders must leave each home's barrier thicker than a town's footprint
  at the town's planned side, or accept the breach as a planned passage.
- Passage count. Content may seal a gated passage behind a Border Gate, which turns
  gated into closed for a player without the key. C2 counts a Border Gate as a passage
  because the Keymaster stands outside it.
- Island places. Ground decides an island, Content must place a shipyard on the coast
  facing it. The existing seaport guarantee is this edge.

## 7. Samplers and complexity

The budget is about one second per map in Python with numba. Today's pipeline fits it
with Markov as the hot loop, already compiled. Every sampler below is $O(|V| \log |V|)$
or less per level, with $|V| = 5184$. Constants are the question, not orders.

Places. Draw $n$ from $p(n \mid k, |\mathrm{Land}|)$. Assign $k$ homes. Draw the remaining
roles from the role marginal. Draw sizes from $p(\sigma / |\mathrm{Land}| \mid \rho)$ and
renormalise. Draw the adjacency graph by a Metropolis walk over edge sets with energy
$-\sum_{pq \in A} \log p(\rho_p, \rho_q \mid \text{adjacent}) + \lambda_{\deg} \sum_p
(\deg p - \bar d_{\rho_p})^2$, with the constraint that the graph is planar and connected
on non-closed edges. With $n$ about 26 places per level and a few hundred moves this is
milliseconds.
Planarity is checked by the layout, not here: Layout rejects a graph it cannot embed.

Ground. Value noise thresholded at the corpus barrier-fraction quantile, as today,
$O(|V|)$. The conditioned variant adds a low-frequency pull toward water along the
planned closed adjacencies. It needs anchors first, so Ground and Layout alternate once:
anchors on a provisional land mask, water pulled, anchors refined.

Layout. Anchors by multidimensional scaling of the graph distance on $(\Pi, A)$ into the
plane, $O(n^3)$, then snapped to land and spread by one max-min pass. Regions by
capacity-constrained multi-source Dijkstra with jittered costs, the existing growth,
$O(|V| \log |V|)$. Check $A \subseteq \hat A(\zeta)$. On failure, move the anchor of the
missing pair toward each other by one step of the graph distance and regrow, at most
five tries. The watershed and frame arms are alternative region-shape variants with the
same contract.

Identity. The palette partition first: draw $K$ from the corpus records nearest
$(n, |\mathrm{Land}|)$, scaled by $n$ over the record's place count and floored at the
component count of $\hat A$. Seed and grow as in 2.1, $O(n^2)$ for the farthest-first
seeds and $O(n^2)$ for the growth. Then a Metropolis walk over the $K$ region dominants
with the energy of 2.1, from a greedy colouring that gives no region its lower-indexed
neighbours' terrains. The hard exclusion enters as a large finite energy, so the walk
can pass through a clash and leave it. With $K$ about 7 and a few hundred sweeps this is
milliseconds. The walk returns one dominant per place, $d_p = d_{\pi(p)}$.

Borders. Boundary extraction, $O(|V|)$. Kind per realised adjacency from the table. For a
barrier, $W_{pq}$ is the set of tiles within depth $w$ of $B_{pq}$ on either side, by a
BFS of depth $w$ from $B_{pq}$, $O(|B_{pq}| w)$. Passages: pick $|\Psi_{pq}|$ crossing
points spaced at least `MIN_ENTRANCE_SEP` apart along $B_{pq}$, then carve a 3-wide
corridor through $W_{pq}$ by the shortest path across the band. This reuses
`plan_entrances` with the band now produced before paint, which closes L2 as a reshape.
For a transition, $Z_{pq}$ is the same BFS with a graded distance label.

$\Psi$ is the only entrance plan the later steps read. The zone plan builds each zone's
entrances and walkable web from it, the vegetation keeps its passages clear and closes
the rest of every front, and the border guard step guards its passages. An open pair's
passage is its whole front. The border guard step keeps its crossing sealer as a safety
net and logs how many leaks it sealed, which reads how well the barrier held.

Implementation note, the deviations of slice 5. A realised pair the place graph never
planned is closed, because nothing in the plan asked for it. The spanning set of passable
pairs is a spanning forest over the realised pairs, planned pairs first and each weighted
by the share of its role pair the corpus leaves passable, so a level split by water keeps
one tree per piece. Its pairs draw gated or open, every other planned pair draws from the
whole table. The content plan counts hops over the passable pairs only. No barrier of
depth $w$ is carved: a closed front closes by the vegetation's densification and its
border sealer, as before. The sealer may close a tile of a zone's web only when that
tile's neighbours inside the same zone stay joined, because a detour through the
neighbouring zone is the very crossing it is closing. Markov keeps one gated pair per
realised adjacency with every passage `plan_entrances` plans, so its maps do not change.

Paint. Base coat is a lookup, $O(|V|)$. Accent patches: a Poisson number of seeds per
place at the learned rate, each grown by BFS to a size drawn from the accent-size
distribution, confined to $R_p \setminus Z_{pq}$. Transition grading: in $Z_{pq}$, tile
$u$ takes $d_q$ with probability $\mathrm{dist}(u, R_p) / w_{pq}$ smoothed by one Gibbs
sweep. Texture: Markov Gibbs sweeps inside each place over the tiles not in a barrier,
with the pair table fitted inside places. Today's sweeps run in a 2-tile band about
every border. Moving them inside places changes where they run and not how many tiles,
so the compiled cost is unchanged in order.

Content. Covariates by BFS: edge depth, passage distance, openness, home distance, each
$O(|V|)$ per level. Per place: draw the total, split by role mix, then place each object
by sampling a tile from $\lambda(\cdot, m \mid X)$ restricted to the place, with
rejection against C4 and C5. Each placement is $O(|R_p|)$ for the weight vector plus
$O(|F|)$ per rejection. With about 150 objects on a 72 map that is a few hundred
thousand operations. Guards on passages: one per passage with probability from the
table, level from the value link with the guarded set computed by one BFS behind the
passage. Fairness check and bounded resampling as in 4.4.

Roads. One Dijkstra per town and per passage on the passable graph, $O(|V| \log |V|)$
each, at most a few dozen runs.

Reading. All statistics of 3.4 on the generated map, each $O(|V|)$ or $O(n^2)$.

Total: a few tens of $O(|V| \log |V|)$ passes and the Markov sweeps. Today's generator
runs the same number of passes with a different order. The place-first order adds no
iterative solver and no map-wide optimisation. The one new loop is the Layout retry,
bounded at five.

## 8. Judge-free readings per part

Each reading is a scalar or a short vector computed on a generated map and on the held
set, with the hand-made against hand-made spread as the floor. A part passes when its
readings fall inside the hand-made spread.

| Part | Reading | Definition |
|---|---|---|
| Places | place count | $n$ against $p(n \mid k, |\mathrm{Land}|)$ |
| Places | role coverage | one home per player, at least one treasure ground and one pocket per level at the corpus rate |
| Places | home separation | $d_g(h_i, h_j) / N$ |
| Layout | compactness | $|\partial R_p|^2 / |R_p|$ by role |
| Layout | roughness | boundary length over hull perimeter |
| Layout | straight coast | share of coast in straight runs of 6 or more |
| Identity | dominant share | $\min_p \hat\Theta_p(d_p)$ and its mean |
| Identity | same share | share of $\hat A$ pairs with $d_p = d_q$, corpus 0.71 pooled |
| Identity | palette regions | components of same-dominant places on $\hat A$, corpus median 6 |
| Identity | harsh profile | harsh share by distance to the nearest town, which must be flat |
| Identity | faction match | share of homes on their faction's native terrain |
| Borders | raw cut | $\mathrm{cut}(\tau) / \sum_{pq} |B_{pq}|$ |
| Borders | passages | $|\Psi_{pq}|$ and width by kind |
| Borders | mass share | share of blocking vegetation inside barriers |
| Paint | accent size | accent patch size distribution per 100 tiles |
| Paint | pair table | inside-place pair statistics against the fitted table |
| Content | rate by role | $n_p^{\mathrm{tot}} / |R_p|$ by role |
| Content | value gradient | slope of $\log \nu(R_p)$ on home distance |
| Content | guard link | residual of $s(g)$ against $\alpha + \beta \log \nu_g$ |
| Content | pairing | mine-guard and dwelling-town rates |
| Content | valley rate | levels with a 30-tile region, one guard, no town |
| Content | start room | C4 holds on every player town |
| Roads | road reach | road length per town and share of objects within two tiles |
| Whole | two-sample distance | energy distance between the reading vectors of generated and held maps |

The whole-map reading is the stand-in for the judge. It is honest only when every
component reading is one the judge could see in the picture. A reading that passes while
judges still name a cue means the cue is missing from the table, not that the judge is
wrong.

### 8.1 The default terrain model

`python -m vcmi_mapgen.cli readings` prints these readings for generated maps beside the
corpus spread. One reader from `core/reading/` measures both sides. The section above
states no rule for choosing between two terrain models, so the choice uses a fallback
rule. The candidate replaces the default when its median sits closer to the corpus median
on a strict majority of the readings. No reading may sit farther from the corpus median
than the default's by more than the corpus interquartile range. Pipeline time is printed
but not judged.

The run on 2026-10-04 generated seeds 1 to 10 at size 72 with each model and read the 71
corpus maps of side 72. Each cell is a median. The corpus column adds its quartiles.

| Reading | Corpus [q1, q3] | places | markov |
|---|---|---|---|
| palette regions | 7 [5, 7.5] | 5 | 7 |
| same share | 0.625 [0.510, 0.756] | 0.760 | 0.394 |
| raw cut | 0.052 [0.022, 0.111] | 0.042 | 0.062 |
| open share | 0 [0, 0.020] | 0 | 0 |
| gated share | 0.457 [0.368, 0.529] | 0.544 | 0.619 |
| closed share | 0.533 [0.450, 0.629] | 0.456 | 0.372 |
| walkable share of land | 0.365 [0.334, 0.443] | 0.458 | 0.465 |
| walkable share in a guard's zone of control | 0.182 [0.139, 0.206] | 0.300 | 0.237 |
| rewards per 100 walkable tiles | 21.0 [17.7, 24.6] | 14.5 | 13.6 |
| guards per 100 land tiles | 1.43 [1.18, 1.72] | 2.90 | 2.45 |
| home separation | 1.07 [0.83, 1.60] | 1.65 | 1.13 |
| value at hop 0 | 124 [104, 141] | 110 | 116 |
| value at hop 1 | 127 [102, 153] | 114 | 117 |
| value at hop 2 | 127 [108, 140] | 144 | 121 |
| value at hop 3 | 115 [100, 155] | 119 | 102 |
| value at hop 4 or more | 143 [122, 175] | 126 | 124 |
| guard level at hop 0 | 1.95 [1.67, 2.56] | 2.52 | 2.53 |
| guard level at hop 1 | 2.54 [1.96, 2.93] | 2.55 | 2.57 |
| guard level at hop 2 | 3.00 [2.47, 3.38] | 2.41 | 2.61 |
| guard level at hop 3 | 2.80 [2.29, 3.53] | 2.43 | 2.56 |
| guard level at hop 4 or more | 2.83 [2.12, 3.50] | 2.59 | 2.50 |
| road share of walkable tiles | 0.100 [0.052, 0.217] | 0.124 | 0 |
| seconds per map | | 3.7 | 3.8 |

Places sits closer on 12 of the 22 judged readings: same share, raw cut, the gated and
closed shares, walkable share, rewards, guard level at hops 0, 1 and 4, value at hops 3
and 4, and road share. Open share ties. No reading is worse than markov's by more than the
corpus IQR. Places is the default, and markov stays selectable with `--terrain markov`.

The margin is narrow. Both models place about twice the corpus guard rate and too few
rewards per walkable tile, and both leave too much of the walkable land inside a guard's
zone of control. Places also lays out homes farther apart than the corpus and merges its
palettes into fewer regions.

## 9. Why each failed arm fails, in these terms

Every arm below kept $\zeta = \mathrm{segment}(\tau)$. Each changed one factor of the
terrain-first model and left the factorisation alone, so each inherited the three
consequences of 6.2. The study's control sat at 50 composition answers over 53 pairs with
a floor of 29 and a target of at most 37.

- W1, watershed layout, 44. It changed the region-shape variant of $p(\tau)$. Regions
  became basins instead of grown blobs. Every border was still a terrain change, so the
  raw-cut reading did not move, and no role existed for content to read.
- W2, a second watershed setting, 40. Same change, different scale. The place count and
  compactness moved toward the corpus. Raw cut and roles did not. The gain is the
  Layout reading alone.
- P1, a sealed valley, 39. It added one role by hand after paint: a region sealed by
  vegetation with a guard and no town. In the formulation that is a single edit to $X$
  and $W$ with no $P$ behind it. It moved the valley rate from 0.00 toward 0.27, which is
  the gain. It did not touch the other roles or the borders, and it could only seal a
  terrain blob, so the valley's shape was still a paint accident.
- F1, frames, 41. It imposed a layout from a frame warp. That is a Layout variant with a
  fixed shape family. It moved compactness and roughness. It carried no palettes by
  role and no border kinds, and it drew its shapes from a family rather than from a
  learned distribution, which is the template the premises forbid in another guise.
- WS1, watershed on the spine-road host, 39. Roads fell off the top of the cue list, and
  terrain band and terrain border took 22 answers each. Fixing roads exposed the next
  cue. In the formulation, $p(\mathrm{Road} \mid X, B, \tau)$ improved while
  $\mathrm{cut}(\tau)$ stayed at the terrain-first maximum. That is the premise about
  roads and regions in numbers: one tell removed, the next one counted.
- WP1, watershed with the valley on the same host, 40. Terrain band took 25. Five
  player towns had a guard inside their entrance's zone of control. That is C4 broken.
  Content placed guards without knowing which places were homes, because no $\rho$
  existed. A model with homes as a role cannot make this error: the guard intensity is
  zero on a home's start room by construction.

Across the six, the Layout readings moved and the Borders, Identity and role-dependent
Content readings did not. The judge counted what did not move.

## 10. Open decisions

Three choices are left open by this note. Each has a recommendation.

1. Place inference on the corpus. Section 3.2 defines $\hat\zeta$ by a geodesic Voronoi
   on passability seeded by towns and cut by guards. An alternative seeds by terrain
   blobs and merges. The passability version matches how a player reads a hand-made map,
   and it is the one that makes accents stay inside places. Recommendation: the
   passability version, checked on a handful of corpus maps by eye before any statistic is
   trusted.
2. The content sampler. Section 5.3 keeps the sequential sampler as the default and a
   birth-death chain as a variant. The sequential sampler cannot pull guard level toward
   the value link once a guard is placed, and the chain can. Recommendation: sequential
   first, with the value link applied at the moment a guard is drawn, and the chain only
   if the guard-link reading stays outside the hand-made spread.
3. Fairness. Section 4.4 makes fairness a tolerance on three functionals with bounded
   resampling, and section 1.2 defines the exact symmetric alternative. Recommendation:
   the tolerance. Hand-made maps are not mirror images, the corpus spread between a map's
   own homes gives the tolerance for free, and exact symmetry is a template.
