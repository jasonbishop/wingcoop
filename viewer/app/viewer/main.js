// The replay viewer page: open a log, put it on the table, wire up the controls.
//
// URL parameters:
//   ?log=<path>     open a log the dev server lists (e.g. docs/samples/coop-3p-greedy-every-decision.jsonl.gz)
//   &at=<n>         start at position n (0 = before the first decision)
//   &quality=low    lighter shadows and card textures

import { tweens } from '../../components/tabletop/src/index.js';
import { GameTable } from './scene/GameTable.js';
import { ReplayPlayer } from './player.js';
import { loadFile, loadPath } from './replay/load.js';
import { Hud } from './ui/hud.js';
import { Home } from './ui/home.js';

const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);

let session = null;   // { replay, game, player, hud }

const home = new Home({
  onFile: file => open(() => loadFile(file), null),
  onPath: path => open(() => loadPath(path), path),
});

async function open(load, path) {
  home.busy('Opening…');
  let replay;
  try {
    replay = await load();
  } catch (err) {
    console.error(err);
    home.busy(null);
    await home.show({ canClose: !!session });
    home.error(err.message || String(err));
    return;
  }
  home.busy(null);
  start(replay, path);
}

function start(replay, path) {
  if (session) {
    session.player.pause();
    session.hud.dispose();
    session.game.dispose();
    session = null;
  }
  $('app').hidden = false;
  home.hide();
  $('loading').hidden = false;

  const game = new GameTable({ container: $('table'), replay, quality: params.get('quality') === 'low' ? 'low' : 'high' });
  const player = new ReplayPlayer(replay, game);
  const at = Number(params.get('at'));
  if (path && path === params.get('log') && at > 0) player.goto(at);
  const hud = new Hud(replay, player, game);
  session = { replay, game, player, hud };
  window.viewer = { ...session, tweens };   // poke at it from the console
  game.ready.then(() => { if (session?.game === game) $('loading').hidden = true; });

  // keep the address bar pointing at this game and position, so a reload comes back here
  const url = new URL(location.href);
  if (path) url.searchParams.set('log', path); else url.searchParams.delete('log');
  url.searchParams.delete('at');
  history.replaceState(null, '', url);
  let timer = null;
  player.addEventListener('position', () => {
    if (!path) return;
    clearTimeout(timer);
    timer = setTimeout(() => {
      const u = new URL(location.href);
      if (player.index > 0) u.searchParams.set('at', String(player.index)); else u.searchParams.delete('at');
      history.replaceState(null, '', u);
    }, 400);
  });
}

$('open').addEventListener('click', () => {
  session?.player.pause();
  home.show({ canClose: !!session });
});

if (params.get('log')) open(() => loadPath(params.get('log')), params.get('log'));
else home.show();
