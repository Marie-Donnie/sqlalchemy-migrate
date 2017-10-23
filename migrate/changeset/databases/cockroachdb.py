"""
   `CockroachDB`_ database specific implementations of changeset classes.

   .. _`CockroachDB`: http://www.postgresql.org/
"""
from migrate.changeset.databases import postgres

from sqlalchemy import schema

class CockroachColumnGenerator(postgres.PGColumnGenerator):
    """CockroachDB column generator implementation."""
    pass


class CockroachColumnDropper(postgres.PGColumnDropper):
    """CockroachDB column dropper implementation."""
    pass


class CockroachSchemaChanger(postgres.PGSchemaChanger):
    """CockroachDB schema changer implementation."""
    pass


class CockroachConstraintGenerator(postgres.PGConstraintGenerator):
    """CockroachDB constraint generator implementation."""
    pass


class CockroachConstraintDropper(postgres.PGConstraintDropper):
    """CockroachDB constaint dropper implementation."""
    pass


class CockroachDialect(postgres.PGDialect):
    columngenerator = CockroachColumnGenerator
    columndropper = CockroachColumnDropper
    schemachanger = CockroachSchemaChanger
    constraintgenerator = CockroachConstraintGenerator
    constraintdropper = CockroachConstraintDropper
