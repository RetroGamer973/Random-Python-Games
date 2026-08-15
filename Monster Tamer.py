#!/usr/bin/env python3
"""
MONSTER TAMER - a Donsol/Scoundrel-style solo card game about
capturing and battling monsters to build up an XP high score.

Runs in a plain terminal - no external dependencies. Designed to
run comfortably on low-power hardware (e.g. Raspberry Pi Zero).

=== HOW IT WORKS ===
Every turn, 4 cards are dealt:
    - 1 or 2 Monster cards      (always at least 1, never more than 2)
    - A Potion card             (1 in 3 chance of appearing)
    - Capture Ball card(s)      (fill whatever slots are left, so
                                  there's always at least one)

Top status bar always shows: XP score, Capture Level, and your
active monster's HP.

MONSTER cards:
    Each monster has an HP (4-18) and a "Capture Level" requirement.
    - To CATCH a monster, your Capture Level must be strictly higher
      than the monster's displayed capture level.
      SPECIAL RULE: on the very first round of a run, every monster
      is catchable regardless of capture level.
    - To BATTLE a monster, you need an active (captured) monster.
      If your active monster's HP is higher than the enemy's HP, you
      win: the enemy is defeated, you gain its XP value, and your
      monster's HP drops by the enemy's HP (e.g. your monster has 10
      HP, the enemy has 5 HP -> you win, your monster ends at 5 HP).
      If your active monster's HP is NOT higher than the enemy's,
      your monster is defeated and removed from your roster. If that
      was your last monster, you DIE: your XP score resets to 0 and
      you start a fresh run.
    If a monster is both catchable and battleable, you choose which
    to do. If neither is possible right now, you can't act on it
    this turn - pick a different card instead.

CAPTURE BALL cards:
    Raise your Capture Level permanently by the amount shown.

POTION cards:
    Heal your active monster's HP by the amount shown (capped at
    that monster's max HP). Does nothing if you have no active
    monster.

Design choices made where the spec was ambiguous (flag if you'd
rather have these different):
    - Only ONE card is resolved per turn; a fresh set of 4 is dealt
      every turn (no carry-over / no deck to exhaust - this is an
      endless score-attack game, matching "xp score is the point").
    - Catching a monster does NOT grant XP by itself - only
      defeating a monster in battle grants its XP.
    - On death, XP resets to 0 AND you lose your monster roster /
      capture level progress, restarting back at "round 1" (where
      everything is catchable again) - a clean fresh run.
    - If you have multiple captured monsters and your active one
      dies, you keep your remaining monsters and just lose the
      active one (pick a new active monster from the menu).
"""

import random
import sys

STARTING_CAPTURE_LEVEL = 1

MONSTER_NAMES = [
    "Slime", "Goblin", "Wolf", "Bat", "Imp", "Suhail", "Wisp",
    "Serpent", "Golem", "Harpy", "Troll", "Wraith", "Drake", "Ogre",
]


def gen_monster():
    hp = random.randint(4, 18)
    # xp scales with hp: weak (hp 4) -> 1xp, strong (hp 18) -> ~6xp,
    # average around 3xp for an average (hp 11) monster.
    xp_value = max(1, round(1 + (hp - 4) / 2.8))
    capture_level = random.randint(1, 10)
    name = random.choice(MONSTER_NAMES)
    return {
        "type": "monster",
        "name": name,
        "hp": hp,
        "max_hp": hp,
        "capture_level": capture_level,
        "xp_value": xp_value,
    }


def gen_potion():
    heal = random.randint(3, 8)
    return {"type": "potion", "heal": heal}


def gen_ball():
    boost = random.randint(1, 3)
    return {"type": "ball", "boost": boost}


def deal_cards():
    num_monsters = random.choice([1, 2])
    has_potion = 1 if random.random() < (1 / 3) else 0
    num_balls = 4 - num_monsters - has_potion

    cards = [gen_monster() for _ in range(num_monsters)]
    if has_potion:
        cards.append(gen_potion())
    cards += [gen_ball() for _ in range(num_balls)]

    random.shuffle(cards)
    return cards


