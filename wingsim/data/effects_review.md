# Effect specs for review

Generated from wingsearch commit `43e5036`. One section per distinct power text (70 texts, 174 birds). Check that each spec does what the printed text says.

## All players draw 1 [card] from the deck.

- Template: `all_draw_deck`
- Birds (5): Canvasback, Northern Shoveler, Purple Gallinule, Spotted Sandpiper, Wilson's Snipe

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "draw_cards",
   "from": "deck",
   "n": 1,
   "who": "all"
  }
 ]
}
```

- Ruling 20201116: Back is a body part for this bonus card, as listed in the European Expansion rulebook ("Anatomist (birds with body parts in their names): back, leg, toe"), so Canvasback counts toward it.
- Ruling 02f: This bird is worth 5 points, not 4. (This misprint was corrected in the third printing, and a corrected card is available in the update pack.)

## All players gain 1 [fish] from the supply.

- Template: `all_gain_supply`
- Birds (1): Osprey

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "gain_food",
   "from": "supply",
   "food": [
    "fish"
   ],
   "n": 1,
   "who": "all"
  }
 ]
}
```

- Ruling 20190416: Powers are optional: the owner of Osprey may choose not to activate its power at all, in which case no player gains a [fish].

## All players gain 1 [fruit] from the supply.

- Template: `all_gain_supply`
- Birds (2): Baltimore Oriole, Black-Chinned Hummingbird

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "gain_food",
   "from": "supply",
   "food": [
    "fruit"
   ],
   "n": 1,
   "who": "all"
  }
 ]
}
```


## All players gain 1 [invertebrate] from the supply.

- Template: `all_gain_supply`
- Birds (2): Eastern Phoebe, Scissor-Tailed Flycatcher

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "gain_food",
   "from": "supply",
   "food": [
    "invertebrate"
   ],
   "n": 1,
   "who": "all"
  }
 ]
}
```


## All players gain 1 [seed] from the supply.

- Template: `all_gain_supply`
- Birds (1): Red Crossbill

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "gain_food",
   "from": "supply",
   "food": [
    "seed"
   ],
   "n": 1,
   "who": "all"
  }
 ]
}
```


## All players lay 1 [egg] on any 1 [bowl] bird. You may lay 1 [egg] on 1 additional [bowl] bird.

- Template: `all_lay_nest_plus_one`
- Birds (1): Lazuli Bunting

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "lay_eggs",
   "n": 1,
   "on": "any",
   "nest": "bowl",
   "who": "all",
   "may_decline": true
  },
  {
   "op": "lay_eggs",
   "n": 1,
   "on": "any",
   "nest": "bowl",
   "who": "self",
   "different_bird": true,
   "may_decline": true
  }
 ]
}
```

- Ruling 20220515: A power may be activated even if its full benefit is not possible; as much of it as possible is implemented. For example, Lazuli Bunting's power may be used even if another player has no [bowl] bird with an empty nest to lay an [egg] on.
- Ruling 20190406: If you use Lazuli Bunting's power to lay 2 [egg], they must be laid on different [bowl]/[star] birds.

## All players lay 1 [egg] on any 1 [cavity] bird. You may lay 1 [egg] on 1 additional [cavity] bird.

- Template: `all_lay_nest_plus_one`
- Birds (1): Pileated Woodpecker

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "lay_eggs",
   "n": 1,
   "on": "any",
   "nest": "cavity",
   "who": "all",
   "may_decline": true
  },
  {
   "op": "lay_eggs",
   "n": 1,
   "on": "any",
   "nest": "cavity",
   "who": "self",
   "different_bird": true,
   "may_decline": true
  }
 ]
}
```

- Ruling 20240604: When Pileated Woodpecker's power is activated, other players may choose not to lay an [egg].
- Ruling 20231126: "May" indicates a binary option: you may do exactly as instructed, or you may not do it at all. It never licenses substituting a different action. On Blue Jay, you may cache the gained [seed] on this bird or keep it in your personal supply, since you have already gained it. On Pileated Woodpecker, you may lay the additional [egg] on a [cavity] bird or lay no additional [egg] at all.
- Ruling 20190406: If you use Pileated Woodpecker's power to lay 2 [egg], they must be laid on different [cavity]/[star] birds.

## All players lay 1 [egg] on any 1 [ground] bird. You may lay 1 [egg] on 1 additional [ground] bird.

- Template: `all_lay_nest_plus_one`
- Birds (1): Western Meadowlark

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "lay_eggs",
   "n": 1,
   "on": "any",
   "nest": "ground",
   "who": "all",
   "may_decline": true
  },
  {
   "op": "lay_eggs",
   "n": 1,
   "on": "any",
   "nest": "ground",
   "who": "self",
   "different_bird": true,
   "may_decline": true
  }
 ]
}
```

- Ruling 20190406: If you use this bird's power to lay 2 [egg], they must be laid on different [ground]/[star] birds.

## Cache 1 [seed] from the supply on this bird.

- Template: `cache_supply`
- Birds (5): Carolina Chickadee, Juniper Titmouse, Mountain Chickadee, Red-Breasted Nuthatch, White-Breasted Nuthatch

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "cache_food",
   "food": "seed",
   "n": 1
  }
 ]
}
```


## Discard 1 [egg] to draw 2 [card].

- Template: `discard_egg_draw`
- Birds (2): Franklin's Gull, Killdeer

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "discard_to_gain",
   "cost": {
    "what": "egg",
    "from": "any_bird"
   },
   "then": [
    {
     "op": "draw_cards",
     "from": "any",
     "n": 2,
     "who": "self"
    }
   ]
  }
 ]
}
```


## Discard 1 [egg] from any of your other birds to gain 1 [wild] from the supply.

- Template: `discard_egg_other_gain_wild`
- Birds (3): American Crow, Black-Crowned Night-Heron, Fish Crow

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "discard_to_gain",
   "cost": {
    "what": "egg",
    "from": "other_birds"
   },
   "then": [
    {
     "op": "gain_food",
     "from": "supply",
     "food": "any",
     "n": 1,
     "who": "self"
    }
   ]
  }
 ]
}
```

- Ruling 20200703: Rodentologist counts only birds with the [rodent] symbol specifically; a [wild] food symbol (e.g., American Crow) does not count.
- Ruling 20191007: For the food cost of played birds end-of-round goal, the clarification to count only 1 food for birds with a choice in their food cost refers to the "/" in food costs. Song Sparrow ([invertebrate]/[seed]/[fruit]) counts as 1, while Fish Crow ([fish]+[wild]) counts as 2.

## Discard 1 [egg] from any of your other birds to gain 2 [wild] from the supply.

- Template: `discard_egg_other_gain_wild`
- Birds (2): Chihuahuan Raven, Common Raven

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "discard_to_gain",
   "cost": {
    "what": "egg",
    "from": "other_birds"
   },
   "then": [
    {
     "op": "gain_food",
     "from": "supply",
     "food": "any",
     "n": 2,
     "who": "self"
    }
   ]
  }
 ]
}
```

