// Plain sentences for events and decisions. Text may contain symbols in brackets
// ("[fish]"), which the HUD turns into icons.

import { FOODS, HABITATS, DIE_FACES, playerName } from './data.js';

const P = p => playerName(p);
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
const foodList = vec => vec.map((n, f) => (n ? `${n} [${FOODS[f]}]` : null)).filter(Boolean).join(' + ') || 'nothing';
const faceText = f => (f === 5 ? '[invertebrate]/[seed]' : `[${FOODS[f]}]`);
const WHY = { bird_cost: 'to play', bonus_trade: 'for the row bonus', power_cost: 'for a power', end_of_turn: 'at the end of the turn', predator_miss: 'after the hunt missed' };

export const DECISION_TITLES = {
  setup_keep_birds: 'Which starting birds to keep',
  setup_discard_food: 'Which starting food to give up',
  setup_keep_bonus: 'Which bonus card to keep',
  set_difficulty: 'Set the difficulty for this round',
  action: 'Choose an action',
  pay_food: 'How to pay the food cost',
  pay_egg: 'Which egg pays the column cost',
  take_die: 'Take a die from the birdfeeder',
  reroll_feeder: 'All dice match: reroll the feeder?',
  draw_card: 'Draw a card',
  lay_egg: 'Where to lay an egg',
  bonus_trade: 'Trade for one extra?',
  activate_power: 'Use this power?',
  cache_food: 'Cache the food?',
  optional_lay: 'Also lay an egg here?',
  tuck_card: 'Which card to tuck',
  discard_card: 'Which card to discard',
  discard_egg: 'Which egg to discard',
  discard_food: 'Which food to discard',
  choose_food: 'Choose a food',
  choose_first_player: 'Who goes first',
  repeat_power: 'Which power to repeat',
  move_bird: 'Move the bird where',
  play_extra: 'Play another bird?',
  keep_bonus: 'Which bonus card to keep',
  draft_pick: 'Pick a card',
  end_turn: 'End of turn',
};

export const ACTION_NAMES = { play: 'Play a bird', food: 'Gain food', eggs: 'Lay eggs', cards: 'Draw cards', play_extra: 'Play another bird' };

