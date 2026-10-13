// Where things are on mat.jpg, as fractions of the image (0..1 from the left / top).
// Measured from art/source/player-mat.jpg; re-measure if the mat art changes.

export const HABITATS = ['wetland', 'forest', 'grassland'];
export const SLOTS_PER_ROW = 7;

export const MAT_IMAGE = [2576, 1438];

// Card frame rectangles: left edges of the 7 columns, and top/bottom of each row (image px).
const COLS_X = [679, 945, 1208, 1468, 1727, 1989, 2250];
const COL_W = 228;
const ROWS_Y = { wetland: [122, 458], forest: [554, 889], grassland: [990, 1318] };

/** Centre of a slot as fractions of the image. */
export function slotCenterUV(habitat, i) {
  const [y0, y1] = ROWS_Y[habitat];
  return [(COLS_X[i] + COL_W / 2) / MAT_IMAGE[0], (y0 + y1) / 2 / MAT_IMAGE[1]];
}

/** Slot size as fractions of the image. */
export function slotSizeUV(habitat) {
  const [y0, y1] = ROWS_Y[habitat];
  return [COL_W / MAT_IMAGE[0], (y1 - y0) / MAT_IMAGE[1]];
}
