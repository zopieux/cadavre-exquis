import re
import enum
import time
import copy
import random

import irc3
from irc3.plugins.command import command
from irc3.plugins.cron import cron
from irc3.utils import IrcString

from . import data
from .irc_colors import IRCColors as colors

TRUE_FALSE = (True, False)


class State(enum.IntEnum):
    wait_for_names = enum.auto()
    queue = enum.auto()
    game = enum.auto()
    game_grace_period = enum.auto()
    post_game_cooldown = enum.auto()

    @classmethod
    def game_states(cls):
        return (cls.game, cls.game_grace_period)

    @classmethod
    def non_game_states(cls):
        return (cls.queue, cls.post_game_cooldown)


class PlayTime:
    RE_TIME = re.compile(r'(\d*(?:\.\d+)?)([smh]?)')
    UNITS = dict(s=1, m=60, h=3600)

    def __init__(self, value):
        m = self.RE_TIME.match(value)

        if not m:
            raise ValueError('Invalid time format')

        self.time_unit = m.group(2)
        if self.time_unit:
            self.deadline = time.time() + (
                                float(m.group(1)) * self.UNITS[self.time_unit])
        else:
            self.count = int(m.group(1))

    def count_game(self):
        if not self.time_unit:
            self.count -= 1

    def check_time(self):
        "Returns True if the player is allowed to play now"

        if self.time_unit:
            return time.time() < self.deadline
        else:
            return self.count > 0

    def __repr__(self):
        if not self.time_unit:
            return f'PlayTime(count={self.count})'
        else:
            return f'PlayTime(deadline={self.deadline})'


