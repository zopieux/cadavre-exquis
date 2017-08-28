import re

__all__ = ['IRCColors']


class IRCColors:
    """Provide composition of IRC control codes via attribute access.

    Attributes can be a concatenation of up to three parts.
        - A control code (bold, reverse, etc).
        - A foreground color name
        - A background color name

    For instance:
        - "Bold" will toggle bold
        - "BoldRed" will toggle bold and set color to red
        - "BoldGreenRed" will toggle bold, set foreground color to green
           and set background color to red

    The result is a Tag object (a str subclass) that can be used as such
    or called to apply the formatting.

    Note that those are case insensitive and that underscores are ignored.
    """

    COLOR_RE = re.compile(r'\x03\d{0,2}(?:,\d{1,2})?', re.ASCII)

    COLOR_NAMES = dict(
        white='00',
        black='01',
        blue='02',
        green='03',
        red='04',
        brown='05',
        purple='06',
        orange='07',
        yellow='08',
        ltgreen='09',
        teal='10',
        cyan='11',
        ltblue='12',
        pink='13',
        grey='14',
        ltgrey='15',
        default='99',
    )

    CONTROL_CODES = dict(
        bold='\x02',
        color='\x03',
        italic='\x1D',
        underline='\x1F',
        reverse='\x16',
        reset='\x0F'
    )

    TOGGLES = ('bold', 'italic', 'underline', 'reverse')

    class Tag(str):
        def __new__(cls, start, end):
            return str.__new__(cls, start)

        def __init__(self, start, end):
            self.end = end

        def __call__(self, text):
            return self + text + self.end

    def __getattr__(self, tags):
        if tags.startswith('_'):
            raise AttributeError(tags)

        cur_tags = tags.lower().replace('_', '')
        attrs = ''
        colors = []

        for code_name, code in self.CONTROL_CODES.items():
            if cur_tags.startswith(code_name):
                attrs += code
                cur_tags = cur_tags[len(code_name):]
                break

        if not attrs or cur_tags:
            for prefix in ('', ','):
                for color_name, color_code in self.COLOR_NAMES.items():
                    if not cur_tags.startswith(color_name):
                        continue
                    colors.append(prefix + color_code)
                    cur_tags = cur_tags[len(color_name):]
                    break

        if cur_tags:
            print(cur_tags)
            raise AttributeError(tags)

        end = attrs
        for name, code in self.CONTROL_CODES.items():
            if name not in self.TOGGLES:
                end = end.replace(code, '')

        if colors:
            end += self.CONTROL_CODES['color'] + ''.join(
                    c[:-2] + self.COLOR_NAMES['default']
                    for c in colors
            )

            attrs += self.CONTROL_CODES['color'] + ''.join(colors)

        return self.Tag(attrs, end)

    def strip(self, text):
        text = self.COLOR_RE.sub('', text)
        for code in self.CONTROL_CODES.values():
            text = text.replace(code, '')
        return text


IRCColors = IRCColors()
