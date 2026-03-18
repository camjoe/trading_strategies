# Dev Tools

Helper scripts for local database maintenance.

## Usage

Run from the repository root:

```powershell
python -m dev_tools.db_admin <command>
```

## Commands

### List accounts

```powershell
python -m dev_tools.db_admin list-accounts
```

### Backup database

Create a timestamped backup in `trading/database/backups/`:

```powershell
python -m dev_tools.db_admin backup-db
```

Backup to a specific directory:

```powershell
python -m dev_tools.db_admin backup-db local/backups
```

Backup to a specific file:

```powershell
python -m dev_tools.db_admin backup-db local/backups/paper_trading_manual.db
```

### Delete accounts

Preview deletes (no changes):

```powershell
python -m dev_tools.db_admin delete-accounts momentum_5k meanrev_5k --dry-run
```

Delete specific accounts and create a backup first:

```powershell
python -m dev_tools.db_admin delete-accounts momentum_5k,meanrev_5k --backup-before
```

Delete all accounts (requires explicit confirmation flag):

```powershell
python -m dev_tools.db_admin delete-accounts --all --yes --backup-before
```
