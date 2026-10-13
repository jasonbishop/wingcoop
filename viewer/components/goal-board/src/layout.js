// Where things are on board.jpg, as fractions of the image. Measured from
// art/source/goals-and-cards.jpg (the board crop starts at sheet pixel 122, 180).

export const BOARD_IMAGE = [2160, 882];
export const ROUNDS = 4;
export const SQUARES = 6;
export const MEDALLIONS = 5;   // numbered 1..5

const X0 = 122, Y0 = 180;
const ROW_Y = [339, 526, 713, 901];
const SQUARE_X = [551, 697, 835, 973, 1111, 1277];
const MEDALLION_X = [1492, 1648, 1806, 1963, 2116];

const uv = (x, y) => [(x - X0) / BOARD_IMAGE[0], (y - Y0) / BOARD_IMAGE[1]];

/** round 1..4, i 0..5 */
export const squareUV = (round, i) => uv(SQUARE_X[i], ROW_Y[round - 1]);
/** round 1..4, n 1..5 */
export const medallionUV = (round, n) => uv(MEDALLION_X[n - 1], ROW_Y[round - 1]);
/** round 1..4: just left of the board, level with the row */
export const rowUV = round => uv(X0, ROW_Y[round - 1]);
