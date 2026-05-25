# Alembic Migration Guide for E-Library

## Setup

### 1. Install Alembic (if not already installed)
```bash
pip install alembic
```

### 2. Ensure Database URL is in .env
```env
DATABASE_URL=postgresql+psycopg://postgres:juan@localhost:5432/elibrary_db
```

---

## Running Migrations

### Option 1: Using the Helper Script (Recommended)

```bash
cd backend

# Apply all pending migrations to the database
python migration_runner.py upgrade

# Show current database revision
python migration_runner.py current

# Show migration history
python migration_runner.py history

# Rollback last migration
python migration_runner.py downgrade

# Rollback to specific number of revisions
python migration_runner.py downgrade -2

# Rollback to specific revision
python migration_runner.py downgrade 001_initial_schema
```

### Option 2: Using Alembic Directly

```bash
cd backend

# Apply all pending migrations
alembic upgrade head

# Rollback last migration
alembic downgrade -1

# Show current revision
alembic current

# Show migration history
alembic history

# Rollback to specific revision
alembic downgrade 001_initial_schema
```

---

## Creating New Migrations

### Manual Migration (Define Changes Yourself)

```bash
# Create a new empty migration with a description
python migration_runner.py revision -m "add_column_to_book_table"

# Then edit the file in migrations/versions/
```

This creates a file like `002_add_column_to_book_table.py` in `migrations/versions/`.

Edit the `upgrade()` and `downgrade()` functions to define your schema changes.

### Example: Adding a Column

In your migration file (`migrations/versions/002_add_isbn_column.py`):

```python
def upgrade() -> None:
    op.add_column('book', sa.Column('isbn', sa.String(), nullable=True))

def downgrade() -> None:
    op.drop_column('book', 'isbn')
```

Then run:
```bash
python migration_runner.py upgrade
```

---

## Common Migration Operations

### Add a Column
```python
op.add_column('table_name', sa.Column('column_name', sa.String(), nullable=True))
```

### Drop a Column
```python
op.drop_column('table_name', 'column_name')
```

### Create an Index
```python
op.create_index('ix_table_column', 'table_name', ['column_name'], unique=False)
```

### Drop an Index
```python
op.drop_index('ix_table_column', table_name='table_name')
```

### Create a Table
```python
op.create_table(
    'new_table',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id')
)
```

### Drop a Table
```python
op.drop_table('table_name')
```

---

## Project Structure

```
backend/
├── alembic.ini                 # Alembic configuration
├── migration_runner.py         # Helper script for running migrations
├── migrations/
│   ├── env.py                  # Alembic environment configuration
│   ├── script.py.mako          # Migration template
│   └── versions/
│       ├── 001_initial_schema.py
│       ├── 002_add_isbn_column.py
│       └── ...
├── models/
│   ├── user.py
│   ├── book.py
│   ├── category.py
│   ├── author.py
│   ├── history.py
│   └── recommendation.py
├── main.py
└── ...
```

---

## Important Notes

1. **Always create migrations for schema changes** - Don't manually edit the database
2. **Version control migrations** - Commit migration files to git
3. **Test migrations** - Run upgrade then downgrade to ensure reversibility
4. **Naming conventions** - Use descriptive migration names (e.g., `add_isbn_to_books` not `migration_1`)
5. **Keep backups** - Before running migrations on production, backup your database

---

## Troubleshooting

### "No such table" Error
The database doesn't have the schema yet. Run:
```bash
python migration_runner.py upgrade
```

### "Can't locate revision" Error
Check if the migration file exists in `migrations/versions/` and the name is correct.

### Connection Issues
Verify your `.env` file has the correct `DATABASE_URL`:
```env
DATABASE_URL=postgresql+psycopg://postgres:juan@localhost:5432/elibrary_db
```

### Rolling Back All Migrations
```bash
python migration_runner.py downgrade base
```

---

## Next Steps

1. Update `main.py` to remove `SQLModel.metadata.create_all` calls
2. Run migrations before starting your application
3. Include migrations in your deployment pipeline
