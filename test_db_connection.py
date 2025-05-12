import os
from dotenv import load_dotenv
import psycopg2
from datetime import datetime
import logging

# Logging ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# .env dosyasını yükle
load_dotenv(dotenv_path="odulbot.env")

def test_db_connection():
    try:
        # Bağlantı bilgilerini yazdır (şifre hariç)
        print("\n🔍 Bağlantı Bilgileri:")
        print(f"Host: {os.environ.get('PGHOST')}")
        print(f"Database: {os.environ.get('PGDATABASE')}")
        print(f"User: {os.environ.get('PGUSER')}")
        print(f"Port: {os.environ.get('PGPORT')}")
        
        # Veritabanına bağlan
        conn = psycopg2.connect(
            host=os.environ.get('PGHOST'),
            database=os.environ.get('PGDATABASE'),
            user=os.environ.get('PGUSER'),
            password=os.environ.get('PGPASSWORD'),
            port=os.environ.get('PGPORT')
        )
        
        print("\n✅ Veritabanı bağlantısı başarılı!")
        
        # Çekilişleri kontrol et
        with conn.cursor() as cur:
            print("\n🔍 Çekilişler kontrol ediliyor...")
            
            # Tablo yapısını kontrol et
            cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'giveaways'
            """)
            columns = cur.fetchall()
            print("\n📊 Giveaways tablo yapısı:")
            for col in columns:
                print(f"- {col[0]}: {col[1]}")
            
            # Aktif çekilişleri kontrol et
            cur.execute("""
                SELECT g.id, g.reward, g.cost, g.winners, g.end_time,
                       COALESCE(array_agg(gp.user_id), ARRAY[]::bigint[]) as participants
                FROM giveaways g
                LEFT JOIN giveaway_participants gp ON g.id = gp.giveaway_id
                WHERE g.end_time > CURRENT_TIMESTAMP
                GROUP BY g.id
                ORDER BY g.end_time ASC
            """)
            
            giveaways = cur.fetchall()
            print(f"\n🎯 Aktif çekiliş sayısı: {len(giveaways)}")
            
            if giveaways:
                print("\n📝 Çekiliş detayları:")
                for i, g in enumerate(giveaways, 1):
                    print(f"\nÇekiliş {i}:")
                    print(f"ID: {g[0]}")
                    print(f"Ödül: {g[1]}")
                    print(f"Maliyet: {g[2]} DMND")
                    print(f"Kazanan Sayısı: {g[3]}")
                    print(f"Bitiş: {g[4]}")
                    print(f"Katılımcı Sayısı: {len(g[5])}")
            else:
                print("\nℹ️ Aktif çekiliş bulunmuyor.")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"\n❌ Hata: {str(e)}")
        return False

if __name__ == "__main__":
    print("🔍 Veritabanı bağlantı testi başlıyor...")
    test_db_connection() 