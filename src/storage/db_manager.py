import sqlite3
from datetime import datetime, timezone
import os
import threading

DB_FILE = 'products.db'

class DBManager:
    
    def __init__(self, db_file: str = DB_FILE):
        db_dir = os.path.dirname(db_file)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        self.db_file = db_file
        self._lock = threading.Lock()

        try:
            self.conn = sqlite3.connect(db_file, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            print(f"[INFO] Connected to '{db_file}'")
        except sqlite3.Error as e:
            raise RuntimeError(f"Error connecting to database: {e}")

    def close_connection(self):
        if self.conn:
            self.conn.close()
            print(f"[INFO] Closed connection to '{self.db_file}'")

    def _execute(self, query: str, params: tuple = (), fetch: str = None):
        
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            if fetch == 'one':
                result = cursor.fetchone()
            elif fetch == 'all':
                result = cursor.fetchall()
            else:
                self.conn.commit()
                result = cursor.lastrowid if cursor.lastrowid != 0 else cursor.rowcount
            cursor.close()
            return result

    def initialize_database(self):
        create_table = """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_name TEXT NOT NULL,
            product_code TEXT NOT NULL,
            name TEXT NOT NULL,
            url TEXT,
            last_price_usd REAL,
            last_stock_status TEXT,
            is_tracked INTEGER DEFAULT 1,
            first_seen_timestamp TEXT NOT NULL,
            last_seen_timestamp TEXT NOT NULL,
            UNIQUE(site_name, product_code)
        );
        """
        self._execute(create_table)
        print("[INFO] 'products' table ready.")

    def add_or_update_product(self,
                              site_name: str,
                              product_code: str,
                              name: str,
                              url: str,
                              price_usd: float,
                              stock_status: str) -> bool:
        now_iso = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()

        if sqlite3.sqlite_version_info >= (3, 24, 0):
            query = """
            INSERT INTO products (site_name, product_code, name, url,
                                  last_price_usd, last_stock_status,
                                  first_seen_timestamp, last_seen_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(site_name, product_code) DO UPDATE SET
                name = excluded.name,
                url = excluded.url,
                last_price_usd = excluded.last_price_usd,
                last_stock_status = excluded.last_stock_status,
                last_seen_timestamp = excluded.last_seen_timestamp;
            """
            params = (site_name, product_code, name, url,
                      price_usd, stock_status, now_iso, now_iso)
            try:
                self._execute(query, params)
                return True
            except sqlite3.Error as e:
                print(f"[ERROR] Upsert failed: {e}")
                return False
        else:
            try:
                insert_q = ("INSERT INTO products (site_name, product_code, name, url,"
                            " last_price_usd, last_stock_status, first_seen_timestamp, last_seen_timestamp)"
                            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
                params = (site_name, product_code, name, url,
                          price_usd, stock_status, now_iso, now_iso)
                self._execute(insert_q, params)
                return True
            except sqlite3.IntegrityError:
                update_q = ("UPDATE products SET name = ?, url = ?, last_price_usd = ?,"
                            " last_stock_status = ?, last_seen_timestamp = ?"
                            " WHERE site_name = ? AND product_code = ?")
                update_params = (name, url, price_usd, stock_status, now_iso,
                                 site_name, product_code)
                try:
                    rowcount = self._execute(update_q, update_params)
                    return rowcount > 0
                except sqlite3.Error as e:
                    print(f"[ERROR] Update on conflict failed: {e}")
                    return False

    def get_product(self, site_name: str, product_code: str):
        query = "SELECT * FROM products WHERE site_name = ? AND product_code = ?;"
        return self._execute(query, (site_name, product_code), fetch='one')

    def update_product_tracking(self,
                                site_name: str,
                                product_code: str,
                                is_tracked: bool) -> int:
        query = "UPDATE products SET is_tracked = ? WHERE site_name = ? AND product_code = ?;"
        params = (1 if is_tracked else 0, site_name, product_code)
        return self._execute(query, params)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_connection()


if __name__ == '__main__':
    test_db = 'test_products.db'
    if os.path.exists(test_db): os.remove(test_db)

    with DBManager(db_file=test_db) as db:
        db.initialize_database()

        print("Testing insert...")
        assert db.add_or_update_product('site', 'code1', 'Name1', 'url1', 10.5, 'OK')
        prod = db.get_product('site', 'code1')
        print(dict(prod))

        print("Testing upsert...")
        assert db.add_or_update_product('site', 'code1', 'Name2', 'url2', 9.99, 'LOW')
        prod2 = db.get_product('site', 'code1')
        print(dict(prod2))

    if os.path.exists(test_db): os.remove(test_db)
