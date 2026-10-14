// Where everything sits. Players are seated around a round table, clockwise in seat order
// seen from above, each with their mat facing the middle. The shared pieces ride a
// turntable in the middle that turns to face whichever seat is being watched.
//
// World: table top y = 0, +z toward the default camera. Seat 0 sits at +z.
// "Seat frame": the same axes turned so that a seat's player is at +z looking at the middle.

import { MAT_H } from '../../../components/player-mat/src/index.js';
import { CARD_H } from '../../../components/cards/src/index.js';

export const SUSAN_RADIUS = 10;

// Things in front of a mat, relative to the mat's centre (x to the player's right, z toward the player).
export const SEAT = {
  halfWidth: 9.2,
  inner: MAT_H / 2,                       // mat edge nearest the middle
  supply: [-2.6, MAT_H / 2 + 0.75],       // food piles
  plaque: [2.0, MAT_H / 2 + 0.9],
  bonus: [6.3, MAT_H / 2 + 1.3],          // bonus cards
  cubes: [-8.55, MAT_H / 2 + 0.45],       // turns left this round
  firstToken: [-6.3, MAT_H / 2 + 0.8],
  hand: [0, MAT_H / 2 + 2.55 + CARD_H / 2],
  handWidth: 17,
  outer: MAT_H / 2 + 2.55 + CARD_H + 0.3, // far edge of the hand
};

// Shared pieces on the turntable (x, z), seen from the watched seat.
export const CENTRE = {
  board: [0.6, 4.3],
  feeder: [-5.0, -5.0], feederScale: 0.55,
  deck: [-1.8, -1.2],
  tray: [2.75, -1.2],
  discard: [6.6, -1.2],
  bonusDeck: [2.6, -4.8],
  bonusDiscard: [4.5, -4.8],
  reveal: [2.75, -3.6],                   // where a card being looked at is held up
};

/** Distance of a mat's centre from the middle of the table for n players. */
export function seatRadius(n) {
  const clear = SUSAN_RADIUS + 1.2;
  // with many seats, neighbouring mats must not overlap at their inner corners
  const polygon = n >= 3 ? (SEAT.halfWidth + 0.4) / Math.tan(Math.PI / n) : 0;
  return Math.max(clear, polygon) + SEAT.inner;
}

/** Diameter of the (round) table. */
export function tableSize(n) {
  return 2 * (seatRadius(n) + SEAT.outer + 6);
}

/** Angle of a seat around the table, in radians clockwise from seat 0 (seen from above). */
export const seatAngle = (seat, n) => (2 * Math.PI * seat) / n;

/** rotation.y that turns the seat frame to a seat (also the turntable's angle for that seat). */
export const seatRotation = (seat, n) => -seatAngle(seat, n);

/** Seat-frame point -> world [x, y, z]. */
export function fromSeatFrame([x, y, z], seat, n) {
  const r = seatRotation(seat, n), c = Math.cos(r), s = Math.sin(r);
  return [x * c + z * s, y, -x * s + z * c];
}

export function seatPosition(seat, n) {
  return fromSeatFrame([0, 0, seatRadius(n)], seat, n);
}

/**
 * Camera views from a seat, as { position, target } in world coordinates.
 *   seat:   the player's mat and hand with the turntable beyond it
 *   mat:    close on the mat and hand
 *   centre: the turntable
 *   table:  everything
 */
export function seatView(kind, seat, n) {
  const R = seatRadius(n);
  const near = R + SEAT.outer + 3.4;      // just behind the hand
  // A camera pitched down by `pitch` that frames the table from z = far to z = near
  // (the lens is 32 degrees tall): how high, how far back, and where it looks.
  const frame = (pitch, far) => {
    const lo = 1 / Math.tan(((pitch - 16) * Math.PI) / 180), hi = 1 / Math.tan(((pitch + 16) * Math.PI) / 180);
    const y = (near - far) / (lo - hi), z = near + y * hi;
    return { position: [0, y, z], target: [0, 0, z - y / Math.tan((pitch * Math.PI) / 180)] };
  };
  const frames = {
    seat: frame(50, -(SUSAN_RADIUS + 4)),
    mat: { position: [0, 25, R + 22.5], target: [0, 0, R + 2.2] },
    centre: { position: [0, 25, 21.5], target: [0, 0, 0.6] },
    table: frame(68, -(near + 1)),
  };
  const f = frames[kind] || frames.seat;
  return { position: fromSeatFrame(f.position, seat, n), target: fromSeatFrame(f.target, seat, n) };
}
