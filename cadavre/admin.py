from irc3.plugins.command import command


@command(permission='admin')
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
