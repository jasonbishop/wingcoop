"""Table talk: messages the players say to each other, outside the game rules.

One TableTalk is shared by the seats of a game that talk (members); seats that do not
talk (bots) neither post nor read. A message is said once, at the speaker's action
decision, and every member sees the recent ones in later prompts. A person at the
table could post here too.
"""


class TableTalk:
    def __init__(self, members=()):
        self.members = sorted(members)    # seats that read and speak
        self.messages = []                # {"round", "turn_no", "player", "text"}, oldest first

    def post(self, round_no, turn_no, player, text):
        self.messages.append({"round": round_no, "turn_no": turn_no, "player": player, "text": text})

    def recent(self, n):
        return self.messages[-n:]
