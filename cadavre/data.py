PIECES = {
    'S': "sujet",
    'Se': "attribut du sujet",
    'V': "verbe",
    'C': "complément d'objet",
    'Ce': "attribut du complément d'objet",
    'Cc': "complément circonstentiel (temps, lieu, manière, cause, …)",
}

SUBJECT_PIECES = ('S', 'Se', 'V')

EXAMPLES = {
    'S': ["les sorcières", "la voisine", "les hommes", "le pape"],
    'Se': ["chamboulées", "toute jaune", "terrifiés", "confiant"],
    'V': ["sont amusées par", "est émue par", "s'amusent avec", "parle avec"],
    'C': ["les sorcières", "la voisine", "les hommes", "le pape"],
    'Ce': ["chamboulées", "toute jaune", "terrifiés", "confiant"],
    'Cc': ["près du lampadaire", "la veille de Noël", "sans bouger"],
}

MODES = {
    3: ['S', 'V', 'C'],
    4: ['S', 'Se', 'V', 'C'],
    5: ['S', 'Se', 'V', 'C', 'Ce'],
    6: ['S', 'Se', 'V', 'C', 'Ce', 'Cc'],
}

LIGATURES = {
    ("à", "le"): "au",
    ("à", "les"): "aux",
    ("de", "le"): "du",
    ("de", "les"): "des",
    ("de", "un"): "d'un",
    ("de", "une"): "d'une",
    ("de", "des"): "des",
}


def assemble_sentence(parts, colors=True):
    """
    Assemble parts and try to keep it French.

    >>> assemble_sentence(['meuf à', 'le voisin'])
    'Meuf au voisin.'
    >>> assemble_sentence(['meuf à', 'la voisine'])
    'Meuf à la voisine.'
    >>> assemble_sentence(['meuf à', 'les voisins'])
    'Meuf aux voisins.'
    >>> assemble_sentence(['meuf à', 'mes voisins'])
    'Meuf à mes voisins.'
    >>> assemble_sentence(['meuf de', 'le voisin'])
    'Meuf du voisin.'
    >>> assemble_sentence(['meuf de', 'la voisine'])
    'Meuf de la voisine.'
    >>> assemble_sentence(['meuf de', 'les voisins'])
    'Meuf des voisins.'
    >>> assemble_sentence(['meuf de', 'mon fils'])
    'Meuf de mon fils.'
    >>> assemble_sentence(['meuf de', 'un voisin'])
    "Meuf d'un voisin."
    >>> assemble_sentence(['meuf de', 'une nana'])
    "Meuf d'une nana."
    >>> assemble_sentence(['meuf de', 'des voisins'])
    'Meuf des voisins.'
    >>> assemble_sentence(['meuf que', ', en bon prince, il nique'])
    'Meuf que, en bon prince, il nique.'
    >>> assemble_sentence(['meuf que, moi,', ', en bon prince, je nique'])
    'Meuf que, moi, en bon prince, je nique.'
    >>> assemble_sentence(['meuf que', 'il nique'])
    "Meuf qu'il nique."
    >>> assemble_sentence(['meuf QUE', 'il nique'])
    "Meuf QU'il nique."
    >>> assemble_sentence(['meuf que', 'elle nique'])
    "Meuf qu'elle nique."
    >>> assemble_sentence(['meuf que', 'on baise'])
    "Meuf qu'on baise."
    >>> assemble_sentence(['meuf que', 'Aristote démonte'])
    "Meuf qu'Aristote démonte."
    >>> assemble_sentence(['meuf que', 'Ursule encule'])
    "Meuf qu'Ursule encule."
    """
    parts = parts[:]
    result = ""

    def ligature(part):
        nonlocal result
        for (left, right), replace in LIGATURES.items():
            if (result.lower().endswith(" " + left) and
                    part.lower().startswith(right + " ")):
                result = " ".join(
                    (result[:-len(left) - 1], replace, part[len(right) + 1:]))
                return True
            if result.lower().endswith(" que") and part[0].lower() in 'aeiou':
                result = result[:-1] + "'" + part
                return True
        return False

    for i, part in enumerate(parts):
        part = part.strip()
        if i == 0:
            result += part[0].upper() + part[1:]
        elif result.endswith(",") and part.startswith(","):
            result += " " + part[1:].strip() + " "
        elif ligature(part):
            continue
        elif not part.startswith(","):
            result += " " + part
        else:
            result += part

    return result.strip() + "."