- Ruling 20220826: The [wild] symbol always includes [nectar], so Chihuahuan Raven may take [nectar] from the supply with its power. The Oceania rulebook suggests that players who find this too powerful remove Chihuahuan Raven and Common Raven from the deck when playing with the Oceania Expansion.
- Ruling 20201204a: The [wild] ("any food") symbol includes [nectar] among the foods you may choose, but you are never obligated to choose [nectar].
- Ruling 20200623: The 2 [wild] may be two food tokens of the same type or of two different types.

## Discard 1 [fish] to tuck 2 [card] from the deck behind this bird.

- Template: `discard_food_tuck_deck`
- Birds (2): American White Pelican, Double-Crested Cormorant

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "discard_to_gain",
   "cost": {
    "what": "food",
    "food": [
     "fish"
    ]
   },
   "then": [
    {
     "op": "tuck",
     "from": "deck",
     "n": 2
    }
   ]
  }
 ]
}
```

- Ruling 20220213a: You must discard an actual [fish] to activate American White Pelican; food substitutions only apply when playing a bird, not when paying a cost in a bird's power.

## Discard 1 [seed] to tuck 2 [card] from the deck behind this bird.

- Template: `discard_food_tuck_deck`
- Birds (3): Black-Bellied Whistling-Duck, Canada Goose, Sandhill Crane

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "discard_to_gain",
   "cost": {
    "what": "food",
    "food": [
     "seed"
    ]
   },
   "then": [
    {
     "op": "tuck",
     "from": "deck",
     "n": 2
    }
   ]
  }
 ]
}
```

- Ruling 20201010b: Cached food normally cannot be spent, but Eurasian Nuthatch's "at any time" overrides that: a [seed] cached on it may be discarded to pay this power's cost.
- Ruling 20211123: [nectar] cannot be substituted for a specific food type demanded by a bird power; Sandhill Crane's "Discard 1 [seed]" must be paid with [seed].

## Draw 1 [card].

- Template: `draw`
- Birds (1): Mallard

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "draw_cards",
   "from": "any",
   "n": 1,
   "who": "self"
  }
 ]
}
```


## Draw 2 [card].

- Template: `draw`
- Birds (2): Black-Necked Stilt, Carolina Wren

```json
{
 "timing": "white",
 "steps": [
  {
   "op": "draw_cards",
   "from": "any",
   "n": 2,
   "who": "self"
  }
 ]
}
```


## Draw 2 new bonus cards and keep 1.

- Template: `draw_bonus_keep`
- Birds (15): Atlantic Puffin, Bell's Vireo, California Condor, Cassin's Finch, Cerulean Warbler, Chestnut-Collared Longspur, Greater Prairie-Chicken, King Rail, Painted Bunting, Red-Cockaded Woodpecker, Roseate Spoonbill, Spotted Owl, Sprague's Pipit, Whooping Crane, Wood Stork

```json
{
 "timing": "white",
 "steps": [
  {
   "op": "draw_bonus_keep",
   "draw": 2,
   "keep": 1
  }
 ]
}
```

- Ruling 20210130: For end-of-round goals that name two food types in the food cost of your birds, count every icon of either type printed in the food costs of your played birds; a single bird does not need to require both. For example, with 5 [fruit] icons and 8 [seed] icons among your played birds, your number for the goal is 13.
- Ruling 02d: This bird counts toward the Cartographer bonus card: prairie is a qualifying keyword. (Early printings of that bonus card did not list it; the omission was corrected in print by December 2019.)
- Ruling 20240526: "Wood" (singular) in a bird's name is not a geography term for the Cartographer bonus card, so birds such as Wood Stork and woodswallows do not count.

## Draw 1 [card]. If you do, discard 1 [card] from your hand at the end of your turn.

- Template: `draw_discard_end_of_turn`
- Birds (3): Black Tern, Clark's Grebe, Forster's Tern

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "draw_cards",
   "from": "any",
   "n": 1,
   "who": "self",
   "discard_eot": 1
  }
 ]
}
```

- Ruling 20200508: You do not need to reserve a [card] in hand to satisfy Clark's Grebe's power; if you end your turn with no [card] in hand, there is nothing to discard and that is fine.
- Ruling 20240903: The card drawn with Forster's Tern goes into your hand; Great Crested Grebe and Wilson's Storm Petrel work differently, keeping their drawn cards separate from your hand until the end of your turn, when you keep 1 and discard the rest.
- Ruling 20210124: Forster's Tern requires discarding from your hand, so if your hand is empty at the end of your turn (for instance because you tucked all your cards with Common Chiffchaff), you discard nothing.

## Draw 2 [card]. If you do, discard 1 [card] from your hand at the end of your turn.

- Template: `draw_discard_end_of_turn`
- Birds (5): Common Yellowthroat, Pied-Billed Grebe, Red-Breasted Merganser, Ruddy Duck, Wood Duck

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "draw_cards",
   "from": "any",
   "n": 2,
   "who": "self",
   "discard_eot": 1
  }
 ]
}
```

- Ruling 20231204: You do not need to keep a card in hand to discard: if you draw 2 [card] with Wood Duck and then play or tuck your whole hand (for example with Common Chiffchaff), having nothing to discard at the end of your turn is legal.
- Ruling 20210130: For end-of-round goals that name two food types in the food cost of your birds, count every icon of either type printed in the food costs of your played birds; a single bird does not need to require both. For example, with 5 [fruit] icons and 8 [seed] icons among your played birds, your number for the goal is 13.

## Draw the 3 face-up [card] in the bird tray.

- Template: `draw_tray_all`
- Birds (1): Brant

```json
{
 "timing": "white",
 "steps": [
  {
   "op": "draw_cards",
   "from": "tray",
   "n": "all",
   "who": "self"
  }
 ]
}
```


## Each player gains 1 [die] from the birdfeeder, starting with the player of your choice.

- Template: `each_gain_die_in_order`
- Birds (2): Anna's Hummingbird, Ruby-Throated Hummingbird

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "gain_food",
   "from": "feeder",
   "food": "any",
   "n": 1,
   "who": "each_from_feeder_in_order",
   "may_decline": true
  }
 ]
}
```

