import enum
import random
import time

import irc3
from irc3.plugins.command import command

from . import data

TRUE_FALSE = (True, False)


class State(enum.IntEnum):
    wait_for_names = enum.auto()
    queue = enum.auto()
    game = enum.auto()
    grace_period = enum.auto()
    post_game_cooldown = enum.auto()


@irc3.plugin
class Cadavre:
    @classmethod
    def reload(cls, old):
        return cls(old.bot)

    def __init__(self, bot):
        self.channel_name = bot.config.autojoins[0]
        self.bot = bot
        self.state = None
        self.reset()

    def reset(self):
        self.pending_players = set()
        self.player_pieces = {}
        self.players = []
        self.pieces = {}
        self.start_time = None
        self.blame_users = set()

    def mode_nick(self, mode, *nicks):
        if not nicks:
            return
        sign, mode = mode
        self.bot.mode(self.channel_name, sign + mode * len(nicks), *nicks)

    def ensure_state(self, *states):
        if self.state not in states:
            raise RuntimeError(
                f"expected to be in states {states}, but is {self.state}")

    @property
    def channel(self):
        return self.bot.channels[self.channel_name]

    def say(self, msg, to=None):
        self.bot.privmsg(to or self.channel_name, msg)

    def handle_part(self, nick):
        self.pending_players.discard(nick)
        if self.state == State.game and nick in self.player_pieces:
            self.say(f"gros con de {nick}, on abandonne")
            self.end_game()

    @irc3.event(irc3.rfc.JOIN)
    def on_join(self, mask, channel, **kw):
        if channel == self.channel_name and mask.nick == self.bot.nick:
            self.state = State.wait_for_names

    @irc3.event(irc3.rfc.RPL_ENDOFNAMES)
    def on_endofnames(self, me, channel, **kw):
        if self.state != State.wait_for_names:
            return
        self.pending_players = set(self.channel.modes['+'])
        if self.pending_players:
            self.say(f"hey {', '.join(self.pending_players)}, "
                     f"vous êtes dans la prochaine partie")
        self.state = State.queue

    @irc3.event(irc3.rfc.PART)
    def on_part(self, mask, channel, data):
        if channel == self.channel_name:
            self.handle_part(mask.nick)

    @irc3.event(irc3.rfc.QUIT)
    def on_quit(self, mask, data):
        self.handle_part(mask.nick)

    @irc3.event(irc3.rfc.KICK)
    def on_kick(self, mask, channel, data):
        if channel == self.channel_name:
            self.handle_part(mask.nick)

    @irc3.event(irc3.rfc.PRIVMSG)
    def on_private_message(self, mask, event, target, data):
        if self.state not in (State.game, State.grace_period):
            return
        if target != self.bot.nick:
            return
        if mask.nick not in self.player_pieces:
            return

        piece = self.player_pieces[mask.nick]
        already = piece in self.pieces
        modified = already and self.pieces[piece].lower() != data.lower()
        self.pieces[piece] = data

        counter = f"[{len(self.pieces)}/{len(self.player_pieces)}] "

        if not already:
            delay = time.monotonic() - self.start_time
            msg = f"{mask.nick} m'a donné son fragment en {delay:.1f} sec"
            self.say(counter + msg)
        elif already and modified:
            msg = f"pour info, {mask.nick} a modifié son fragment"
            self.say(counter + msg)

        if len(self.pieces) == len(self.player_pieces):
            self.enter_grace_period()

    @command(permission='admin')
    def kick(self, mask, target, args):
        """Kick player from the queue

            %%kick <nick>...
        """
        kicked = set(args['<nick>'])
        self.pending_players -= kicked
        voiced = set(self.channel.modes['+'])
        self.mode_nick('-v', *(kicked))  # TODO: *(kicked & voiced)

    @command(permission='admin')
    def abort(self, mask, target, args):
        """Abort the game

            %%abort
        """
        if self.state != State.game:
            return
        self.say("partie avortée (noraj thizanne)")
        self.end_game()

    @command(permission='play')
    def join(self, mask, target, args):
        """Join the waiting room for the next game

            %%join
        """
        if self.state != State.queue:
            return
        if len(self.pending_players) == max(data.MODES):
            return "nan, y'a déjà trop de joueurs"
        self.pending_players.add(mask.nick)
        if mask.nick not in self.channel.modes['+']:
            self.mode_nick('+v', mask.nick)
        if len(self.pending_players) == max(data.MODES):
            self.start_game()

    @command(permission='play')
    def part(self, mask, target, args):
        """Exit from the waiting room

            %%part
        """
        if self.state != State.queue:
            return
        self.pending_players.discard(mask.nick)
        if mask.nick in self.channel.modes['+']:
            self.mode_nick('-v', mask.nick)

    @command(permission='play')
    def start(self, mask, target, args):
        """Start a game (if enough players have joined)

            %%start
        """
        if self.state != State.queue:
            return
        if mask.nick not in self.pending_players:
            return
        if len(self.pending_players) < min(data.MODES):
            return "nan, il manque des joueurs"
        self.start_game()

    @command(permission='play')
    def blame(self, mask, target, args):
        """Blame players that have not answered yet

            %%blame
        """
        if self.state != State.game:
            return

        nick = mask.nick
        if nick in self.blame_users:
            return
        self.blame_users.add(nick)

        missing = set(nick for nick, piece in self.player_pieces.items()
                      if piece not in self.pieces)
        if not missing:
            return

        msg = f"on attend toujours {', '.join(missing)}"
        # invoked by a player that did not answer (such troll lol)
        if nick in missing:
            msg += f" (oui, surtout toi, con de {nick})"
        self.say(msg)

    def start_game(self):
        self.ensure_state(State.queue)

        subject_gender = random.choice(TRUE_FALSE)
        object_gender = random.choice(TRUE_FALSE)
        subject_plurality = random.choice(TRUE_FALSE)
        object_plurality = random.choice(TRUE_FALSE)

        gender_name = lambda ge: 'masculin' if ge else 'féminin'
        plurality_name = lambda nb: 'singulier' if nb else 'pluriel'
        example_idx = lambda gender, plurality: gender * 2 + plurality

        self.players = list(self.pending_players)
        random.shuffle(self.players)

        for player, piece in zip(self.players, data.MODES[len(self.players)]):
            self.player_pieces[player] = piece

            examples = data.EXAMPLES[piece]

            if piece == 'Cc':
                gender = None
                plurality = None
                example = random.choice(examples)
            else:
                subject = piece in data.SUBJECT_PIECES
                gender = subject_gender if subject else object_gender
                plurality = subject_plurality if subject else object_plurality
                example = examples[example_idx(gender, plurality)]

            conjug = f'au {gender_name(gender)} {plurality_name(plurality)}'
            if piece == 'V':
                conjug = f'conjugué {conjug}, à la troisième personne'

            msg = (f"donne-moi un {data.PIECES[piece]} {conjug}, "
                   f"par exemple “{example}”")
            self.say(msg, to=player)

        people = ", ".join(self.pending_players)
        msg = f"{people} : c'est parti, lisez vos PV pour savoir quoi m'envoyer"
        self.start_time = time.monotonic()
        self.say(msg)
        self.state = State.game

    def enter_grace_period(self):
        self.ensure_state(State.game)
        self.state = State.grace_period

        def announce_and_end():
            parts = [self.pieces[piece] for piece in
                     data.MODES[len(self.pieces)]]
            self.say(f"merci à {', '.join(self.players)} :")
            sentence = data.assemble_sentence(parts)
            self.say(f"\N{WHITE RIGHT-POINTING TRIANGLE} {sentence}")
            self.end_game()

        self.bot.loop.call_later(4, announce_and_end)

    def end_game(self):
        self.ensure_state(State.game, State.grace_period)
        self.state = State.post_game_cooldown

        players = self.pending_players.copy()
        self.reset()
        self.pending_players = players

        def waiting_room():
            self.ensure_state(State.post_game_cooldown)
            self.state = State.queue
            self.say("on rejoue ?")

        self.bot.loop.call_later(6, waiting_room)