from storage.database import sync_connection, sync_cursor
from config.settings import load_config
from storage.database import init_sync_pool

cfg = load_config()
init_sync_pool(cfg.db)

with sync_connection() as conn:
    with sync_cursor(conn) as cur:
        # raw_articles stats
        cur.execute("SELECT status, count(*) FROM raw_articles GROUP BY status;")
        raw_stats = cur.fetchall()
        print("--- RAW ARTICLES ---")
        for row in raw_stats:
            print(f"{row['status']}: {row['count']}")

        # processed_articles stats
        cur.execute("SELECT status, count(*) FROM processed_articles GROUP BY status;")
        proc_stats = cur.fetchall()
        print("\n--- PROCESSED ARTICLES ---")
        for row in proc_stats:
            print(f"{row['status']}: {row['count']}")
