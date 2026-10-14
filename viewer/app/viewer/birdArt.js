// Bird illustrations. Drop an image into components/cards/assets/birds/ named after the
// bird's id ("136.jpg") or its name in lower case with dashes ("great-horned-owl.jpg") and
// the card picks it up; birds without one show a silhouette.
//
// (The sheets in art/source hold only two birds so far; crop more through art/manifest.json.)

const files = import.meta.glob('../../components/cards/assets/birds/*.{jpg,jpeg,png,webp}', { eager: true, query: '?url', import: 'default' });

const byName = {};
for (const [path, url] of Object.entries(files)) {
  byName[path.split('/').pop().replace(/\.[a-z]+$/, '').toLowerCase()] = url;
}

// Art whose file name is not a bird's own name.
const ALIASES = { 'song-sparrow': 'sparrow' };

export const slug = name => name.toLowerCase().replace(/['’.]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

/** URL of a bird's illustration, or undefined. */
export function birdArt(id, name) {
  const s = slug(name || '');
  return byName[String(id)] ?? byName[s] ?? byName[ALIASES[s]] ?? undefined;
}
