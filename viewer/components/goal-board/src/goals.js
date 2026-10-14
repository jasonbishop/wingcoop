// Round-end goal tiles. Each key needs a tile image (cropped via art/manifest.json).
// Add new goals by cropping their art and adding an entry here.

export const GOALS = {
  wetland_total: {
    label: 'Total birds in wetlands',
    image: new URL('../assets/goal_wetland_total.jpg', import.meta.url).href,
  },
  cave_dwellers: {
    label: 'Cave dwellers',
    image: new URL('../assets/goal_cave_dwellers.jpg', import.meta.url).href,
  },
};
