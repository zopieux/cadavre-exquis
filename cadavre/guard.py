
from irc3.plugins.command import mask_based_policy


class policy(mask_based_policy):
    key = __name__ + '.masks'

    def __call__(self, predicates, meth, client, target, args, **kwargs):
        permission = predicates.get('permission')
        if predicates.get('module') == 'irc3.plugins.command':
            permission = permission or 'admin'
        if args.get('help') or self.has_permission(client, permission):
            return meth(client, target, args)