- Ruling 20200420: Any player may decline to take food from the birdfeeder when this bird's power is activated, and they do not get a second chance during that activation.
- Ruling 20200405a: You may choose yourself as the player who gains food first.
- Ruling 20201002: [nectar] is wild for playing birds and may be spent for any food in a bird's cost, including a single [nectar] to pay a cost of 1 [seed], but cannot be substituted when a bird's power refers to a specific food type.
- Ruling 20230909: "The player of your choice" includes yourself, so you may take the first [die] from the birdfeeder.

## Player(s) with the fewest birds in their [wetland] draw 1 [card].

- Template: `fewest_draw`
- Birds (2): American Bittern, Common Loon

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "draw_cards",
   "from": "any",
   "n": 1,
   "who": "fewest_in_habitat",
   "habitat": "wetland"
  }
 ]
}
```

- Ruling 20200322: American Bittern's power is optional: if activating it would not benefit the player who activated it (for example, if that player does not have the fewest birds in their [wetland]), they may choose not to activate it at all.
- Ruling 20220305: Zero birds counts as the fewest birds, so a player with no birds in their [wetland] can be the player with the fewest birds and draw 1 [card].

## Player(s) with the fewest birds in their [forest] gain 1 [die] from birdfeeder.

- Template: `fewest_gain_die`
- Birds (1): Hermit Thrush

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "gain_food",
   "from": "feeder",
   "food": "any",
   "n": 1,
   "who": "fewest_in_habitat",
   "habitat": "forest"
  }
 ]
}
```

- Ruling 20230412: Zero counts as "fewest": player(s) with no birds in their [forest] gain 1 [die] from the birdfeeder.
- Ruling 20221112: You may decline to activate Hermit Thrush, but if you do activate it, the player(s) with the fewest birds in their [forest] gain their [die] - activating a power is optional, but the whole power then resolves.

## Gain all [fish] that are in the birdfeeder.

- Template: `gain_all_feeder`
- Birds (1): Bald Eagle

```json
{
 "timing": "white",
 "steps": [
  {
   "op": "gain_food",
   "from": "feeder",
   "food": [
    "fish"
   ],
   "n": "all",
   "who": "self"
  }
 ]
}
```


## Gain all [invertebrate] that are in the birdfeeder.

- Template: `gain_all_feeder`
- Birds (1): Northern Flicker

```json
{
 "timing": "white",
 "steps": [
  {
   "op": "gain_food",
   "from": "feeder",
   "food": [
    "invertebrate"
   ],
   "n": "all",
   "who": "self"
  }
 ]
}
```


## Gain 1 [die] from the birdfeeder.

- Template: `gain_die`
- Birds (1): American Redstart

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "gain_food",
   "from": "feeder",
   "food": "any",
   "n": 1,
   "who": "self"
  }
 ]
}
```

- Ruling 20191126b: This bird's power lets you take 1 food from the birdfeeder, as if [wild] were replaced by [die] in the power text.
- Ruling 20191207: This bird does not count toward the Anatomist bonus card.

## Gain 1 [invertebrate] or [fruit] from the birdfeeder, if available.

- Template: `gain_feeder_either_if_available`
- Birds (2): Indigo Bunting, Western Tanager

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "gain_food",
   "from": "feeder",
   "food": [
    "invertebrate",
    "fruit"
   ],
   "n": 1,
   "who": "self"
  }
 ]
}
```

- Ruling 20190117: When using this bird's power, if all [die] in the birdfeeder show the same face you may reroll before taking food.

## Gain 1 [seed] or [fruit] from the birdfeeder, if available.

- Template: `gain_feeder_either_if_available`
- Birds (1): Rose-Breasted Grosbeak

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "gain_food",
   "from": "feeder",
   "food": [
    "seed",
    "fruit"
   ],
   "n": 1,
   "who": "self"
  }
 ]
}
```

- Ruling 20190117: When using this bird's power, if all [die] in the birdfeeder show the same face you may reroll before taking food.

## Gain 1 [invertebrate] from the birdfeeder, if available.

- Template: `gain_feeder_if_available`
- Birds (1): Great Crested Flycatcher

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "gain_food",
   "from": "feeder",
   "food": [
    "invertebrate"
   ],
   "n": 1,
   "who": "self"
  }
 ]
}
```

- Ruling 20190117: When using this bird's power, if all [die] in the birdfeeder show the same face you may reroll before taking food.

## Gain 1 [seed] from the birdfeeder, if available. You may cache it on this bird.

- Template: `gain_feeder_may_cache`
- Birds (6): Acorn Woodpecker, Blue Jay, Clark's Nutcracker, Red-Bellied Woodpecker, Red-Headed Woodpecker, Steller's Jay

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "gain_food",
   "from": "feeder",
   "food": [
    "seed"
   ],
   "n": 1,
   "who": "self",
   "may_cache": true
  }
 ]
}
```

- Ruling 20200423: Once you have chosen whether to cache the [seed] gained with this power or keep it in your personal supply, the choice cannot be changed later.
- Ruling 20231126: "May" is a binary option: do exactly as instructed or not at all, never a substitution. On Blue Jay you may cache the gained [seed] on this bird or keep it in your personal supply, since you have already gained it.
- Ruling 20190901: Caching the [seed] is optional; you may instead keep it as a food token to spend.
- Ruling 20200113: The normal reroll rules apply while you look for the [seed]: if every [die] in the birdfeeder shows the same face you may reroll them all, including when only 1 [die] is left in the birdfeeder.
- Ruling 20210902: The gained [seed] goes to your personal supply unless you choose to cache it on this bird; caching is optional.
- Ruling 20221224: Because caching is optional, you may instead add the [seed] gained with Red-Bellied Woodpecker's power to your personal food supply.
- Ruling 20260818: "May" creates a choice. On Red-Headed Woodpecker, you may decline to cache the [seed] and instead keep it as a normal food resource to spend later.

## Gain 1 [fruit] from the supply.

- Template: `gain_supply`
- Birds (1): Northern Cardinal

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "gain_food",
   "from": "supply",
   "food": [
    "fruit"
   ],
   "n": 1,
   "who": "self"
  }
 ]
}
```


