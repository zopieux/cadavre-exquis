import fnmatch

from irc3.plugins.command import mask_based_policy


class policy(mask_based_policy):
    key = __name__ + '.masks'

    def has_permission(self, mask, predicates):
        permission = predicates.get('permission')
        if predicates.get('module') == 'irc3.plugins.command':
            permission = 'admin'
        if permission is None:
            return True
        for pattern in self.masks:
            if fnmatch.fnmatch(mask, pattern):
                if not isinstance(self.masks, dict):
                    return True
                perms = self.masks[pattern]
                if permission in perms or 'all_permissions' in perms:
                    return True
        return False

    def __call__(self, predicates, meth, client, target, args, **kwargs):
        print(predicates, meth, client, target, args, kwargs)
        if args.get('help') or self.has_permission(client, predicates):
            return meth(client, target, args)
