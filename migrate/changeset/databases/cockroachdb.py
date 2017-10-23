"""
   `CockroachDB`_ database specific implementations of changeset classes.

   .. _`CockroachDB`: http://www.postgresql.org/
"""
from migrate.changeset.databases import postgres
from sqlalchemy import schema

from operator import attrgetter
from sets import Set



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
    """CockroachDB constraint generator (`create`) implementation.

    See, https://www.cockroachlabs.com/docs/stable/add-constraint.html

    """
    def visit_migrate_foreign_key_constraint(self, constraint):
        """Add the Foreign Key Constraint.

        Note:
        - CockroachDB only support ON DELETE/UPDATE RESTRICT
        - Before you can add the Foreign Key constraint to columns,
          the columns must already be indexed. If they are not already
          indexed, use CREATE INDEX to index them and only then use
          the ADD CONSTRAINT statement to add the Foreign Key
          constraint to the columns.

        See,
        https://www.cockroachlabs.com/docs/stable/add-constraint.html#add-the-foreign-key-constraint
        https://github.com/cockroachdb/cockroach/blob/4d587b1f19582c19b4c44c4fcc2b58efa38a57ed/pkg/sql/parser/sql.y#L2974
        """

        # Only support ON DELETE/UPDATE RESTRICT.
        if constraint.ondelete:
            constraint.ondelete = "RESTRICT"
        if constraint.onupdate:
            constraint.onupdate = "RESTRICT"

        # -- Make index
        # Table that will receive a FK
        tname = self.preparer.format_table(constraint.table)
        # Columns in the FK (have to be indexed)
        cnames = map(self.preparer.format_column, constraint.columns.values())
        # Index
        self.append("CREATE INDEX ON %s (%s)" % (tname, ', '.join(cnames)))
        self.execute()

        # Proceed
        super(CockroachConstraintGenerator, self).visit_migrate_foreign_key_constraint(constraint)

class CockroachConstraintDropper(postgres.PGConstraintDropper):
    """CockroachDB constaint dropper implementation."""
    pass


class CockroachDialect(postgres.PGDialect):
    columngenerator = CockroachColumnGenerator
    columndropper = CockroachColumnDropper
    schemachanger = CockroachSchemaChanger
    constraintgenerator = CockroachConstraintGenerator
    constraintdropper = CockroachConstraintDropper