## Gain 1 [invertebrate] from the supply.

- Template: `gain_supply`
- Birds (3): Blue-Gray Gnatcatcher, Painted Whitestart, Yellow-Bellied Sapsucker

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "gain_food",
   "from": "supply",
   "food": [
    "invertebrate"
   ],
   "n": 1,
   "who": "self"
  }
 ]
}
```

- Ruling 20191207: This bird does not count toward the Anatomist bonus card.

## Gain 1 [seed] from the supply.

- Template: `gain_supply`
- Birds (1): Spotted Towhee

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "gain_food",
   "from": "supply",
   "food": [
    "seed"
   ],
   "n": 1,
   "who": "self"
  }
 ]
}
```


## Gain 3 [fish] from the supply.

- Template: `gain_supply`
- Birds (1): Brown Pelican

```json
{
 "timing": "white",
 "steps": [
  {
   "op": "gain_food",
   "from": "supply",
   "food": [
    "fish"
   ],
   "n": 3,
   "who": "self"
  }
 ]
}
```


## Gain 3 [seed] from the supply.

- Template: `gain_supply`
- Birds (1): American Goldfinch

```json
{
 "timing": "white",
 "steps": [
  {
   "op": "gain_food",
   "from": "supply",
   "food": [
    "seed"
   ],
   "n": 3,
   "who": "self"
  }
 ]
}
```


## Lay 1 [egg] on any bird.

- Template: `lay_any`
- Birds (4): Baird's Sparrow, Cassin's Sparrow, Chipping Sparrow, Grasshopper Sparrow

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "lay_eggs",
   "n": 1,
   "on": "any",
   "who": "self"
  }
 ]
}
```


## Lay 1 [egg] on each of your birds with a [bowl] nest.

- Template: `lay_each_nest`
- Birds (1): Say's Phoebe

```json
{
 "timing": "white",
 "steps": [
  {
   "op": "lay_eggs",
   "n": 1,
   "on": "each",
   "nest": "bowl",
   "who": "self"
  }
 ]
}
```


## Lay 1 [egg] on each of your birds with a [cavity] nest.

- Template: `lay_each_nest`
- Birds (1): Ash-Throated Flycatcher

```json
{
 "timing": "white",
 "steps": [
  {
   "op": "lay_eggs",
   "n": 1,
   "on": "each",
   "nest": "cavity",
   "who": "self"
  }
 ]
}
```


## Lay 1 [egg] on each of your birds with a [ground] nest.

- Template: `lay_each_nest`
- Birds (1): Bobolink

```json
{
 "timing": "white",
 "steps": [
  {
   "op": "lay_eggs",
   "n": 1,
   "on": "each",
   "nest": "ground",
   "who": "self"
  }
 ]
}
```


## Lay 1 [egg] on each of your birds with a [platform] nest.

- Template: `lay_each_nest`
- Birds (1): Inca Dove

```json
{
 "timing": "white",
 "steps": [
  {
   "op": "lay_eggs",
   "n": 1,
   "on": "each",
   "nest": "platform",
   "who": "self"
  }
 ]
}
```


## Lay 1 [egg] on this bird.

- Template: `lay_this`
- Birds (4): California Quail, Mourning Dove, Northern Bobwhite, Scaled Quail

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "lay_eggs",
   "n": 1,
   "on": "this",
   "who": "self"
  }
 ]
}
```

- Ruling 20210130: For end-of-round goals that name two food types in the food cost of your birds, count every icon of either type printed in the food costs of your played birds; a single bird does not need to require both. For example, with 5 [fruit] icons and 8 [seed] icons among your played birds, your number for the goal is 13.
- Ruling 20201002: [nectar] is wild for playing birds and may be spent for any food in a bird's cost, including a single [nectar] to pay a cost of 1 [seed]. [nectar] cannot be substituted when a bird's power refers to a specific food type.
- Ruling 20191201: The "white" in Northern Bobwhite counts as a color for the Photographer bonus card.

## Look at a [card] from the deck. If less than 100cm, tuck it behind this bird. If not, discard it.

- Template: `look_at_deck_tuck_if_small`
- Birds (3): Golden Eagle, Great Horned Owl, Peregrine Falcon

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "look_at_deck_card",
   "max_wingspan": 100
  }
 ]
}
```

- Ruling 20220307: When a bird power refers to a characteristic of other birds, only birds currently on your player mat are applicable, not birds in your hand or elsewhere, unless the power specifically says otherwise (such as a power that looks at the top card of the deck). Hooded Merganser therefore repeats the power of a bird with the [predator] icon already played in its habitat, and a bird whose power it repeats may also be activated in its own right during the same turn as the action cube moves along the row.
- Ruling 20200907: When paying a bird's food cost, you may exchange any 2 food tokens to stand in for 1 food of any type you lack. This exchange may be used multiple times in the same payment (e.g., paying 4 [seed] to replace 2 missing foods). The 2-for-1 exchange is only available when playing a bird.
- Ruling 20190729: This bird counts toward the Photographer bonus card.
- Ruling 20201006: Great Horned Owl's beak points straight forward, neither left nor right; the rulebook's list of such birds includes it.

## Look at a [card] from the deck. If less than 50cm, tuck it behind this bird. If not, discard it.

- Template: `look_at_deck_tuck_if_small`
- Birds (1): Greater Roadrunner

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "look_at_deck_card",
   "max_wingspan": 50
  }
 ]
}
```


## Look at a [card] from the deck. If less than 75cm, tuck it behind this bird. If not, discard it.

- Template: `look_at_deck_tuck_if_small`
- Birds (6): Barred Owl, Cooper's Hawk, Northern Harrier, Red-Shouldered Hawk, Red-Tailed Hawk, Swainson's Hawk

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "look_at_deck_card",
   "max_wingspan": 75
  }
 ]
}
```

- Ruling 20190724: This bird does not count toward the Photographer bonus card.
- Ruling 20241222: Red-Tailed Hawk draws from the top of the deck, not from the 3 face-up cards on the bird tray, so its power can always be activated — there will always be cards in the deck.

## If this bird is to the right of all other birds in its habitat, move it to another habitat.

- Template: `move_if_rightmost`
- Birds (8): Bewick's Wren, Blue Grosbeak, Chimney Swift, Common Nighthawk, Lincoln's Sparrow, Song Sparrow, White-Crowned Sparrow, Yellow-Breasted Chat

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "move_bird",
   "if": "rightmost"
  }
 ]
}
```