/** One sentence for an event. `book` is the CardBook. */
export function describeEvent(e, book) {
  const bird = id => book.birdName(id);
  switch (e.e) {
    case 'setup': return 'The table is set: goals, bird tray and birdfeeder.';
    case 'setup_kept_birds': return `${P(e.p)} keeps ${e.birds.length ? e.birds.map(bird).join(', ') : 'no birds'}.`;
    case 'setup_discarded_food': return `${P(e.p)} gives up ${e.food.length ? e.food.map(f => `[${FOODS[f]}]`).join(' ') : 'no food'}.`;
    case 'bonus_drawn': return `${P(e.p)} draws ${plural(e.cards.length, 'bonus card')}: ${e.cards.map(b => book.bonusName(b)).join(', ')}.`;
    case 'bonus_reshuffled': return `The bonus discard pile is shuffled into a new bonus deck of ${plural(e.cards, 'card')}.`;
    case 'bonus_kept': return `${P(e.p)} keeps the bonus card ${book.bonusName(e.bonus)}.`;
    case 'group_decision': return e.kind === 'set_difficulty' ? `The group sets the difficulty to ${e.choice[1]}.` : `The group decides: ${e.kind}.`;
    case 'round_start': return `Round ${e.round} begins. ${P(e.first)} goes first. Goal: ${book.goal(e.goal)?.plain ?? e.goal}.`;
    case 'turn_start': return `${P(e.p)}'s turn.`;
    case 'turn_end': return `${P(e.p)}'s turn ends.`;
    case 'action':
      if (e.action === 'play' || e.action === 'play_extra') return `${P(e.p)} plays ${bird(e.bird)} in the ${HABITATS[e.habitat]}${e.action === 'play_extra' ? ' (extra bird)' : ''}.`;
      return `${P(e.p)}: ${ACTION_NAMES[e.action] ?? e.action}.`;
    case 'food_spent': return `${P(e.p)} pays ${foodList(e.food)} ${e.bird != null && e.why === 'bird_cost' ? `for ${bird(e.bird)}` : WHY[e.why] ?? ''}.`.replace(' .', '.');
    case 'egg_discarded': return `${P(e.p)} removes an [egg] from ${bird(e.bird)} ${WHY[e.why] ?? ''}.`.replace(' .', '.');
    case 'card_discarded':
      if (e.why === 'predator_miss') return `${bird(e.bird)} goes to the discard pile.`;
      return `${P(e.p)} discards ${bird(e.bird)} ${WHY[e.why] ?? ''}.`.replace(' .', '.');
    case 'bird_played': return `${bird(e.bird)} lands in ${P(e.p)}'s ${HABITATS[e.habitat]}, column ${e.slot + 1}.`;
    case 'die_taken': return `${P(e.p)} takes a ${faceText(e.face)} die${e.face === 5 ? ` as [${FOODS[e.food]}]` : ''}.`;
    case 'feeder_reset': return `The birdfeeder is refilled (${e.why === 'all_same' ? 'all dice matched' : 'it was empty'}): ${e.dice.map(faceText).join(' ')}.`;
    case 'food_gained': return `${P(e.p)} gains ${e.n} [${FOODS[e.food]}] from the supply.`;
    case 'cards_drawn': {
      const from = { deck: 'from the deck', tray: 'from the tray', draft: 'from the revealed cards' }[e.source] ?? '';
      return `${P(e.p)} draws ${e.birds.map(bird).join(', ')} ${from}.`;
    }
    case 'card_set_aside': return `${P(e.p)} takes ${bird(e.bird)} from the ${e.source} for everyone to pick from.`;
    case 'cards_revealed': return `${P(e.p)} reveals ${e.birds.map(bird).join(', ')}.`;
    case 'card_tucked': return `${P(e.p)} tucks ${e.card != null ? bird(e.card) : 'a card'} from the ${e.source} behind ${bird(e.bird)}.`;
    case 'eggs_laid': return `${P(e.p)} lays ${e.n} [egg] on ${bird(e.bird)}.`;
    case 'food_cached': return `${bird(e.bird)} caches ${e.n} [${FOODS[e.food]}]${e.source === 'player' ? " from the player's food" : ''}.`;
    case 'power': return `${bird(e.bird)}'s ${e.color} power is used${e.repeated_by != null ? ` (repeated by ${bird(e.repeated_by)})` : ''}.`;
    case 'predator':
      if (e.kind === 'roll') return `${bird(e.bird)} hunts: rolls ${e.dice.length ? e.dice.map(faceText).join(' ') : 'no dice'}: ${e.success ? 'success' : 'no luck'}.`;
      return `${bird(e.bird)} hunts: looks at ${bird(e.card)}: ${e.success ? 'caught' : 'too big, discarded'}.`;
    case 'bird_moved': return `${bird(e.bird)} moves from ${P(e.p)}'s ${HABITATS[e.source]} to the ${HABITATS[e.to]}.`;
    case 'tray_cleared': return `End of round: ${e.birds.length ? e.birds.map(bird).join(', ') : 'nothing'} leave${e.birds.length === 1 ? 's' : ''} the bird tray.`;
    case 'tray_refill': return `Bird tray: ${e.tray.map(bird).join(', ') || 'empty'}.`;
    case 'deck_reshuffled': return `The discard pile is shuffled into a new deck of ${plural(e.cards, 'card')}.`;
    case 'round_end': {
      const counts = e.counts.map((c, p) => `${P(p)} ${c}`).join(', ');
      if (e.info && e.info[0] === 'coop') {
        const sign = e.group_delta > 0 ? '+' : '';
        return `Round ${e.round} goal: ${counts}. Difficulty ${e.info[1]}: ${e.info[2] ? 'met' : 'missed'}. Group score ${sign}${fmt(e.group_delta)} (now ${fmt(e.group_score)}).`;
      }
      return `Round ${e.round} goal: ${counts}. Points: ${e.points.map(fmt).join(', ')}.`;
    }
    case 'final_scoring': return 'The game is over. Final scores are in.';
    default: return `${e.e}`;
  }
}

export const fmt = x => (Number.isInteger(x) ? String(x) : (Math.round(x * 100) / 100).toString());

/** Seats an event concerns, for colouring. */
export const eventSeat = e => (typeof e.p === 'number' ? e.p : null);

export { DIE_FACES };
