import psycopg2
from psycopg2 import pool
from datetime import datetime
import os
from dotenv import load_dotenv
import logging
import json

# Logging ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# .env dosyasını yükle
load_dotenv(dotenv_path="odulbot.env")

class Database:
    _connection_pool = None
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if Database._connection_pool is None:
            try:
                # Bağlantı havuzu ayarlarını güncelle
                Database._connection_pool = pool.ThreadedConnectionPool(
                    minconn=5,
                    maxconn=20,
                    host=os.environ.get('PGHOST'),
                    database=os.environ.get('PGDATABASE'),
                    user=os.environ.get('PGUSER'),
                    password=os.environ.get('PGPASSWORD'),
                    port=os.environ.get('PGPORT'),
                    sslmode=os.environ.get('PGSSLMODE', 'require'),
                    # Bağlantı zaman aşımı ayarları
                    connect_timeout=10,
                    keepalives=1,
                    keepalives_idle=30,
                    keepalives_interval=10,
                    keepalives_count=5
                )
                logging.info("✅ Veritabanı bağlantı havuzu oluşturuldu")
                self.init_db()  # Veritabanını başlat
            except Exception as e:
                logging.error(f"❌ Veritabanı bağlantı havuzu oluşturulurken hata: {str(e)}")
                raise

    def get_connection(self):
        max_retries = 3
        retry_count = 0
        last_error = None
        
        while retry_count < max_retries:
            try:
                conn = self._connection_pool.getconn()
                # Bağlantıyı test et
                with conn.cursor() as cur:
                    cur.execute('SELECT 1')
                return conn
            except Exception as e:
                last_error = e
                retry_count += 1
                logging.warning(f"⚠️ Bağlantı alınamadı (Deneme {retry_count}/{max_retries}): {str(e)}")
                if retry_count < max_retries:
                    import time
                    time.sleep(1)  # 1 saniye bekle
        
        logging.error(f"❌ Veritabanı bağlantısı alınamadı: {str(last_error)}")
        raise last_error

    def release_connection(self, conn):
        try:
            if conn and not conn.closed:
                self._connection_pool.putconn(conn)
        except Exception as e:
            logging.error(f"❌ Veritabanı bağlantısı serbest bırakılırken hata: {str(e)}")
            try:
                conn.close()
            except:
                pass
            raise

    def __del__(self):
        if Database._connection_pool is not None:
            try:
                Database._connection_pool.closeall()
                logging.info("✅ Veritabanı bağlantı havuzu kapatıldı")
            except Exception as e:
                logging.error(f"❌ Veritabanı bağlantı havuzu kapatılırken hata: {str(e)}")

    def init_db(self):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Kullanıcı tablosu
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS user_points (
                        user_id BIGINT PRIMARY KEY,
                        points INTEGER DEFAULT 0,
                        role VARCHAR(20) DEFAULT 'User',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Çekilişler tablosu
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS giveaways (
                        id SERIAL PRIMARY KEY,
                        reward VARCHAR(100) NOT NULL,
                        cost INTEGER NOT NULL,
                        winners INTEGER NOT NULL,
                        end_time TIMESTAMP NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Çekiliş katılımcıları tablosu
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS giveaway_participants (
                        giveaway_id INTEGER REFERENCES giveaways(id),
                        user_id BIGINT REFERENCES user_points(user_id),
                        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (giveaway_id, user_id)
                    )
                ''')

                # Tamamlanmış çekilişler tablosu
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS completed_giveaways (
                        id SERIAL PRIMARY KEY,
                        giveaway_id INTEGER REFERENCES giveaways(id),
                        reward VARCHAR(100) NOT NULL,
                        prize_points INTEGER NOT NULL,
                        participants_count INTEGER NOT NULL,
                        winners JSONB NOT NULL,
                        end_time TIMESTAMP NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Puan talepleri tablosu
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS point_requests (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES user_points(user_id),
                        wallet_address VARCHAR(42) NOT NULL,
                        amount INTEGER NOT NULL,
                        status VARCHAR(20) DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        processed_at TIMESTAMP
                    )
                ''')

                # Referanslar tablosu
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS referrals (
                        id SERIAL PRIMARY KEY,
                        referrer_id BIGINT REFERENCES user_points(user_id),
                        referred_id BIGINT REFERENCES user_points(user_id),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Duyurular tablosu
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS announcements (
                        id SERIAL PRIMARY KEY,
                        text TEXT NOT NULL,
                        photo_id VARCHAR(255),
                        sent_by BIGINT REFERENCES user_points(user_id),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            conn.commit()

    def get_user_points(self, user_id):
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute('SELECT points FROM user_points WHERE user_id = %s', (user_id,))
                result = cur.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logging.error(f"❌ Kullanıcı puanları alınırken hata: {str(e)}")
            raise
        finally:
            if conn:
                self.release_connection(conn)

    def set_user_points(self, user_id, points):
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO user_points (user_id, points)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE
                    SET points = %s
                ''', (user_id, points, points))
                conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logging.error(f"❌ Kullanıcı puanları güncellenirken hata: {str(e)}")
            raise
        finally:
            if conn:
                self.release_connection(conn)

    def get_user_role(self, user_id):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT role FROM user_points WHERE user_id = %s', (user_id,))
                result = cur.fetchone()
                return result[0] if result else 'User'

    def set_user_role(self, user_id, role):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO user_points (user_id, role)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET role = %s
                ''', (user_id, role, role))
            conn.commit()

    def create_giveaway(self, reward, cost, winners, end_time):
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO giveaways (reward, cost, winners, end_time)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                ''', (reward, cost, winners, end_time))
                giveaway_id = cur.fetchone()[0]
                conn.commit()
                return giveaway_id
        except Exception as e:
            if conn:
                conn.rollback()
            logging.error(f"❌ Çekiliş oluşturulurken hata: {str(e)}")
            raise
        finally:
            if conn:
                self.release_connection(conn)

    def get_active_giveaways(self):
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT g.id, g.reward, g.cost, g.winners, g.end_time,
                           COALESCE(array_agg(gp.user_id), ARRAY[]::bigint[]) as participants
                    FROM giveaways g
                    LEFT JOIN giveaway_participants gp ON g.id = gp.giveaway_id
                    WHERE g.end_time > CURRENT_TIMESTAMP
                    GROUP BY g.id
                    ORDER BY g.end_time ASC
                ''')
                giveaways = []
                for row in cur.fetchall():
                    giveaway_id, reward, cost, winners, end_time, participants = row
                    giveaways.append({
                        "id": giveaway_id,
                        "reward": reward,
                        "cost": cost,
                        "winners": winners,
                        "end_time": end_time,
                        "participants": participants
                    })
                return giveaways
        except Exception as e:
            logging.error(f"❌ Aktif çekilişler alınırken hata: {str(e)}")
            raise
        finally:
            if conn:
                self.release_connection(conn)

    def delete_giveaway(self, giveaway_id):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM giveaway_participants WHERE giveaway_id = %s', (giveaway_id,))
                cur.execute('DELETE FROM giveaways WHERE id = %s', (giveaway_id,))
            conn.commit()

    def add_participant(self, giveaway_id, user_id):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO giveaway_participants (giveaway_id, user_id)
                    VALUES (%s, %s)
                    ON CONFLICT (giveaway_id, user_id) DO NOTHING
                ''', (giveaway_id, user_id))
            conn.commit()

    def get_participants(self, giveaway_id):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT user_id FROM giveaway_participants
                    WHERE giveaway_id = %s
                ''', (giveaway_id,))
                return [row[0] for row in cur.fetchall()]

    def complete_giveaway(self, giveaway_id, reward, prize_points, participants_count, winners):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO completed_giveaways 
                    (giveaway_id, reward, prize_points, participants_count, winners, end_time)
                    VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ''', (giveaway_id, reward, prize_points, participants_count, winners))
                cur.execute('DELETE FROM giveaways WHERE id = %s', (giveaway_id,))
            conn.commit()

    def add_point_request(self, request_data):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO point_requests (user_id, wallet_address, amount)
                    VALUES (%s, %s, %s)
                ''', (request_data['user_id'], request_data['wallet_address'], request_data['amount']))
            conn.commit()

    def get_pending_requests(self):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT id, user_id, wallet_address, amount, created_at
                    FROM point_requests
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                ''')
                requests = []
                for row in cur.fetchall():
                    requests.append({
                        "id": row[0],
                        "user_id": row[1],
                        "wallet_address": row[2],
                        "amount": row[3],
                        "created_at": row[4]
                    })
                return requests

    def add_processed_request(self, request_data):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    UPDATE point_requests
                    SET status = %s, processed_at = %s
                    WHERE id = %s
                ''', (request_data['status'], request_data['processed_date'], request_data['id']))
            conn.commit()

    def add_referral(self, referrer_id, referred_id):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO referrals (referrer_id, referred_id)
                    VALUES (%s, %s)
                ''', (referrer_id, referred_id))
            conn.commit()

    def get_referrals(self, referrer_id):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT referred_id FROM referrals
                    WHERE referrer_id = %s
                ''', (referrer_id,))
                return [row[0] for row in cur.fetchall()]

    def add_announcement(self, announcement_data):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO announcements (text, photo_id, sent_by)
                    VALUES (%s, %s, %s)
                ''', (announcement_data['text'], announcement_data.get('photo'), announcement_data['sent_by']))
            conn.commit()

    def get_announcements(self):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT text, photo_id, created_at
                    FROM announcements
                    ORDER BY created_at DESC
                    LIMIT 5
                ''')
                announcements = []
                for row in cur.fetchall():
                    announcements.append({
                        "text": row[0],
                        "photo_id": row[1],
                        "date": row[2]
                    })
                return announcements 