- Ruling 02a: When using this bird's power to move this bird to another habitat, the action cube does not change habitats with it.
- Ruling 20250319: Common Myna's habitat restriction applies only to where it can be played, not to where it can move, so if it copies Blue Grosbeak's power it may move out of the [grassland].
- Ruling 20200528: Both "beak" and "head" are on the Anatomist list, so birds such as Blue Grosbeak and Loggerhead Shrike count. "Horn" is not on the list, so Horned Lark does not count; follow the printed list strictly, including the additions in the expansion rulebooks.
- Ruling 20221228: Blue Grosbeak's power may be used every time it is activated, as long as no other bird in its habitat is to its right; it may be moved again to a different habitat on a later turn.
- Ruling 20201206b: Habitat restrictions apply only when a bird is played. Afterwards a power such as Chimney Swift's—including when it is copied by Superb Lyrebird or Tūī—may move a bird into a habitat where it could not have been played.
- Ruling 20200104: After this bird moves, you carry on activating the habitat you originally chose—the move does not give you the benefits of the new habitat.
- Ruling 20220521a: This bird may move from any column, including the leftmost one, as long as there are no birds to the right of it in its row (Appendix, page 12).
- Ruling 20191007: For the food cost of played birds end-of-round goal, the clarification to count only 1 food for birds with a choice in their food cost refers to the "/" in food costs. Song Sparrow ([invertebrate]/[seed]/[fruit]) counts as 1, while Fish Crow ([fish]+[wild]) counts as 2.

## Draw [card] equal to the number of players +1. Starting with you and proceeding clockwise, each player selects 1 of those cards and places it in their hand. You keep the extra card.

- Template: `override:draft_players_plus_one`
- Birds (1): American Oystercatcher

```json
{
 "timing": "white",
 "steps": [
  {
   "op": "draft_cards",
   "n": "players_plus_1",
   "from": "any"
  }
 ]
}
```

- Ruling 20200617: You may take the drawn cards from the deck and/or from the bird tray, despite this bird's entry in the Appendix.
- Ruling 20201010: You must draw all X+1 cards as instructed, since some of them are allocated to other players.
- Ruling 20250603: The drawn cards are revealed: players look at them before choosing, rather than selecting blind.
- Ruling 20221123: Unless a power specifies that cards must be drawn from the deck or from the bird tray, you may choose where to draw each [card] from: the face-up cards in the bird tray or the top of the deck. On Indian Peafowl, the additional [card] you draw may come from either source, even though the first 2 [card] must come from the deck.
- Ruling 20190311: In a game against the Automa, draw 3 [card] and keep 2; the Automa is not passed a [card], so the third is discarded.

## When another player takes the “gain food” action, if they gain any number of [rodent], cache 1 [rodent] from the supply on this bird.

- Template: `pink_gain_food_cache`
- Birds (1): Loggerhead Shrike

```json
{
 "timing": "pink",
 "trigger": {
  "on": "on_other_player_gain_food",
  "food": "rodent"
 },
 "steps": [
  {
   "op": "cache_food",
   "food": "rodent",
   "n": 1
  }
 ]
}
```

- Ruling 20190405: Activating a bird's power is not the same as taking the corresponding action. A bird activated by another power that gains [rodent] does not trigger Loggerhead Shrike, because the "gain food" action was not taken; likewise, a bird moved to another habitat by a bird power is not being played, so no [egg] cost is paid for the column it moves into.
- Ruling 20191218: Loggerhead Shrike is not triggered by [rodent] gained from a "when activated" bird power, such as Eastern Screech-Owl's, even when that power fires during another player's "gain food" action.
- Ruling 20260708: Loggerhead Shrike triggers only when another player gains [rodent] as part of the "gain food" core action of the [forest] habitat, not from [rodent] gained or cached by bird powers.

## When another player takes the “lay eggs” action, lay 1 [egg] on a bird with a [bowl] nest.

- Template: `pink_lay_eggs_lay_nest`
- Birds (3): Bronzed Cowbird, Brown-Headed Cowbird, Yellow-Billed Cuckoo

```json
{
 "timing": "pink",
 "trigger": {
  "on": "on_other_player_lay_eggs"
 },
 "steps": [
  {
   "op": "lay_eggs",
   "n": 1,
   "on": "any",
   "nest": "bowl",
   "who": "self"
  }
 ]
}
```

- Ruling 20190718: Bronzed Cowbird has an egg limit of 0 and cannot hold eggs.
- Ruling 20200109b: You may not use this bird's power to lay an [egg] on another player's bird.
- Ruling 20190921: A bird with a [star] nest counts as any and all nest types at all times throughout the game, including for egg-laying powers, bonus cards, and end-of-round goals. A power such as Bronzed Cowbird's that lays 1 [egg] on a bird with a [bowl] nest may lay it on a bird with a [star] nest.
- Ruling 20210107: Brown-Headed Cowbird has no nest type, so it does not count toward the Site Selection Expert bonus card; it is not treated as a [star] nest.
- Ruling 20200411: Powers that trigger when another player takes the "lay eggs" or "gain food" action refer only to those basic actions, not to laying eggs or gaining food from a card power. A card effect that lets a player lay an [egg] or gain food is not the "lay eggs" or "gain food" action.
- Ruling 20200323: Eggs laid by any power are always taken from the general supply and then placed on a bird; they are never moved from another bird.

## When another player takes the “lay eggs” action, lay 1 [egg] on another bird with a [cavity] nest.

- Template: `pink_lay_eggs_lay_other_nest`
- Birds (1): Barrow's Goldeneye

```json
{
 "timing": "pink",
 "trigger": {
  "on": "on_other_player_lay_eggs"
 },
 "steps": [
  {
   "op": "lay_eggs",
   "n": 1,
   "on": "any",
   "nest": "cavity",
   "who": "self",
   "other_than_this": true
  }
 ]
}
```

- Ruling 20200109b: You may not use this bird's power to lay an [egg] on another player's bird.
- Ruling 20190921: A bird with a [star] nest counts as any and all nest types at all times throughout the game, including for egg-laying powers, bonus cards, and end-of-round goals. A power such as Barrow's Goldeneye's that lays 1 [egg] on a bird with a [cavity] nest may lay it on a bird with a [star] nest.
- Ruling 20190729: This bird counts toward the Photographer bonus card.

