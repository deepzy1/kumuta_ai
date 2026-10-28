"""Run schema/data migrations without starting the app or contacting Google."""
from pathlib import Path
from dotenv import load_dotenv


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    from .database import migrate
    from .migrations import MIGRATIONS
    migrate()
    print(f'Migration complete (schema version {max(MIGRATIONS)}).')


if __name__ == '__main__':
    main()