@irc3.plugin
class Cadavre:
    requires = [
        'irc3.plugins.command',
        'irc3.plugins.userlist'
    ]

    @classmethod
    def reload(cls, old):
        self = cls(old.bot)

        for attr, value in old.__dict__.items():
            if attr == 'bot':
                continue
            setattr(self, attr, copy.deepcopy(value))

        if self.state == State.post_game_cooldown:
            self.waiting_room()
        elif self.state == State.game_grace_period:
            self.announce_game_end()

        return self

    def __init__(self, bot):
        self.channel_name = irc3.utils.as_list(bot.config.autojoins)[0]
        self.bot = bot
        self.state = None
        self.last_game = None
        self.subscribed_players = set()
        self.player_times = {}
        self.reset()

    def connection_made(self):
        self.bot.send('CAP REQ :multi-prefix')

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
        # we are in-game, nick has a role, they did not give their answer
        # TODO: fill-in missing pieces instead
        # or use some non-playing pending player
        if (self.state == State.game
                and nick in self.player_pieces
                and self.player_pieces[nick] not in self.pieces):
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
        if self.state not in State.game_states():
            return
        if target != self.bot.nick:
            return
        if mask.nick not in self.player_pieces:
            return

        piece = self.player_pieces[mask.nick]
        already = piece in self.pieces
        self.pieces[piece] = data

        counter = f"[{len(self.pieces)}/{len(self.player_pieces)}] "

        if not already:
            delay = time.monotonic() - self.start_time
            msg = f"{mask.nick} m'a donné son fragment en {delay:.1f} sec"
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
        self.mode_nick('-v', *(kicked & voiced))

    @command(permission='admin')
    def abort(self, mask, target, args):
        """Abort the game

            %%abort
        """
        if self.state != State.game:
            return
        self.say("partie avortée (noraj thizanne)")
        self.end_game()

    @command(permission='admin')
    def dump(self, mask, target, args):
        """Dump the internal game state

            %%dump
        """
        for name, val in self.__dict__.items():
            self.say(f'{name} = {val!r}', to=mask.nick)

    @command(name='reset', permission='admin')
    def reset_cmd(self, mask, target, args):
        """Reset the game state

            %%reset
        """
        self.reset()
        self.state = State.queue

    @command(permission='admin', use_shlex=False, options_first=True)
    def exec(self, mask, target, args):
        """Exec python code

            %%exec <code>...
        """
        try:
            code = ' '.join(args['<code>'])
            res = eval(code)
            if res is not None:
                return str(res)
        except Exception as ex:
            return colors.bold_red('Exception: ') + str(ex)

    @command(permission='play', aliases=['play'])
    def join(self, mask, target, args):
        """Join the waiting room for the next game(s).

            %%join [<time>]

            <time> can be either the number of games you wish to play or
            a time unit such as '10m' or '1h'.
        """
        if args['<time>']:
            self.player_times[mask.nick] = PlayTime(args['<time>'])
        elif mask.nick in self.player_times:
            del self.player_times[mask.nick]

        if mask.nick in self.pending_players:
            return
        if len(self.pending_players) == max(data.MODES):
            return f"{mask.nick}: nan, y'a déjà trop de joueurs"

        self.pending_players.add(mask.nick)

        if self.state in State.non_game_states():
            if mask.nick not in self.channel.modes['+']:
                self.mode_nick('+v', mask.nick)
            if len(self.pending_players) == max(data.MODES):
                self.start_game()
        elif self.state in State.game_states():
            # in game, defer +v
            return f"{mask.nick}: je note pour la prochaine partie"

    @command(permission='play', aliases=['unplay'])
    def part(self, mask, target, args):
        """Exit from the waiting room

            %%part
        """
        if self.state in State.game_states():
            if mask.nick in self.pending_players:
                self.pending_players.remove(mask.nick)
                return f"{mask.nick}: ok bisous"
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

        delay = time.monotonic() - self.start_time
        msg = f"après {delay:.1f} sec on attend toujours {', '.join(missing)}"
        # invoked by a player that did not answer (such troll lol)
        if nick in missing:
            msg += f" (oui, surtout toi, con de {nick})"
        self.say(msg)

    @command(permission='play')
    def sub(self, mask, target, args):
        """Subscribe to %%summon notifications

            %%sub

        """
        if mask.nick not in self.subscribed_players:
            self.subscribed_players.add(mask.nick)

    @command(permission='play')
    def unsub(self, mask, target, args):
        """Unsubscribe to %%summon notifications

            %%unsub

        """
        if mask.nick in self.subscribed_players:
            self.subscribed_players.remove(mask.nick)

    @command(permission='play')
    def summon(self, mask, target, args):
        """Summon players that have used %%sub

            %%summon
        """
        nicks = self.subscribed_players - {mask.nick}
        if not nicks:
            return

        return f"allô {', '.join(nicks)}, on joue ?"

    @command(permission='play')
    def reveal(self, mask, target, args):
        """Reveal last sentence piece boundaries

            %%reveal
        """
        if not self.last_game:
            return "je n'ai rien dans le sac"

        players, parts = self.last_game
        sentence = data.assemble_sentence(
            parts, colors.underline, data.UNDERLINE)
        self.say(f"dernière phrase par {', '.join(players)}:")
        self.say(f"\N{WHITE RIGHT-POINTING TRIANGLE} {sentence}")

    @cron('* * * * *')
    def check_times(self):
        for player, play_time in self.player_times.items():
            if not play_time.check_time():
                self.part(IrcString(player), None, {})

    def start_game(self):
        self.ensure_state(State.queue)

        subject_gender = random.choice(TRUE_FALSE)
        object_gender = random.choice(TRUE_FALSE)
        subject_plurality = random.choice(TRUE_FALSE)
        object_plurality = random.choice(TRUE_FALSE)

        def gender_name(ge):
            return "masculin" if ge else "féminin"

        def plurality_name(nb):
            return "singulier" if nb else "pluriel"

        def example_idx(gender, plurality):
            return gender * 2 + plurality

        self.players = list(self.pending_players)
        random.shuffle(self.players)

        messages = []
        fragments = []
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

            tune = ''
            if piece == 'V':
                tune = (f" conjugué au {gender_name(gender)} à la 3è personne "
                        f"du {plurality_name(plurality)}")
            elif piece != 'Cc':
                tune = (f" accordé au {gender_name(gender)} "
                        f"{plurality_name(plurality)}")

            msg = (f"donne-moi un {data.PIECES[piece]}{tune} "
                   f"convenant à cette phrase: ")

            fragments.append(example)
            messages.append(msg)

        for i, (player, msg) in enumerate(zip(self.players, messages)):
            def highlight_part(phrase, index):
                phrase = phrase[:]
                phrase[index] = colors.bold_green(phrase[index])
                return ' '.join(phrase)

            msg += highlight_part(fragments, i)
            self.say(msg, to=player)

        people = ", ".join(self.pending_players)
        msg = f"{people}: c'est parti, lisez vos PV pour savoir quoi m'envoyer"
        self.start_time = time.monotonic()
        self.say(msg)
        self.state = State.game

    def enter_grace_period(self):
        self.ensure_state(State.game)
        self.state = State.game_grace_period
        self.bot.loop.call_later(4, self.announce_game_end)

    def announce_game_end(self):
        self.ensure_state(State.game_grace_period)
        parts = [self.pieces[piece] for piece in data.MODES[len(self.pieces)]]
        self.last_game = (list(self.players), list(parts))
        self.say(f"merci à {', '.join(self.players)}:")
        sentence = data.assemble_sentence(parts)
        self.say(f"\N{WHITE RIGHT-POINTING TRIANGLE} {sentence}")
        self.end_game()

    def end_game(self):
        self.ensure_state(*State.game_states())

        for player in set(self.players):
            play_time = self.player_times.get(player)
            if play_time:
                play_time.count_game()

        self.check_times()
        self.state = State.post_game_cooldown

        # voice deferred pending, unvoice deferred leaving
        voiced = set(self.channel.modes['+'])
        self.mode_nick('+v', *(self.pending_players - voiced))
        self.mode_nick('-v', *(voiced - self.pending_players))

        players = self.pending_players.copy()
        self.reset()
        self.pending_players = players

        self.bot.loop.call_later(6, self.waiting_room)

    def waiting_room(self):
        self.ensure_state(State.post_game_cooldown)
        self.state = State.queue
        self.say("on rejoue ?")