## When another player takes the “lay eggs” action, lay 1 [egg] on another bird with a [ground] nest.

- Template: `pink_lay_eggs_lay_other_nest`
- Birds (1): American Avocet

```json
{
 "timing": "pink",
 "trigger": {
  "on": "on_other_player_lay_eggs"
 },
 "steps": [
  {
   "op": "lay_eggs",
   "n": 1,
   "on": "any",
   "nest": "ground",
   "who": "self",
   "other_than_this": true
  }
 ]
}
```

- Ruling 20200109b: You may not use this bird's power to lay an [egg] on another player's bird.
- Ruling 20190921: A bird with a [star] nest counts as any and all nest types at all times throughout the game, including for egg-laying powers, bonus cards, and end-of-round goals. A power such as American Avocet's that lays 1 [egg] on a bird with a [ground] nest may lay it on a bird with a [star] nest.

## When another player plays a bird in their [forest], gain 1 [invertebrate] from the supply.

- Template: `pink_play_bird_gain_supply`
- Birds (1): Eastern Kingbird

```json
{
 "timing": "pink",
 "trigger": {
  "on": "on_other_player_play_bird_in",
  "habitat": "forest"
 },
 "steps": [
  {
   "op": "gain_food",
   "from": "supply",
   "food": [
    "invertebrate"
   ],
   "n": 1,
   "who": "self"
  }
 ]
}
```

- Ruling 20200716a: Eastern Kingbird's power triggers whenever another player plays a bird in their [forest] on their turn, even without using the "play a bird" action (e.g. via Goldcrest's power), despite this bird's Appendix entry.
- Ruling 20200710: Playing a bird is not the same as activating a bird. This bird's power is not triggered when another player moves an existing bird into their [forest]; only when a new bird is played there.

## When another player plays a bird in their [wetland], gain 1 [fish] from the supply.

- Template: `pink_play_bird_gain_supply`
- Birds (1): Belted Kingfisher

```json
{
 "timing": "pink",
 "trigger": {
  "on": "on_other_player_play_bird_in",
  "habitat": "wetland"
 },
 "steps": [
  {
   "op": "gain_food",
   "from": "supply",
   "food": [
    "fish"
   ],
   "n": 1,
   "who": "self"
  }
 ]
}
```

- Ruling 20200716a: This bird's power is triggered by another player playing a bird in their [wetland] during their turn, even when not using the "play a bird" card action to do so (instead using, e.g., the Common Moorhen's power), despite this bird's entry in the Appendix.

## When another player plays a bird in their [grassland], tuck 1 [card] from your hand behind this bird.

- Template: `pink_play_bird_tuck`
- Birds (1): Horned Lark

```json
{
 "timing": "pink",
 "trigger": {
  "on": "on_other_player_play_bird_in",
  "habitat": "grassland"
 },
 "steps": [
  {
   "op": "tuck",
   "from": "hand",
   "n": 1
  }
 ]
}
```

- Ruling 20240714a: Playing Red Kite on top of another bird in a player's [grassland] still counts as playing a bird in that habitat, so it triggers Horned Lark.
- Ruling 20200528: "Horn" is not on the Anatomist list, so Horned Lark does not count; follow the printed list strictly, including the additions in the expansion rulebooks. ("Beak" and "head" are on the list, so birds such as Blue Grosbeak and Loggerhead Shrike count.)
- Ruling 20200405: This bird counts toward the Bird Counter bonus card despite the specification of brown powers in that bonus card's entry in the Appendix.
- Ruling 20200204a: A pink power activates directly after the action that triggered it, once the triggering player has finished all the actions on the card that caused it. The player with the pink power completes it before the original player continues activating any further birds in their row.

## When another player's [predator] succeeds, gain 1 [die] from the birdfeeder.

- Template: `pink_predator_gain_die`
- Birds (3): Black Vulture, Black-Billed Magpie, Turkey Vulture

```json
{
 "timing": "pink",
 "trigger": {
  "on": "on_other_player_predator_success"
 },
 "steps": [
  {
   "op": "gain_food",
   "from": "feeder",
   "food": "any",
   "n": 1,
   "who": "self"
  }
 ]
}
```

- Ruling 20231229: A [predator] power "succeeds" when its element of chance produces the result it is looking for (for example, looking at the top card of the deck and finding a bird with a small enough wingspan to tuck). Black Vulture's power triggers whenever another player's [predator] finds what it is looking for.
- Ruling 20220209: Activate this power immediately when another player's [predator] succeeds, not at the end of that player's turn.
- Ruling 20231030: When more than one player's "once between turns" power is triggered at the same time, they resolve in turn order starting with the player after the active player. Black Vulture, Black-Billed Magpie and Turkey Vulture are all triggered and activated as soon as the successful [predator] finishes its power, before the active player continues to their next bird.
- Ruling 20201203a: If another player activates Laughing Kookaburra's [predator] power and it succeeds (they gain a food), Black-Billed Magpie's power triggers and you gain 1 [die] from the birdfeeder.
- Ruling 20210321: Black-Billed Magpie is not a predator bird and does not count for the Falconer bonus card; a bird is a predator only if it has the [predator] icon before its power text.
- Ruling 20240115: When a power is copied, the whole power including its label transfers to the copying bird. A bird such as Tūī that copies a [predator] power therefore has a [predator] power while it activates it, and its success triggers Black-Billed Magpie.
- Ruling 20211023: Turkey Vulture is not a [predator] bird; its [predator] symbol appears within the power text rather than before it. A predator "succeeds" when another player's [predator] power results in that player gaining a benefit - for example, revealing a card whose wingspan is less than the stated value and tucking it.
- Ruling 20200522: A [predator] "succeeds" when its action is successful, not when the bird is played - usually meaning it caches a food or tucks a card. If a bird such as Northern Goshawk uses its power to tuck cards instead of paying some or all of its food cost, that counts as both tucking a card and a [predator] succeeding, and triggers pink powers accordingly.
- Ruling 20210104: Gaining food from the birdfeeder with the Sacred Kingfisher's power counts as a successful [predator] action, so it can trigger Turkey Vulture. It cannot trigger the pink power of the player whose turn it is, because the Sacred Kingfisher's power resolves as the final step of that player's turn, not between turns.
- Ruling 20200204a: A pink power activates directly after the action that triggered it, once the triggering player has finished all the actions on the card that caused it. The player with the pink power completes it before the original player continues activating any further birds in their row.
- Ruling 20200331: "Turkey" does not count as a geography term for the Cartographer bonus card, and neither does "turkey vulture" (turkey vultures are named after the bird, not the country).