def card_label(card):
    if card["type"] == "monster":
        return (f"{card['name']} - HP {card['hp']}, "
                f"Capture Lvl {card['capture_level']}, "
                f"worth {card['xp_value']} XP")
    if card["type"] == "potion":
        return f"Potion - heals {card['heal']} HP"
    if card["type"] == "ball":
        return f"Capture Ball - +{card['boost']} Capture Level"
    return "???"


class Game:
    def __init__(self):
        self.reset_run()
        self.round_num = 1

    def reset_run(self):
        """Wipe progress after a death - fresh run."""
        self.xp = 0
        self.capture_level = STARTING_CAPTURE_LEVEL
        self.roster = []          # list of monster dicts you own
        self.active_index = None  # index into self.roster
        self.round_num = 1
        self.no_monster_rounds = 0
        self._just_died = True    # so play_turn doesn't skip past round 1

    @property
    def active(self):
        if self.active_index is None or self.active_index >= len(self.roster):
            return None
        return self.roster[self.active_index]

    # ---------- display ----------
    def status_bar(self):
        active = self.active
        if active:
            active_str = f"{active['name']} HP {active['hp']}/{active['max_hp']}"
        else:
            active_str = "(none)"
        return (f"XP: {self.xp}   |   Capture Level: {self.capture_level}   |   "
                f"Active Monster: {active_str}")

    def show_status(self):
        print("\n" + "=" * 60)
        print(self.status_bar())
        if len(self.roster) > 1:
            bench = ", ".join(
                f"{m['name']}({m['hp']}/{m['max_hp']})"
                for i, m in enumerate(self.roster) if i != self.active_index
            )
            print(f"Bench: {bench}")
        if self.active is None and self.no_monster_rounds > 0:
            print(f"WARNING: no active monster for {self.no_monster_rounds} "
                  f"round(s) - lose the run at 2!")
        print("=" * 60)

    def show_room(self, cards):
        print(f"\nRound {self.round_num} - choose a card:")
        for i, c in enumerate(cards, 1):
            tag = ""
            if c["type"] == "monster" and self.round_num == 1:
                tag = "  [catchable - round 1]"
            print(f"  [{i}] {card_label(c)}{tag}")
        if len(self.roster) > 1:
            print("  [s] Switch active monster")
        print("  [q] Quit")

    # ---------- actions ----------
    def switch_active(self):
        print("\nYour monsters:")
        for i, m in enumerate(self.roster):
            marker = " (active)" if i == self.active_index else ""
            print(f"  [{i + 1}] {m['name']} HP {m['hp']}/{m['max_hp']}{marker}")
        choice = input("Switch to which monster? (number, or blank to cancel): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(self.roster):
            self.active_index = int(choice) - 1
            print(f"{self.roster[self.active_index]['name']} is now active.")

    def catch_monster(self, card):
        mon = {
            "type": "monster",
            "name": card["name"],
            "hp": card["hp"],
            "max_hp": card["hp"],
            "capture_level": card["capture_level"],
            "xp_value": card["xp_value"],
        }
        self.roster.append(mon)
        print(f"\nYou caught {mon['name']} (HP {mon['hp']})!")
        if self.active_index is None:
            self.active_index = len(self.roster) - 1
            print(f"{mon['name']} is now your active monster.")

    def battle_monster(self, card):
        active = self.active
        print(f"\n{active['name']} (HP {active['hp']}) battles "
              f"{card['name']} (HP {card['hp']})!")
        if active["hp"] > card["hp"]:
            active["hp"] -= card["hp"]
            self.xp += card["xp_value"]
            print(f"Victory! {active['name']} defeats {card['name']} "
                  f"and takes {card['hp']} damage "
                  f"(now {active['hp']}/{active['max_hp']} HP). "
                  f"+{card['xp_value']} XP!")
        else:
            print(f"Defeat! {active['name']} (HP {active['hp']}) couldn't "
                  f"overcome {card['name']} (HP {card['hp']}) and is lost.")
            del self.roster[self.active_index]
            self.active_index = None
            if self.roster:
                # auto-pick the next monster on the bench so play continues
                self.active_index = 0
                print(f"{self.roster[0]['name']} steps up as your new "
                      f"active monster.")
            else:
                print("\nYou have no monsters left. YOU DIED.")
                print(f"Final XP for this run: {self.xp}")
                self.reset_run()
                print("Your XP has reset to 0. Starting a new run "
                      "(round 1 - everything is catchable again).")

    def resolve_monster(self, card):
        catchable = self.round_num == 1 or self.capture_level > card["capture_level"]
        can_battle = self.active is not None

        if catchable and can_battle:
            choice = input("Catch it [c] or battle it [b]? ").strip().lower()
            if choice.startswith("c"):
                self.catch_monster(card)
            elif choice.startswith("b"):
                self.battle_monster(card)
            else:
                print("Not a valid choice - nothing happens this turn.")
        elif catchable:
            self.catch_monster(card)
        elif can_battle:
            self.battle_monster(card)
        else:
            print(f"\nYour Capture Level ({self.capture_level}) isn't high "
                  f"enough for {card['name']} (needs > "
                  f"{card['capture_level']}), and you have no monster to "
                  f"battle with. You can't act on this card - pick "
                  f"another.")

    def resolve_potion(self, card):
        active = self.active
        if not active:
            print("\nYou have no active monster to heal.")
            return
        before = active["hp"]
        active["hp"] = min(active["max_hp"], active["hp"] + card["heal"])
        healed = active["hp"] - before
        print(f"\n{active['name']} heals {healed} HP "
              f"(now {active['hp']}/{active['max_hp']}).")

    def resolve_ball(self, card):
        self.capture_level += card["boost"]
        print(f"\nCapture Level increased by {card['boost']}! "
              f"Now {self.capture_level}.")

    def resolve(self, card):
        if card["type"] == "monster":
            self.resolve_monster(card)
        elif card["type"] == "potion":
            self.resolve_potion(card)
        elif card["type"] == "ball":
            self.resolve_ball(card)

    # ---------- main loop ----------
    def play_turn(self):
        cards = deal_cards()
        self.show_status()
        self.show_room(cards)

        valid = [str(i) for i in range(1, len(cards) + 1)]
        prompt = f"> "
        choice = input(prompt).strip().lower()

        if choice == "q":
            return False
        if choice == "s" and len(self.roster) > 1:
            self.switch_active()
            return True
        if choice not in valid:
            print("Invalid choice.")
            return True

        card = cards[int(choice) - 1]
        self._just_died = False
        self.resolve(card)
        if self._just_died:
            # a death happened this turn (from a lost battle) and
            # reset_run() already handled it - don't immediately
            # advance past round 1, and don't re-check the
            # no-monster-loss condition on the very turn we reset.
            pass
        else:
            self.round_num += 1
            if self.active is None:
                self.no_monster_rounds += 1
                if self.no_monster_rounds >= 2:
                    print(f"\nYou've gone {self.no_monster_rounds} rounds "
                          f"without a monster. You lose!")
                    print(f"Final XP for this run: {self.xp}")
                    self.reset_run()
                    print("Your XP has reset to 0. Starting a new run "
                          "(round 1 - everything is catchable again).")
            else:
                self.no_monster_rounds = 0
        return True

    def run(self):
        print("=" * 60)
        print(" MONSTER TAMER - catch 'em, battle 'em, chase the high score")
        print("=" * 60)
        print(
            "\nEach turn shows 4 cards: monsters, a chance of a potion, "
            "and capture balls.\nCatch monsters to build your roster, "
            "battle them for XP, heal with potions,\nand raise your "
            "Capture Level with balls so you can catch tougher monsters.\n"
            "Every round 1 of a run, ALL monsters are catchable no matter "
            "your level.\nLose your last monster and you die - XP resets "
            "to 0 and you start over.\n"
        )
        input("Press Enter to begin...")

        playing = True
        while playing:
            playing = self.play_turn()

        print(f"\nThanks for playing! Final XP this run: {self.xp}")


def main():
    try:
        Game().run()
    except (KeyboardInterrupt, EOFError):
        print("\n\nGame interrupted. Bye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
