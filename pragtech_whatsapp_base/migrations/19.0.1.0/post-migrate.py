from psycopg2 import sql


def _relation_exists(cr, name):
    cr.execute("SELECT to_regclass(%s)", (name,))
    return cr.fetchone()[0] is not None


def migrate(cr, version):
    if not version:
        return

    old_table = "whatsapp_template_button"
    new_table = "whatsapp_templates_button"

    if not _relation_exists(cr, old_table) or _relation_exists(cr, new_table):
        return

    cr.execute(sql.SQL("ALTER TABLE {} RENAME TO {}").format(
        sql.Identifier(old_table),
        sql.Identifier(new_table),
    ))

    old_sequence = f"{old_table}_id_seq"
    new_sequence = f"{new_table}_id_seq"
    if _relation_exists(cr, old_sequence) and not _relation_exists(cr, new_sequence):
        cr.execute(sql.SQL("ALTER SEQUENCE {} RENAME TO {}").format(
            sql.Identifier(old_sequence),
            sql.Identifier(new_sequence),
        ))
        cr.execute(sql.SQL(
            "ALTER TABLE {} ALTER COLUMN id SET DEFAULT nextval({}::regclass)"
        ).format(
            sql.Identifier(new_table),
            sql.Literal(new_sequence),
        ))