## Play an additional bird in your [forest]. Pay its normal cost.

- Template: `play_additional_in_habitat`
- Birds (4): Downy Woodpecker, Red-Eyed Vireo, Ruby-Crowned Kinglet, Tufted Titmouse

```json
{
 "timing": "white",
 "steps": [
  {
   "op": "play_additional_bird",
   "habitat": "forest"
  }
 ]
}
```

- Ruling 20190309: If you use this bird's power to play another bird with a "play a second bird" power, you may then use the latter bird's power to play yet another bird. Pay each bird's printed food cost and the [egg] cost at the top of the column it is placed in.
- Ruling 20201230: The "normal cost" includes any [egg] required by the column the additional bird is placed in, even if you already paid [egg] to play a bird this turn.
- Ruling 20260128: Food cached on this bird may only be spent on the cost of a bird power, not on the cost of playing a bird – including a bird played via another bird's power, such as Tufted Titmouse.

## Play an additional bird in your [grassland]. Pay its normal cost.

- Template: `play_additional_in_habitat`
- Birds (3): Eastern Bluebird, Mountain Bluebird, Savannah Sparrow

```json
{
 "timing": "white",
 "steps": [
  {
   "op": "play_additional_bird",
   "habitat": "grassland"
  }
 ]
}
```

- Ruling 20190309: If you use this bird's power to play another bird with a "play a second bird" power, you may then use the latter bird's power to play yet another bird. Pay each bird's printed food cost and the [egg] cost at the top of the column it is placed in.

## Play an additional bird in your [wetland]. Pay its normal cost.

- Template: `play_additional_in_habitat`
- Birds (2): Great Blue Heron, Great Egret

```json
{
 "timing": "white",
 "steps": [
  {
   "op": "play_additional_bird",
   "habitat": "wetland"
  }
 ]
}
```

- Ruling 20190309: If you use this bird's power to play another bird with a "play a second bird" power, you may then use the latter bird's power to play yet another bird. Pay each bird's printed food cost and the [egg] cost at the top of the column it is placed in.

## Play an additional bird in this bird's habitat. Pay its normal cost.

- Template: `play_additional_same_habitat`
- Birds (1): House Wren

```json
{
 "timing": "white",
 "steps": [
  {
   "op": "play_additional_bird",
   "habitat": "this"
  }
 ]
}
```

- Ruling 20190309: If you use House Wren's power to play another bird with a "play a second bird" power, you may then use the latter bird's power to play yet another bird. Pay each bird's printed food cost and the [egg] cost at the top of the column it is placed in.
- Ruling 20190128: The additional bird must be played in the same habitat as House Wren. Because the power says a "second" bird, it looks at the first bird, so even though House Wren itself may be played in either of two habitats, both birds go in the same one.

## Repeat a brown power on another bird in this habitat.

- Template: `repeat_brown`
- Birds (2): Gray Catbird, Northern Mockingbird

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "repeat_power",
   "filter": "brown"
  }
 ]
}
```

- Ruling 20210199a: When Gray Catbird repeats the power of a bird with a "copy" power (e.g., the Superb Lyrebird), it repeats the copying power printed on that bird and not any powers that bird copied earlier in the turn.
- Ruling 20190127: Gray Catbird may repeat the brown power of any bird in the habitat, whether it is to the left or right.
- Ruling 20260319: A "repeat" power makes the other bird's power trigger again on that bird itself; it is not a copy performed by this bird. If the repeated power's condition is no longer met for that bird—for example, a bird that must be the rightmost in its habitat is no longer at the right edge—the repeated power simply fizzles.
- Ruling 20200108: This bird does not take on the other bird's power; that bird repeats its own power as if it were activated again. [card] tucked by a repeated tucking power (e.g., Barn Swallow) go behind that bird, and any food or [egg] cost is paid as that bird's power specifies (e.g., Chihuahuan Raven still requires discarding 1 [egg] from one of your other birds). A bird that gains tucked [card] this way does not gain a [flocking] power, but does count toward Citizen Scientist.
- Ruling 20190307: This bird can only repeat the power of a bird that is currently in the same habitat. If a bird has already used a "move this bird to another habitat" power and left, it can no longer be repeated here; repeat its power first and it may then move.
- Ruling 20240110: Copy powers act as if the copied text were printed on the copying bird. So if Superb Lyrebird copies the Northern Mockingbird's power, you then repeat a brown power on another bird in Superb Lyrebird's own habitat ([forest]).

## Repeat 1 [predator] power in this habitat.

- Template: `repeat_predator`
- Birds (1): Hooded Merganser

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "repeat_power",
   "filter": "predator"
  }
 ]
}
```

- Ruling 20210199a: Hooded Merganser cannot copy the power of a bird with a "copy" power that is not a predator power, even if that bird copied a predator power earlier in the turn.
- Ruling 20220307: When a bird power refers to a characteristic of other birds, only birds currently on your player mat are applicable, not birds in your hand or elsewhere, unless the power specifically says otherwise (such as a power that looks at the top card of the deck). Hooded Merganser therefore repeats the power of a bird with the [predator] icon already played in its habitat, and a bird whose power it repeats may also be activated in its own right during the same turn as the action cube moves along the row.
- Ruling 20190127: Hooded Merganser activates another bird's brown power, and it may activate a bird's power regardless of whether that bird is to the left or right of it.
- Ruling 20260111: Hooded Merganser's power is activated as a brown power, so it can only repeat another brown power – specifically a [predator] power – and the repeated bird must be in the same habitat.

## Roll all dice not in birdfeeder. If any are [fish], cache 1 [fish] from the supply on this bird.

- Template: `roll_dice_cache`
- Birds (6): Anhinga, Black Skimmer, Common Merganser, Snowy Egret, White-Faced Ibis, Willet

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "roll_dice_not_in_feeder",
   "food": "fish",
   "then": [
    {
     "op": "cache_food",
     "food": "fish",
     "n": 1
    }
   ]
  }
 ]
}
```


## Roll all dice not in birdfeeder. If any are [rodent], cache 1 [rodent] from the supply on this bird.

- Template: `roll_dice_cache`
- Birds (7): American Kestrel, Barn Owl, Broad-Winged Hawk, Burrowing Owl, Eastern Screech-Owl, Ferruginous Hawk, Mississippi Kite

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "roll_dice_not_in_feeder",
   "food": "rodent",
   "then": [
    {
     "op": "cache_food",
     "food": "rodent",
     "n": 1
    }
   ]
  }
 ]
}
```

