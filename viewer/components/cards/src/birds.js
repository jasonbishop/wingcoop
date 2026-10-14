// Sample birds for demos and tests. Your game data will replace these; the shape is the
// `Bird` typedef in cardFace.js. Only two illustrations exist so far (art/manifest.json
// bird_* entries); add more by cropping new art the same way and pointing `image` at it.

const SPARROW = new URL('../assets/birds/sparrow.jpg', import.meta.url).href;
const OSPREY = new URL('../assets/birds/osprey.jpg', import.meta.url).href;

export const SAMPLE_BIRDS = [
  {
    id: 'song-sparrow', name: 'Song Sparrow', scientific: 'Melospiza melodia', image: SPARROW,
    points: 0, habitats: ['forest', 'grassland', 'wetland'], food: ['invertebrate', 'seed'], foodOr: true,
    nest: 'bowl', eggLimit: 5, wingspan: 23, powerColor: 'pink',
    power: 'Once between turns, when another player tucks a card, tuck 1 card from your hand behind this bird.',
  },
  {
    id: 'osprey', name: 'Osprey', scientific: 'Pandion haliaetus', image: OSPREY,
    points: 5, habitats: ['wetland'], food: ['fish'],
    nest: 'platform', eggLimit: 2, wingspan: 160, powerColor: 'brown',
    power: 'All players gain 1 fish from the supply.',
  },
  {
    id: 'chipping-sparrow', name: 'Chipping Sparrow', scientific: 'Spizella passerina', image: SPARROW,
    points: 1, habitats: ['forest', 'grassland'], food: ['invertebrate', 'seed'],
    nest: 'bowl', eggLimit: 3, wingspan: 22, powerColor: 'white',
    power: 'Lay 1 egg on any bird.',
  },
  {
    id: 'bald-eagle', name: 'Bald Eagle', scientific: 'Haliaeetus leucocephalus', image: OSPREY,
    points: 9, habitats: ['wetland'], food: ['fish', 'fish', 'rodent'],
    nest: 'platform', eggLimit: 1, wingspan: 203, powerColor: 'white',
    power: 'Gain all fish that are in the birdfeeder.',
  },
  {
    id: 'savannah-sparrow', name: 'Savannah Sparrow', scientific: 'Passerculus sandwichensis', image: SPARROW,
    points: 2, habitats: ['grassland'], food: ['seed'],
    nest: 'ground', eggLimit: 2, wingspan: 18, powerColor: 'brown',
    power: 'Lay 1 egg on any bird with a ground nest.',
  },
];
