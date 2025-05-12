import os
from dotenv import load_dotenv
import psycopg2
import logging

# Logging ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# .env dosyasını yükle
load_dotenv(dotenv_path="odulbot.env")

def reset_database():
    try:
        # Veritabanına bağlan
        conn = psycopg2.connect(
            host=os.environ.get('PGHOST'),
            database=os.environ.get('PGDATABASE'),
            user=os.environ.get('PGUSER'),
            password=os.environ.get('PGPASSWORD'),
            port=os.environ.get('PGPORT')
        )
        
        with conn.cursor() as cur:
            # Tabloları sil
            logging.info("🗑️ Tablolar siliniyor...")
            cur.execute("""
                DROP TABLE IF EXISTS announcements CASCADE;
                DROP TABLE IF EXISTS referrals CASCADE;
                DROP TABLE IF EXISTS point_requests CASCADE;
                DROP TABLE IF EXISTS completed_giveaways CASCADE;
                DROP TABLE IF EXISTS giveaway_participants CASCADE;
                DROP TABLE IF EXISTS giveaways CASCADE;
                DROP TABLE IF EXISTS user_points CASCADE;
            """)
            
            # Tabloları yeniden oluştur
            logging.info("📊 Tablolar yeniden oluşturuluyor...")
            
            # Kullanıcı tablosu
            cur.execute('''
                CREATE TABLE user_points (
                    user_id BIGINT PRIMARY KEY,
                    points INTEGER DEFAULT 0,
                    role VARCHAR(20) DEFAULT 'User',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Çekilişler tablosu
            cur.execute('''
                CREATE TABLE giveaways (
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
                CREATE TABLE giveaway_participants (
                    giveaway_id INTEGER REFERENCES giveaways(id),
                    user_id BIGINT REFERENCES user_points(user_id),
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (giveaway_id, user_id)
                )
            ''')
            
            # Tamamlanmış çekilişler tablosu
            cur.execute('''
                CREATE TABLE completed_giveaways (
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
                CREATE TABLE point_requests (
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
                CREATE TABLE referrals (
                    id SERIAL PRIMARY KEY,
                    referrer_id BIGINT REFERENCES user_points(user_id),
                    referred_id BIGINT REFERENCES user_points(user_id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Duyurular tablosu
            cur.execute('''
                CREATE TABLE announcements (
                    id SERIAL PRIMARY KEY,
                    text TEXT NOT NULL,
                    photo_id VARCHAR(255),
                    sent_by BIGINT REFERENCES user_points(user_id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Admin kullanıcısını ekle
            logging.info("👤 Admin kullanıcısı ekleniyor...")
            cur.execute('''
                INSERT INTO user_points (user_id, points, role)
                VALUES (729250257, 1000, 'Admin')
                ON CONFLICT (user_id) DO UPDATE 
                SET points = 1000, role = 'Admin'
            ''')
            
            conn.commit()
            logging.info("✅ Veritabanı başarıyla sıfırlandı ve yeniden oluşturuldu!")
            
    except Exception as e:
        logging.error(f"❌ Hata: {str(e)}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    print("🔄 Veritabanı sıfırlama işlemi başlıyor...")
    reset_database() 