- Ruling 20190522: This bird does not count toward the Anatomist bonus card.
- Ruling 20191218: Food gained from a "when activated" power such as Eastern Screech-Owl's does not trigger Loggerhead Shrike, which refers only to the core benefit of the "gain food" action.
- Ruling 20210327: Eastern Screech-Owl's beak does not point in either direction, so it counts for neither the beaks pointing left nor the beaks pointing right end-of-round goal. (This is listed on page 11 of the Oceania rules.)

## Trade 1 [wild] for any other type from the supply.

- Template: `trade_food`
- Birds (1): Green Heron

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "discard_to_gain",
   "cost": {
    "what": "food",
    "food": "any"
   },
   "then": [
    {
     "op": "gain_food",
     "from": "supply",
     "food": "any_other",
     "n": 1,
     "who": "self"
    }
   ]
  }
 ]
}
```

- Ruling 20230621: [nectar] is an eligible food type for Green Heron's power, so you may trade 1 [wild] for [nectar] from the supply. (An earlier official answer saying nectar was ineligible was retracted.)
- Ruling 20220509: When another player uses Green Heron's power to trade a food token for [nectar], that counts as gaining [nectar], so Spangled Drongo's power triggers. It is not a net gain of food, but it is still a gain. Spangled Drongo is a "once between turns" power, so it may only be used once between each of your turns.
- Ruling 20230101: Food traded away with Green Heron goes back to the supply, not to the birdfeeder; [nectar] traded away is spent instead, so place it in the spent-nectar space of your player mat.
- Ruling 20200712: "Trading" counts as "spending".
- Ruling 20200719: You may not use this bird's power to trade a food token for a food token of the same type.

## Tuck 1 [card] from your hand behind this bird. If you do, draw 1 [card].

- Template: `tuck_hand_then_draw`
- Birds (9): American Coot, American Robin, Barn Swallow, House Finch, Purple Martin, Ring-Billed Gull, Tree Swallow, Violet-Green Swallow, Yellow-Rumped Warbler

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "if_then",
   "if": {
    "op": "tuck",
    "from": "hand",
    "n": 1
   },
   "then": [
    {
     "op": "draw_cards",
     "from": "any",
     "n": 1,
     "who": "self"
    }
   ]
  }
 ]
}
```

- Ruling 20191203c: Violet is a qualifying keyword for the Photographer bonus card, though Violet-Green Swallow also contains green, so it counts either way.

## Tuck 1 [card] from your hand behind this bird. If you do, gain 1 [fruit] from the supply.

- Template: `tuck_hand_then_gain`
- Birds (1): Cedar Waxwing

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "if_then",
   "if": {
    "op": "tuck",
    "from": "hand",
    "n": 1
   },
   "then": [
    {
     "op": "gain_food",
     "from": "supply",
     "food": [
      "fruit"
     ],
     "n": 1,
     "who": "self"
    }
   ]
  }
 ]
}
```


## Tuck 1 [card] from your hand behind this bird. If you do, gain 1 [invertebrate] from the supply.

- Template: `tuck_hand_then_gain`
- Birds (1): Vaux's Swift

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "if_then",
   "if": {
    "op": "tuck",
    "from": "hand",
    "n": 1
   },
   "then": [
    {
     "op": "gain_food",
     "from": "supply",
     "food": [
      "invertebrate"
     ],
     "n": 1,
     "who": "self"
    }
   ]
  }
 ]
}
```


## Tuck 1 [card] from your hand behind this bird. If you do, gain 1 [seed] from the supply.

- Template: `tuck_hand_then_gain`
- Birds (2): Dark-Eyed Junco, Pine Siskin

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "if_then",
   "if": {
    "op": "tuck",
    "from": "hand",
    "n": 1
   },
   "then": [
    {
     "op": "gain_food",
     "from": "supply",
     "food": [
      "seed"
     ],
     "n": 1,
     "who": "self"
    }
   ]
  }
 ]
}
```


## Tuck 1 [card] from your hand behind this bird. If you do, gain 1 [invertebrate] or [seed] from the supply.

- Template: `tuck_hand_then_gain_either`
- Birds (1): Pygmy Nuthatch

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "if_then",
   "if": {
    "op": "tuck",
    "from": "hand",
    "n": 1
   },
   "then": [
    {
     "op": "gain_food",
     "from": "supply",
     "food": [
      "invertebrate",
      "seed"
     ],
     "n": 1,
     "who": "self"
    }
   ]
  }
 ]
}
```


## Tuck 1 [card] from your hand behind this bird. If you do, lay 1 [egg] on any bird.

- Template: `tuck_hand_then_lay_any`
- Birds (1): White-Throated Swift

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "if_then",
   "if": {
    "op": "tuck",
    "from": "hand",
    "n": 1
   },
   "then": [
    {
     "op": "lay_eggs",
     "n": 1,
     "on": "any",
     "who": "self"
    }
   ]
  }
 ]
}
```


## Tuck 1 [card] from your hand behind this bird. If you do, you may also lay 1 [egg] on this bird.

- Template: `tuck_hand_then_may_lay_this`
- Birds (6): Brewer's Blackbird, Bushtit, Common Grackle, Dickcissel, Red-Winged Blackbird, Yellow-Headed Blackbird

```json
{
 "timing": "brown",
 "steps": [
  {
   "op": "if_then",
   "if": {
    "op": "tuck",
    "from": "hand",
    "n": 1
   },
   "then": [
    {
     "op": "lay_eggs",
     "n": 1,
     "on": "this",
     "who": "self",
     "optional": true
    }
   ]
  }
 ]
}
```

- Ruling 20190203: If this bird already has the maximum number of [egg] on it, you may still use its power to tuck a [card]; you simply cannot lay the [egg].
- Ruling 20201020b: Bushtit does not officially count toward the Anatomist bonus card, though some groups house-rule otherwise.
- Ruling 20231204: A [card] drawn with Wilson's Storm Petrel or Great Crested Grebe may not be tucked with Common Grackle. Those [card] are kept separate from your hand and cannot be spent during the turn in which they were drawn (Appendix).
