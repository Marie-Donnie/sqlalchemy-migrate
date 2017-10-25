"""
   `CockroachDB`_ database specific implementations of changeset classes.

   .. _`CockroachDB`: http://www.postgresql.org/
"""
from ..databases import postgres

import sqlalchemy
from sqlalchemy.schema import DropConstraint
from sqlalchemy.engine import reflection
from sqlalchemy.databases import postgresql

# ------------------------------------------- CockroachDB Dialects Workaround
# CockroachDB Dialect misses BOOL type name
from cockroachdb.sqlalchemy.dialect import _type_map, CockroachDBDialect
_type_map['bool'] = _type_map['boolean']

class CockroachDDLCompiler(postgresql.PGDDLCompiler):
    # Handle: sqlalchemy.Column(sqlalchemy.ForeignKey())
    def visit_foreign_key_constraint(self, constraint):
        # Only support ON DELETE/UPDATE RESTRICT.
        if constraint.ondelete:
            constraint.ondelete = "RESTRICT"
        if constraint.onupdate:
            constraint.onupdate = "RESTRICT"

        super(CockroachDDLCompiler, self).visit_foreign_key_constraint(constraint)


CockroachDBDialect.ddl_compiler = CockroachDDLCompiler


# -------------------------------------------- Handle migration
class CockroachColumnGenerator(postgres.PGColumnGenerator):
    """CockroachDB column generator implementation.

    ALTER TABLE ... ADD COLUMN
    """
    def add_foreignkey(self, fk):
        from .visitor import get_engine_visitor, run_single_visitor

        tname = fk.table.name
        cnames = map(self.preparer.format_column, fk.columns.values())
        fk.name = "%s_%s_fkey" % (tname, cnames[0])
        fk.__migrate_visit_name__ = 'migrate_foreign_key_constraint'

        engine = fk.table.metadata.bind
        visitor = get_engine_visitor(engine, 'constraintgenerator')
        run_single_visitor(engine, visitor, fk)


class CockroachColumnDropper(postgres.PGColumnDropper):
    """CockroachDB column dropper implementation.


    ALTER TABLE ... DROP COLUMN
    """
    def visit_column(self, column):
        """Drop a column from its table.

        :param column: the column object
        :type column: :class:`sqlalchemy.Column`
        """
        # Drop Constraint First
        from .visitor import get_engine_visitor, run_single_visitor
        engine = column.table.metadata.bind
        visitor = get_engine_visitor(engine, 'constraintdropper')

        for fk in column.foreign_keys:
            fk.__migrate_visit_name__ = 'migrate_foreign_key_constraint'
            run_single_visitor(engine, visitor, fk.constraint)

        if column.primary_key:
            pk = column.table.primary_key
            pk.__migrate_visit_name__ = 'migrate_primary_key_constraint'
            run_single_visitor(engine, visitor, pk)

        # TODO: Drop CHECK/UNIQUE?

        # Proceed
        super(CockroachColumnDropper, self).visit_column(column)


class CockroachSchemaChanger(postgres.PGSchemaChanger):
    """CockroachDB schema changer implementation."""
    pass


class CockroachConstraintGenerator(postgres.PGConstraintGenerator):
    """CockroachDB constraint generator (`create`) implementation.

    The ADD CONSTRAINT statement add Check, Foreign Key and Unique
    constraint to columns.

    See, https://www.cockroachlabs.com/docs/stable/add-constraint.html

    """
    def visit_migrate_primary_key_constraint(self, constraint):
        """Add the Primary Key constraint.

        CockroachDB does not support the add of a Primary Key
        constraint. To implement this migration, first make a new
        temporary table with the new primary key and copy elements of
        the original table. Then drop the original table and rename
        the temporary one.

        """
        # CockroachDB does not support multiple primary keys, so we
        # only consider the last column from the list of pks. Why the
        # last one? why not!
        pk_column = constraint.columns.values()[-1]
        curr_table = constraint.table

        # Build the temporary table
        tmp_columns = [c.copy() for c in curr_table.columns]
        for c in tmp_columns:
            if c.name == pk_column.name:
                c.primary_key = True
            else:
                c.primary_key = False

        tmp_table = sqlalchemy.Table(curr_table.name + '_migrate_tmp',
                                 curr_table.metadata,
                                 *tmp_columns)
        tmp_table.create()

        # Fill the temporary table with the original one
        tmp_table.insert().from_select(
            [c.name for c in curr_table.columns],
            curr_table.select())

        # Remove the original table and rename the temporary one
        tname = self.preparer.format_table(curr_table)
        tmp_tname = self.preparer.format_table(tmp_table)
        self.append("DROP TABLE %s CASCADE" % tname)
        self.execute()
        self.append("ALTER TABLE %s  RENAME to %s" % (tmp_tname, tname))
        self.execute()


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
        self.append("CREATE INDEX cockroach_fk_%s ON %s (%s)" %
                    ('_'.join(cnames), tname, ', '.join(cnames)))
        self.execute()

        # Proceed
        super(CockroachConstraintGenerator, self).visit_migrate_foreign_key_constraint(constraint)

        # Validate the FK constraint
        # See, https://github.com/cockroachdb/docs/issues/990
        self.append("ALTER TABLE %s VALIDATE CONSTRAINT %s" %
                    (tname, constraint.name))
        self.execute()

class CockroachConstraintDropper(postgres.PGConstraintDropper):
    """CockroachDB constraint dropper (`drop`) implementation.

    The DROP CONSTRAINT statement removes Check and Foreign Key
    constraints from columns.

    See,
    https://www.cockroachlabs.com/docs/stable/drop-constraint.html

    """
    @staticmethod
    def _to_index(table):
        def closure(index_name):
            idx = sqlalchemy.Index(index_name)
            idx.table = table
            return idx

        return closure

    def visit_migrate_foreign_key_constraint(self, constraint):
        # First, drop fk
        constraint.cascade = False
        super(CockroachConstraintDropper, self).visit_migrate_foreign_key_constraint(constraint)

        # Then, drop index created in
        # CockroachConstraintGenerator::visit_migrate_foreign_key_constraint
        #
        # Table that has received a FK
        tname = self.preparer.format_table(constraint.table)
        # Columns in the FK (have been indexed)
        cnames = map(self.preparer.format_column, constraint.columns.values())
        # Drop Index
        self.append("DROP INDEX %s@cockroach_fk_%s" %
                    (tname, '_'.join(cnames)))
        self.execute()

    def visit_migrate_primary_key_constraint(self, constraint):
        """Do not drop constraint"""
        pass

    def visit_migrate_unique_constraint(self, constraint):
        """Drop INDEX if the unique constraint is one"""
        # Get indexes on that columns
        insp = reflection.Inspector.from_engine(constraint.table.metadata.bind)
        indexes = set([i['name']
                       for i in insp.get_indexes(constraint.table)
                       for c in i['column_names']
                       if i['unique'] and c in constraint.columns])
        indexes = map(CockroachConstraintDropper._to_index(constraint.table), indexes)

        # Drop index if constraint is one or proceed
        if indexes:
            [i.drop() for i in indexes]
        else:
            super(CockroachConstraintDropper, self).visit_migrate_unique_constraint(constraint)

class CockroachDialect(postgres.PGDialect):
    columngenerator = CockroachColumnGenerator
    columndropper = CockroachColumnDropper
    schemachanger = CockroachSchemaChanger
    constraintgenerator = CockroachConstraintGenerator
    constraintdropper = CockroachConstraintDropper
