from irc3.plugins.command import command


@command(permission='admin', use_shlex=False, options_first=True)
def dispatch(bot, mask, target, args):
    """Fake some input
        %%dispatch <data>...
    """

    line = ' '.join(args['<data>'])
    bot.dispatch(line)


@command(permission='admin')
def reload(bot, mask, target, args):
    """Reload plugins

        %%reload
    """
    bot.reload()
    return 'Reloaded'


@command(name='as', permission='admin', options_first=True)
def as_cmd(bot, mask, target, args):
    """Simulate a message from another nick

        %%as <nick> <message>...
    """
    nick = args['<nick>']
    message = ' '.join(args['<message>'])

    bot.dispatch(f':{nick}!{nick}@{nick} PRIVMSG {bot.nick} :{message}')
