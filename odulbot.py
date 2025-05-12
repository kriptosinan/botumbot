from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import logging
import random
from datetime import datetime, timedelta
import asyncio
import uuid
from database import Database

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Bot Token
TOKEN = "7722882261:AAHYp2wPLzfgHkcw85l96TCOLVAnUiE-JFw"

# Bot Username
BOT_USERNAME = "Kazanclibotum_bot"

# Admin ID
ADMIN_ID = 729250257

# Initialize database
db = Database()

# Global veri yapıları dosyadan yükleniyor
user_roles = {}  # Kullanıcı rollerini saklamak için boş sözlük
giveaways = []  # Aktif çekilişleri saklamak için boş liste
referrals = []  # Referansları saklamak için boş liste
completed_giveaways = []  # Tamamlanmış çekilişleri saklamak için boş liste
point_requests = []  # Puan taleplerini saklamak için boş liste
processed_requests = []  # İşlenmiş talepleri saklamak için boş liste

# Veritabanından kullanıcı rollerini yükle
def load_user_roles():
    global user_roles
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, role FROM user_points')
        for user_id, role in cursor.fetchall():
            user_roles[user_id] = role

# Veritabanından aktif çekilişleri yükle
def load_giveaways():
    global giveaways
    try:
        giveaways = db.get_active_giveaways()
        # Tarih formatını düzelt
        for giveaway in giveaways:
            if isinstance(giveaway["end_time"], str):
                giveaway["end_time"] = datetime.strptime(giveaway["end_time"], '%Y-%m-%d %H:%M:%S')
        logging.info(f"✅ {len(giveaways)} aktif çekiliş yüklendi")
    except Exception as e:
        logging.error(f"❌ Çekilişler yüklenirken hata: {str(e)}")
        giveaways = []  # Hata durumunda boş liste
        raise  # Hatayı yukarı ilet

# Bot başlatıldığında verileri yükle
load_user_roles()
load_giveaways()

# Sabit klavyeler kaldırıldı, dinamik olarak oluşturulacak
def get_main_keyboard(is_admin=False):
    buttons = [
        [KeyboardButton("💎 Puanlarım"), KeyboardButton("🔗 Referans Linkim")],
        [KeyboardButton("🎯 Etkinlikler"), KeyboardButton("⚙️ Admin Paneli")] if is_admin else [KeyboardButton("🎯 Etkinlikler")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_events_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📊 Çekilişler"), KeyboardButton("🎉 Çekilişe Katıl")],
        [KeyboardButton("🏆 Çekiliş Sonuçları"), KeyboardButton("🔙 Geri Git")]
    ], resize_keyboard=True)

def get_admin_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("➕ Çekiliş Oluştur"), KeyboardButton("🏁 Çekilişi Bitir")],
        [KeyboardButton("👥 Üye Yönetimi"), KeyboardButton("📝 Talepler")],
        [KeyboardButton("🎯 Etkinlikler"), KeyboardButton("💎 Puanlarım")],
        [KeyboardButton("🔗 Referans Linkim")]
    ], resize_keyboard=True)

def get_points_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("💎 DMND Token ile Puan Kazan"), KeyboardButton("📝 Puan Talep Formu")],
        [KeyboardButton("💸 Puan Transfer"), KeyboardButton("🔙 Geri Git")]
    ], resize_keyboard=True)

def get_giveaway_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🔙 Geri Git"), KeyboardButton("❌ İptal")]
    ], resize_keyboard=True)

def get_transfer_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🔙 Geri Git"), KeyboardButton("❌ İptal")]
    ], resize_keyboard=True)

def get_member_management_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("➕ Puan Ekle"), KeyboardButton("➖ Puan Düş")],
        [KeyboardButton("🔙 Geri Git"), KeyboardButton("❌ İptal")]
    ], resize_keyboard=True)

def get_point_request_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🔙 Geri Git"), KeyboardButton("❌ İptal")]
    ], resize_keyboard=True)

def get_request_management_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("✅ Onayla"), KeyboardButton("❌ Reddet")],
        [KeyboardButton("🔙 Geri Git"), KeyboardButton("❌ İptal")]
    ], resize_keyboard=True)

def get_announcement_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🔙 Geri Git")]
    ], resize_keyboard=True)

def get_announcement_list_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🔄 Yenile"), KeyboardButton("🔙 Geri Git")]
    ], resize_keyboard=True)

# Çekiliş oluşturma adımları
GIVEAWAY_STEPS = {
    "waiting": 0,
    "reward": 1,
    "points": 2,
    "winners": 3,
    "duration": 4
}

# Transfer adımları
TRANSFER_STEPS = {
    "waiting": 0,
    "username": 1,
    "amount": 2
}

# Üye yönetimi adımları
MEMBER_MANAGEMENT_STEPS = {
    "waiting": 0,
    "username": 1,
    "amount": 2
}

# Puan talep formu adımları
POINT_REQUEST_STEPS = {
    "waiting": 0,
    "wallet": 1,
    "amount": 2
}

# Duyuru adımları
ANNOUNCEMENT_STEPS = {
    "waiting": 0,
    "text": 1,
    "image": 2
}

# Çekiliş kontrolü için asenkron fonksiyon
async def check_giveaways(context: ContextTypes.DEFAULT_TYPE):
    try:
        current_time = datetime.now()
        active_giveaways = db.get_active_giveaways()
        
        for giveaway in active_giveaways:
            end_time = giveaway["end_time"]
            if isinstance(end_time, str):
                end_time = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
            
            if current_time >= end_time:
                giveaway_id = giveaway["id"]
                participants = giveaway["participants"]
                if participants:
                    random.shuffle(participants)
                    winner_count = min(giveaway["winners"], len(participants))
                    winners_list = participants[:winner_count]
                    reward_amount = int(giveaway["reward"].split()[0])
                    prize_points = reward_amount // winner_count
                    
                    # Complete the giveaway
                    db.complete_giveaway(giveaway_id, giveaway["reward"], prize_points, len(participants), winners_list)
                    
                    # Update points for winners
                    for winner_id in winners_list:
                        current_points = db.get_user_points(winner_id)
                        db.set_user_points(winner_id, current_points + prize_points)
                        try:
                            winner = await context.bot.get_chat(winner_id)
                            await context.bot.send_message(
                                winner_id,
                                f"🎉 *Tebrikler!* 🎉\n\n"
                                f"🏆 {giveaway['reward']} çekilişini kazandın!\n"
                                f"💰 Ödül olarak {prize_points} DMND Puanı hesabına eklendi!\n"
                                f"💎 Eski puan durumun: {current_points} DMND\n"
                                f"💎 Yeni puan durumun: {current_points + prize_points} DMND\n\n"
                                "🎊 *Kutluyoruz!* 🎊",
                                parse_mode='Markdown'
                            )
                        except Exception as e:
                            logging.error(f"Error sending winner notification: {e}")
                    
                    # Send results to admin
                    try:
                        admin_result_message = (
                            "✅ *ÇEKİLİŞ SONUÇLARI* ✅\n\n"
                            f"🏆 *Ödül:* {giveaway['reward']}\n"
                            f"👑 *Kazananlar:*\n" + 
                            "\n".join([f"• {(await context.bot.get_chat(winner_id)).first_name} (@{(await context.bot.get_chat(winner_id)).username}) (ID: `{winner_id}`)" for winner_id in winners_list]) + "\n" +
                            f"💰 *Kazanılan:* {prize_points} DMND (her kazanan için)\n"
                            f"👥 *Toplam Katılımcı:* {len(participants)}\n"
                            f"⏰ *Bitiş Tarihi:* {current_time.strftime('%d.%m.%Y %H:%M')}\n\n"
                            "🎊 *Tebrikler Kazananlarımıza!* 🎊"
                        )
                        await context.bot.send_message(ADMIN_ID, admin_result_message, parse_mode='Markdown')
                    except Exception as e:
                        logging.error(f"Error sending admin notification: {e}")
                    
                    # Send results to participants
                    user_result_message = (
                        "✅ *ÇEKİLİŞ SONUÇLARI* ✅\n\n"
                        f"🏆 *Ödül:* {giveaway['reward']}\n"
                        f"👑 *Kazananlar:*\n" +
                        "\n".join([f"• {(await context.bot.get_chat(winner_id)).first_name} (@{(await context.bot.get_chat(winner_id)).username})" for winner_id in winners_list]) + "\n" +
                        f"💰 *Kazanılan:* {prize_points} DMND (her kazanan için)\n"
                        f"👥 *Toplam Katılımcı:* {len(participants)}\n"
                        f"⏰ *Bitiş Tarihi:* {current_time.strftime('%d.%m.%Y %H:%M')}\n\n"
                        "🎊 *Tebrikler Kazananlarımıza!* 🎊"
                    )
                    
                    for participant_id in participants:
                        if participant_id not in winners_list:
                            try:
                                await context.bot.send_message(participant_id, user_result_message, parse_mode='Markdown')
                            except Exception as e:
                                logging.error(f"Error sending participant notification: {e}")
    except Exception as e:
        logging.error(f"Error in check_giveaways: {e}")

# Job queue için sync wrapper
async def check_giveaways_job(context: ContextTypes.DEFAULT_TYPE):
    await check_giveaways(context)

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    
    if db.get_user_points(user_id) == 0:
        db.set_user_points(user_id, 10)
        db.set_user_role(user_id, "Admin" if user_id == ADMIN_ID else "User")
        await update.message.reply_text(f"Hoş geldin, {user.first_name}! Katıldığın için 10 DMND Puanı kazandın!")
    
    keyboard = get_admin_keyboard() if user_id == ADMIN_ID else get_main_keyboard()
    await update.message.reply_text("Çekiliş Botuna Hoş Geldin! Bir seçenek seç:", reply_markup=keyboard)

# Handle text messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    user_id = update.effective_user.id

    if text == "🏆 Çekiliş Sonuçları":
        if not completed_giveaways:
            await update.message.reply_text("Henüz tamamlanmış çekiliş bulunmuyor.", reply_markup=get_main_keyboard(user_id == ADMIN_ID))
            return
        results = []
        for i, giveaway in enumerate(completed_giveaways[-5:], 1):
            if user_id == ADMIN_ID:
                results.append(
                    f"🎯 *Çekiliş {i}*\n"
                    f"🏆 Ödül: {giveaway['reward']}\n"
                    f"👑 Kazananlar:\n" + 
                    "\n".join([f"- {winner.first_name} (@{winner.username}) (ID: `{winner.id}`)" for winner in giveaway["winners"]]) + "\n" +
                    f"💰 Kazanılan: {giveaway['prize_points']} DMND\n"
                    f"👥 Katılımcı: {giveaway['participants_count']}\n"
                    f"⏰ Tarih: {giveaway['end_time'].strftime('%d.%m.%Y %H:%M')}\n"
                )
            else:
                results.append(
                    f"🎯 *Çekiliş {i}*\n"
                    f"🏆 Ödül: {giveaway['reward']}\n"
                    f"🆔 Kazanan ID'leri:\n" +
                    "\n".join([f"- `{winner_id}`" for winner_id in giveaway["winner_ids"]]) + "\n" +
                    f"💰 Kazanılan: {giveaway['prize_points']} DMND\n"
                    f"👥 Katılımcı: {giveaway['participants_count']}\n"
                    f"⏰ Tarih: {giveaway['end_time'].strftime('%d.%m.%Y %H:%M')}\n"
                )
        await update.message.reply_text(
            "🏆 *Son Çekiliş Sonuçları* 🏆\n\n" + "\n".join(results),
            parse_mode='Markdown',
            reply_markup=get_main_keyboard(user_id == ADMIN_ID)
        )

    elif text == "🎉 Çekilişe Katıl":
        if not giveaways:
            await update.message.reply_text("Şu anda aktif çekiliş bulunmuyor.", reply_markup=get_main_keyboard(user_id == ADMIN_ID))
            return
        giveaway_list = "\n".join([
            f"🎯 *Çekiliş {i+1}*\n"
            f"🏆 Ödül: {g['reward']}\n"
            f"💰 Maliyet: {g['cost']} DMND\n"
            f"⏰ Son Katılım: {g['end_time'].strftime('%d.%m.%Y %H:%M')}\n"
            f"👥 Katılımcı: {len(g['participants'])} kişi\n"
            for i, g in enumerate(giveaways)
        ])
        await update.message.reply_text(
            f"🎉 *Aktif Çekilişler* 🎉\n\n{giveaway_list}\n\n"
            "Katılmak için çekiliş numarasını yazın (örn: 1)",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard(user_id == ADMIN_ID)
        )

    elif text == "💎 Puanlarım":
        points = db.get_user_points(user_id)
        await update.message.reply_text(
            f"💰 *Puan Durumun* 💰\n\n"
            f"Toplam: {points} DMND Puanı\n\n"
            "Puanlarınızı başka üyelere transfer etmek için '💸 Puan Transfer' butonunu kullanabilirsiniz.",
            parse_mode='Markdown',
            reply_markup=get_points_keyboard()
        )

    elif text == "💎 DMND Token ile Puan Kazan":
        await update.message.reply_text(
            "💎 *DMND Token ile Puan Kazanma* 💎\n\n"
            "DMND Token satın alarak puan kazanabilirsiniz.\n"
            "1 DMND Token = 1 Puan olarak hesaplanır\n\n"
            "🛒 *DMND Token Satın Al:*\n"
            "https://pancakeswap.finance/swap?outputCurrency=0x2038E7C6A5C45908249e8bA785B8df5E9A8F5074\n\n"
            "DMND Token aldıktan sonra aşağıdaki cüzdana gönderdikten sonra Puan talebini '📝 Puan Talep Formu' ile admin'e iletebilirsiniz.\n\n"
            "📬 *Cüzdan Adresi:*\n"
            "`0x49bbC2dd14FDB50cEb2104358bE9dE865B803165`\n\n"
            "💡 *Not:* Cüzdan adresini kopyalamak için üzerine tıklayın.",
            parse_mode='Markdown',
            reply_markup=get_points_keyboard(),
            disable_web_page_preview=True
        )

    elif text == "📝 Puan Talep Formu":
        context.user_data["requesting_points"] = True
        context.user_data["request_step"] = POINT_REQUEST_STEPS["wallet"]
        await update.message.reply_text(
            "📝 *Puan Talep Formu* 📝\n\n"
            "1️⃣ Adım: DMND Token'ı gönderdiğiniz cüzdan adresini yazın\n"
            "Örnek: 0x1234...\n\n"
            "İptal etmek için '🔙 Geri Git' butonuna basın.",
            parse_mode='Markdown',
            reply_markup=get_point_request_keyboard()
        )

    elif text == "🔗 Referans Linkim":
        referral_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        keyboard = get_admin_keyboard() if user_id == ADMIN_ID else get_main_keyboard()
        await update.message.reply_text(
            f"🔗 *Referans Linkin* 🔗\n\n"
            f"`{referral_link}`\n\n"
            "Bu linki paylaşarak arkadaşlarını davet edebilirsin.\n"
            "Her davet ettiğin kişi için 1 DMND Puanı kazanırsın!",
            parse_mode='Markdown',
            reply_markup=keyboard
        )

    elif text == "⚙️ Admin Paneli":
        if user_id != ADMIN_ID:
            await update.message.reply_text("Bu bölüme erişmek için Admin olmalısın.", reply_markup=get_main_keyboard())
            return
        await update.message.reply_text("⚙️ *Admin Paneli* ⚙️", parse_mode='Markdown', reply_markup=get_admin_keyboard())

    elif text == "🎯 Etkinlikler":
        await update.message.reply_text(
            "🎯 *Etkinlikler* \n\n"
            "Aşağıdaki butonları kullanarak çekilişlere katılabilirsiniz!",
            parse_mode='Markdown',
            reply_markup=get_events_keyboard()
        )

    elif text == "🔙 Geri Git":
        # Tüm state'leri temizle
        context.user_data.clear()
        
        # Kullanıcı tipine göre ana menüye dön
        if user_id == ADMIN_ID:
            await update.message.reply_text(
                "🏠 *Ana Menüye Dönüldü* 🏠",
                parse_mode='Markdown',
                reply_markup=get_admin_keyboard()
            )
        else:
            await update.message.reply_text(
                "🏠 *Ana Menüye Dönüldü* 🏠",
                parse_mode='Markdown',
                reply_markup=get_main_keyboard()
            )

    # Etkinlikler menüsünden geri dönüş
    elif text == "🔙 Geri Git" and context.user_data.get("in_events_menu"):
        context.user_data.clear()
        if user_id == ADMIN_ID:
            await update.message.reply_text(
                "🏠 *Ana Menüye Dönüldü* 🏠",
                parse_mode='Markdown',
                reply_markup=get_admin_keyboard()
            )
        else:
            await update.message.reply_text(
                "🏠 *Ana Menüye Dönüldü* 🏠",
                parse_mode='Markdown',
                reply_markup=get_main_keyboard()
            )

    # Puanlar menüsünden geri dönüş
    elif text == "🔙 Geri Git" and context.user_data.get("in_points_menu"):
        context.user_data.clear()
        if user_id == ADMIN_ID:
            await update.message.reply_text(
                "🏠 *Ana Menüye Dönüldü* 🏠",
                parse_mode='Markdown',
                reply_markup=get_admin_keyboard()
            )
        else:
            await update.message.reply_text(
                "🏠 *Ana Menüye Dönüldü* 🏠",
                parse_mode='Markdown',
                reply_markup=get_main_keyboard()
            )

    # Çekiliş menüsünden geri dönüş
    elif text == "🔙 Geri Git" and context.user_data.get("in_giveaway_menu"):
        context.user_data.clear()
        await update.message.reply_text(
            "🏠 *Etkinlikler Menüsüne Dönüldü* 🏠",
            parse_mode='Markdown',
            reply_markup=get_events_keyboard()
        )

    # Üye yönetimi menüsünden geri dönüş
    elif text == "🔙 Geri Git" and context.user_data.get("managing_members"):
        context.user_data.clear()
        await update.message.reply_text(
            "🏠 *Admin Paneline Dönüldü* 🏠",
            parse_mode='Markdown',
            reply_markup=get_admin_keyboard()
        )

    # Talep yönetimi menüsünden geri dönüş
    elif text == "🔙 Geri Git" and context.user_data.get("managing_requests"):
        context.user_data.clear()
        await update.message.reply_text(
            "🏠 *Admin Paneline Dönüldü* 🏠",
            parse_mode='Markdown',
            reply_markup=get_admin_keyboard()
        )

    # Duyuru menüsünden geri dönüş
    elif text == "🔙 Geri Git" and context.user_data.get("sending_announcement"):
        context.user_data.clear()
        await update.message.reply_text(
            "🏠 *Admin Paneline Dönüldü* 🏠",
            parse_mode='Markdown',
            reply_markup=get_admin_keyboard()
        )

    # Puan transfer menüsünden geri dönüş
    elif text == "🔙 Geri Git" and context.user_data.get("transferring_points"):
        context.user_data.clear()
        await update.message.reply_text(
            "🏠 *Puanlar Menüsüne Dönüldü* 🏠",
            parse_mode='Markdown',
            reply_markup=get_points_keyboard()
        )

    # Puan talep menüsünden geri dönüş
    elif text == "🔙 Geri Git" and context.user_data.get("requesting_points"):
        context.user_data.clear()
        await update.message.reply_text(
            "🏠 *Puanlar Menüsüne Dönüldü* 🏠",
            parse_mode='Markdown',
            reply_markup=get_points_keyboard()
        )

    elif text == "🏁 Çekilişi Bitir":
        if user_id != ADMIN_ID:
            await update.message.reply_text("Sadece Adminler kullanabilir!", reply_markup=get_main_keyboard())
            return
        if not giveaways:
            await update.message.reply_text("Bitirilecek aktif çekiliş yok.", reply_markup=get_admin_keyboard())
            return
        giveaway_list = "\n".join([
            f"🎯 *Çekiliş {i+1}*\n"
            f"🏆 Ödül: {g['reward']}\n"
            f"⏰ Son Katılım: {g['end_time'].strftime('%d.%m.%Y %H:%M')}\n"
            f"👥 Katılımcı: {len(g['participants'])} kişi\n"
            for i, g in enumerate(giveaways)
        ])
        await update.message.reply_text(
            f"🏁 *Bitirilecek Çekilişler* 🏁\n\n{giveaway_list}\n\n"
            "Bitirmek istediğin çekilişin numarasını yazın:\n\n"
            "İptal etmek için '🔙 Geri Git' butonuna basın.",
            parse_mode='Markdown',
            reply_markup=get_giveaway_keyboard()
        )
        context.user_data["ending_giveaway"] = True

    elif text == "📊 Çekilişler":
        try:
            # Aktif çekilişleri yeniden yükle
            load_giveaways()
            
            if not giveaways:
                await update.message.reply_text(
                    "📢 *Aktif Çekiliş Yok* 📢\n\n"
                    "Şu anda aktif çekiliş bulunmuyor.",
                    parse_mode='Markdown',
                    reply_markup=get_events_keyboard()
                )
                return

            giveaway_list = []
            for i, giveaway in enumerate(giveaways, 1):
                try:
                    participant_count = len(giveaway.get("participants", []))
                    end_time = giveaway["end_time"]
                    
                    giveaway_text = (
                        f"🎯 *Çekiliş {i}*\n"
                        f"🏆 Ödül: {giveaway['reward']}\n"
                        f"💰 Maliyet: {giveaway['cost']} DMND\n"
                        f"⏰ Son Katılım: {end_time.strftime('%d.%m.%Y %H:%M')}\n"
                        f"👥 Katılımcı: {participant_count} kişi\n"
                    )
                    giveaway_list.append(giveaway_text)
                except Exception as e:
                    logging.error(f"Çekiliş {i} listelenirken hata: {str(e)}")
                    continue

            if not giveaway_list:
                await update.message.reply_text(
                    "❌ Çekilişler listelenirken bir hata oluştu.\n"
                    "Lütfen daha sonra tekrar deneyin.",
                    parse_mode='Markdown',
                    reply_markup=get_events_keyboard()
                )
                return

            await update.message.reply_text(
                f"📊 *Aktif Çekilişler* 📊\n\n" + "\n\n".join(giveaway_list) + "\n\n"
                "Katılmak için '🎉 Çekilişe Katıl' butonuna basın.",
                parse_mode='Markdown',
                reply_markup=get_events_keyboard()
            )
        except Exception as e:
            logging.error(f"Çekiliş listeleme hatası: {str(e)}")
            await update.message.reply_text(
                "❌ Çekilişler yüklenirken bir hata oluştu.\n"
                "Lütfen daha sonra tekrar deneyin.",
                parse_mode='Markdown',
                reply_markup=get_events_keyboard()
            )

    elif text == "👥 Üye Yönetimi":
        if user_id != ADMIN_ID:
            await update.message.reply_text("Sadece Adminler kullanabilir!", reply_markup=get_main_keyboard())
            return
        users_list = []
        for uid in user_roles.keys():
            try:
                user = await context.bot.get_chat(uid)
                username = user.username or user.first_name
                points = user_roles.get(uid, 0)
                role = "👑 Admin" if uid == ADMIN_ID else "👤 Üye"
                users_list.append(
                    f"{role}\n"
                    f"🆔 ID: `{uid}`\n"
                    f"👤 Kullanıcı: @{username}\n"
                    f"💰 Puan: {points} DMND\n"
                )
            except Exception as e:
                logging.error(f"Error getting user info for {uid}: {e}")
                continue
        if not users_list:
            await update.message.reply_text(
                "❌ Henüz hiç üye yok!",
                parse_mode='Markdown',
                reply_markup=get_admin_keyboard()
            )
            return
        chunk_size = 10
        for i in range(0, len(users_list), chunk_size):
            chunk = users_list[i:i + chunk_size]
            message = f"👥 *Üye Listesi* 👥\n\n" + "\n".join(chunk)
            await update.message.reply_text(
                message,
                parse_mode='Markdown',
                reply_markup=get_member_management_keyboard()
            )
        context.user_data["managing_members"] = True
        context.user_data["management_step"] = MEMBER_MANAGEMENT_STEPS["waiting"]

    elif context.user_data.get("managing_members"):
        if text == "🔙 Geri Git":
            context.user_data["managing_members"] = False
            context.user_data["management_step"] = MEMBER_MANAGEMENT_STEPS["waiting"]
            context.user_data.pop("target_user", None)
            context.user_data.pop("balance_action", None)
            await update.message.reply_text(
                "❌ Üye yönetimi iptal edildi.",
                parse_mode='Markdown',
                reply_markup=get_admin_keyboard()
            )
            return
        step = context.user_data.get("management_step", MEMBER_MANAGEMENT_STEPS["waiting"])
        if step == MEMBER_MANAGEMENT_STEPS["waiting"]:
            if text == "➕ Puan Ekle" or text == "➖ Puan Düş":
                context.user_data["balance_action"] = "add" if text == "➕ Puan Ekle" else "subtract"
                await update.message.reply_text(
                    "👤 Düzenlemek istediğiniz üyenin Telegram kullanıcı adını yazın\n"
                    "Örnek: @kullaniciadi\n\n"
                    "İptal etmek için '🔙 Geri Git' butonuna basın.",
                    parse_mode='Markdown',
                    reply_markup=get_member_management_keyboard()
                )
                context.user_data["management_step"] = MEMBER_MANAGEMENT_STEPS["username"]
            else:
                await update.message.reply_text(
                    "❌ Lütfen geçerli bir işlem seçin!\n"
                    "➕ Puan Ekle veya ➖ Puan Düş\n\n"
                    "İptal etmek için '🔙 Geri Git' butonuna basın.",
                    parse_mode='Markdown',
                    reply_markup=get_member_management_keyboard()
                )
        elif step == MEMBER_MANAGEMENT_STEPS["username"]:
            if not text.startswith("@"):
                await update.message.reply_text(
                    "❌ Lütfen geçerli bir kullanıcı adı girin!\n"
                    "Örnek: @kullaniciadi\n\n"
                    "İptal etmek için '🔙 Geri Git' butonuna basın.",
                    parse_mode='Markdown',
                    reply_markup=get_member_management_keyboard()
                )
                return
            target_username = text[1:]
            target_user = None
            for uid in user_roles.keys():
                try:
                    user = await context.bot.get_chat(uid)
                    if user.username and user.username.lower() == target_username.lower():
                        target_user = user
                        break
                except Exception:
                    continue
            if not target_user:
                await update.message.reply_text(
                    "❌ Kullanıcı bulunamadı!\n"
                    "Lütfen doğru kullanıcı adını girdiğinizden emin olun.\n\n"
                    "İptal etmek için '🔙 Geri Git' butonuna basın.",
                    parse_mode='Markdown',
                    reply_markup=get_member_management_keyboard()
                )
                return
            if target_user.id == ADMIN_ID:
                await update.message.reply_text(
                    "❌ Admin hesabının bakiyesi düzenlenemez!\n\n"
                    "İptal etmek için '🔙 Geri Git' butonuna basın.",
                    parse_mode='Markdown',
                    reply_markup=get_member_management_keyboard()
                )
                return
            context.user_data["target_user"] = target_user
            action = context.user_data["balance_action"]
            action_text = "eklemek" if action == "add" else "düşmek"
            await update.message.reply_text(
                f"💰 {target_user.first_name} kullanıcısına kaç DMND puanı {action_text} istiyorsunuz?\n"
                "Lütfen bir sayı girin.\n\n"
                "İptal etmek için '🔙 Geri Git' butonuna basın.",
                parse_mode='Markdown',
                reply_markup=get_member_management_keyboard()
            )
            context.user_data["management_step"] = MEMBER_MANAGEMENT_STEPS["amount"]
        elif step == MEMBER_MANAGEMENT_STEPS["amount"]:
            try:
                amount = int(text)
                if amount <= 0:
                    raise ValueError("Amount must be positive")
                target_user = context.user_data["target_user"]
                action = context.user_data["balance_action"]
                current_points = db.get_user_points(target_user.id)
                if action == "add":
                    db.set_user_points(target_user.id, current_points + amount)
                    action_text = "eklendi"
                else:
                    if amount > current_points:
                        raise ValueError("Insufficient points")
                    db.set_user_points(target_user.id, current_points - amount)
                    action_text = "düşüldü"
                await update.message.reply_text(
                    f"✅ Puan düzenleme başarılı!\n\n"
                    f"👤 Kullanıcı: @{target_user.username}\n"
                    f"💰 {amount} DMND puanı {action_text}\n"
                    f"💎 Yeni bakiye: {db.get_user_points(target_user.id)} DMND",
                    parse_mode='Markdown',
                    reply_markup=get_admin_keyboard()
                )
                await context.bot.send_message(
                    target_user.id,
                    f"💰 *Bakiye Değişikliği* 💰\n\n"
                    f"👤 Admin tarafından bakiyeniz düzenlendi\n"
                    f"💰 {amount} DMND puanı {action_text}\n"
                    f"💎 Yeni bakiyeniz: {db.get_user_points(target_user.id)} DMND",
                    parse_mode='Markdown'
                )
            except ValueError as e:
                error_message = "❌ Lütfen geçerli bir sayı girin!\n\n" if str(e) == "Amount must be positive" else "❌ Kullanıcının yeterli puanı yok!\n\n"
                await update.message.reply_text(
                    f"{error_message}"
                    f"Mevcut puan: {current_points} DMND\n\n"
                    "İptal etmek için '🔙 Geri Git' butonuna basın.",
                    parse_mode='Markdown',
                    reply_markup=get_member_management_keyboard()
                )
            finally:
                context.user_data["managing_members"] = False
                context.user_data["management_step"] = MEMBER_MANAGEMENT_STEPS["waiting"]

    elif text == "💸 Puan Transfer":
        context.user_data["transferring_points"] = True
        context.user_data["transfer_step"] = TRANSFER_STEPS["username"]
        await update.message.reply_text(
            "💸 *Puan Transfer* 💸\n\n"
            "1️⃣ Adım: Puan göndermek istediğin kişinin Telegram kullanıcı adını yazın\n"
            "Örnek: @kullaniciadi\n\n"
            "İptal etmek için '🔙 Geri Git' butonuna basın.",
            parse_mode='Markdown',
            reply_markup=get_transfer_keyboard()
        )

    elif text == "➕ Çekiliş Oluştur":
        if user_id != ADMIN_ID:
            await update.message.reply_text("Sadece Adminler kullanabilir!", reply_markup=get_main_keyboard())
            return
        # Diğer yönetim state'lerini temizle
        context.user_data["creating_giveaway"] = True
        context.user_data["giveaway_step"] = GIVEAWAY_STEPS["reward"]
        context.user_data["reward"] = None
        context.user_data["cost"] = None
        context.user_data["winners"] = None
        context.user_data["managing_members"] = False
        context.user_data["management_step"] = MEMBER_MANAGEMENT_STEPS["waiting"]
        context.user_data["target_user"] = None
        context.user_data["balance_action"] = None
        await update.message.reply_text(
            "🎉 *Çekiliş Oluşturma* 🎉\n\n"
            "1️⃣ Adım: Çekiliş ödülünü DMND puanı olarak yazın\n"
            "Örnek: 1000\n\n"
            "İptal etmek için '❌ İptal' butonuna basın.",
            parse_mode='Markdown',
            reply_markup=get_giveaway_keyboard()
        )

    elif context.user_data.get("creating_giveaway"):
        if text == "🔙 Geri Git":
            context.user_data["creating_giveaway"] = False
            context.user_data["giveaway_step"] = GIVEAWAY_STEPS["waiting"]
            context.user_data.pop("reward", None)
            context.user_data.pop("cost", None)
            context.user_data.pop("winners", None)
            await update.message.reply_text(
                "❌ Çekiliş oluşturma iptal edildi.",
                parse_mode='Markdown',
                reply_markup=get_admin_keyboard()
            )
            return
        step = context.user_data.get("giveaway_step", GIVEAWAY_STEPS["reward"])
        if step == GIVEAWAY_STEPS["reward"]:
            try:
                reward = int(text)
                if reward <= 0:
                    raise ValueError("Ödül miktarı 0'dan büyük olmalıdır")
                context.user_data["reward"] = reward
                context.user_data["giveaway_step"] = GIVEAWAY_STEPS["points"]
                await update.message.reply_text(
                    "2️⃣ Adım: Katılım için gereken DMND puanını yazın\n"
                    "Örnek: 50\n\n"
                    "İptal etmek için '🔙 Geri Git' butonuna basın.",
                    parse_mode='Markdown',
                    reply_markup=get_giveaway_keyboard()
                )
            except ValueError:
                await update.message.reply_text(
                    "❌ Lütfen geçerli bir sayı girin!\n"
                    "Sayı 0'dan büyük olmalıdır.\n\n"
                    "İptal etmek için '🔙 Geri Git' butonuna basın.",
                    parse_mode='Markdown',
                    reply_markup=get_giveaway_keyboard()
                )
        elif step == GIVEAWAY_STEPS["points"]:
            try:
                points = int(text)
                if points <= 0:
                    raise ValueError("Points must be positive")
                context.user_data["cost"] = points
                context.user_data["giveaway_step"] = GIVEAWAY_STEPS["winners"]
                await update.message.reply_text(
                    "3️⃣ Adım: Kaç kişi kazanacak?\n"
                    "Örnek: 3\n\n"
                    "İptal etmek için '🔙 Geri Git' butonuna basın.",
                    parse_mode='Markdown',
                    reply_markup=get_giveaway_keyboard()
                )
            except ValueError:
                await update.message.reply_text(
                    "❌ Lütfen geçerli bir sayı girin!\n"
                    "Sayı 0'dan büyük olmalıdır.\n\n"
                    "İptal etmek için '🔙 Geri Git' butonuna basın.",
                    parse_mode='Markdown',
                    reply_markup=get_giveaway_keyboard()
                )
        elif step == GIVEAWAY_STEPS["winners"]:
            try:
                winners = int(text)
                if winners <= 0:
                    raise ValueError("Winner count must be positive")
                context.user_data["winners"] = winners
                context.user_data["giveaway_step"] = GIVEAWAY_STEPS["duration"]
                await update.message.reply_text(
                    "4️⃣ Adım: Çekilişin süresini saat cinsinden yazın\n"
                    "Örnek: 24 (24 saat)\n\n"
                    "İptal etmek için '🔙 Geri Git' butonuna basın.",
                    parse_mode='Markdown',
                    reply_markup=get_giveaway_keyboard()
                )
            except ValueError:
                await update.message.reply_text(
                    "❌ Lütfen geçerli bir sayı girin!\n"
                    "Sayı 0'dan büyük olmalıdır.\n\n"
                    "İptal etmek için '🔙 Geri Git' butonuna basın.",
                    parse_mode='Markdown',
                    reply_markup=get_giveaway_keyboard()
                )
        elif step == GIVEAWAY_STEPS["duration"]:
            try:
                duration = int(text)
                if duration <= 0:
                    raise ValueError("Duration must be positive")
                if not all(key in context.user_data for key in ["reward", "cost", "winners"]):
                    raise ValueError("Missing required data")
                reward = context.user_data["reward"]
                cost = context.user_data["cost"]
                winners = context.user_data["winners"]
                end_time = datetime.now() + timedelta(hours=duration)
                
                # Çekilişi veritabanına ekle
                giveaway_id = db.create_giveaway(f"{reward} DMND", cost, winners, end_time.strftime('%Y-%m-%d %H:%M:%S'))
                
                # Global veri yapısını güncelle
                new_giveaway = {
                    "id": giveaway_id,
                    "reward": f"{reward} DMND",
                    "cost": cost,
                    "winners": winners,
                    "end_time": end_time,
                    "participants": []
                }
                giveaways.append(new_giveaway)
                
                await update.message.reply_text(
                    f"✅ *Çekiliş Başarıyla Oluşturuldu!* ✅\n\n"
                    f"🏆 Ödül: {reward} DMND\n"
                    f"💰 Katılım Ücreti: {cost} DMND\n"
                    f"👥 Kazanan Sayısı: {winners} kişi\n"
                    f"⏰ Son Katılım: {end_time.strftime('%d.%m.%Y %H:%M')}",
                    parse_mode='Markdown',
                    reply_markup=get_admin_keyboard()
                )
                
                # Bildirim mesajını hazırla
                notification_message = (
                    "🎉 *YENİ ÇEKİLİŞ BAŞLADI!* 🎉\n\n"
                    f"🏆 *Ödül:* {reward} DMND\n"
                    f"💰 *Katılım Ücreti:* {cost} DMND\n"
                    f"👥 *Kazanan Sayısı:* {winners} kişi\n"
                    f"⏰ *Son Katılım:* {end_time.strftime('%d.%m.%Y %H:%M')}\n\n"
                    "🎯 Katılmak için '🎯 Etkinlikler' menüsünden '🎉 Çekilişe Katıl' butonuna tıklayın!"
                )
                
                # Bildirimleri gönder
                for user_id in user_roles.keys():
                    if user_id != ADMIN_ID:
                        try:
                            await context.bot.send_message(
                                user_id,
                                notification_message,
                                parse_mode='Markdown'
                            )
                        except Exception as e:
                            logging.error(f"Error sending notification to user {user_id}: {e}")
                
                # Job queue için async wrapper kullan
                context.job_queue.run_once(
                    check_giveaways_job,
                    end_time - datetime.now(),
                    data=new_giveaway
                )
                
            except ValueError as e:
                error_message = str(e)
                if "Duration must be positive" in error_message:
                    error_message = "❌ Lütfen geçerli bir süre girin!\nSayı 0'dan büyük olmalıdır."
                elif "Missing required data" in error_message:
                    error_message = "❌ Eksik bilgi! Lütfen tüm adımları tekrar tamamlayın."
                else:
                    error_message = "❌ Bir hata oluştu! Lütfen tekrar deneyin."
                
                await update.message.reply_text(
                    f"{error_message}\n\n"
                    "İptal etmek için '🔙 Geri Git' butonuna basın.",
                    parse_mode='Markdown',
                    reply_markup=get_giveaway_keyboard()
                )
            except Exception as e:
                logging.error(f"Error creating giveaway: {e}")
                await update.message.reply_text(
                    "❌ Çekiliş oluşturulurken bir hata oluştu! Lütfen tekrar deneyin.",
                    parse_mode='Markdown',
                    reply_markup=get_giveaway_keyboard()
                )
            finally:
                context.user_data["creating_giveaway"] = False
                context.user_data["giveaway_step"] = GIVEAWAY_STEPS["waiting"]
                context.user_data.pop("reward", None)
                context.user_data.pop("cost", None)
                context.user_data.pop("winners", None)

    elif context.user_data.get("ending_giveaway"):
        if text == "🔙 Geri Git":
            context.user_data["ending_giveaway"] = False
            await update.message.reply_text(
                "❌ Çekiliş bitirme işlemi iptal edildi.",
                parse_mode='Markdown',
                reply_markup=get_admin_keyboard()
            )
            return
        if text.isdigit():
            giveaway_index = int(text) - 1
            if 0 <= giveaway_index < len(giveaways):
                giveaway = giveaways[giveaway_index]
                participants = giveaway["participants"]
                if participants:
                    random.shuffle(participants)
                    winner_count = min(giveaway["winners"], len(participants))
                    winners = participants[:winner_count]
                    reward_amount = int(giveaway["reward"].split()[0])
                    prize_points = reward_amount // winner_count
                    for winner_id in winners:
                        current_points = db.get_user_points(winner_id)
                        db.set_user_points(winner_id, current_points + prize_points)
                    completed_giveaway = {
                        "reward": giveaway["reward"],
                        "winners": [await context.bot.get_chat(winner_id) for winner_id in winners],
                        "winner_ids": winners,
                        "prize_points": prize_points,
                        "participants_count": len(participants),
                        "end_time": datetime.now()
                    }
                    db.add_completed_giveaway(completed_giveaway)
                    result_message = (
                        "✅ *ÇEKİLİŞ SONUÇLARI* ✅\n\n"
                        f"🏆 *Ödül:* {giveaway['reward']}\n"
                        f"👑 *Kazananlar:*\n" + 
                        "\n".join([f"• {await context.bot.get_chat(winner_id).first_name} (@{await context.bot.get_chat(winner_id).username}) (ID: `{winner_id}`)" for winner_id in winners]) + "\n" +
                        f"💰 *Kazanılan:* {prize_points} DMND (her kazanan için)\n"
                        f"👥 *Toplam Katılımcı:* {len(participants)}\n"
                        f"⏰ *Bitiş Tarihi:* {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                        "🎊 *Tebrikler Kazananlarımıza!* 🎊"
                    )
                    for winner_id in winners:
                        winner = await context.bot.get_chat(winner_id)
                        current_points = db.get_user_points(winner_id) - prize_points
                        db.set_user_points(winner_id, current_points)
                        await context.bot.send_message(
                            winner_id,
                            f"🎉 *Tebrikler!* 🎉\n\n"
                            f"🏆 {giveaway['reward']} çekilişini kazandın!\n"
                            f"💰 Ödül olarak {prize_points} DMND Puanı hesabına eklendi!\n"
                            f"💎 Eski puan durumun: {current_points} DMND\n"
                            f"💎 Yeni puan durumun: {db.get_user_points(winner_id)} DMND\n\n"
                            "🎊 *Kutluyoruz!* 🎊",
                            parse_mode='Markdown'
                        )
                    for participant_id in participants:
                        if participant_id not in winners:
                            await context.bot.send_message(participant_id, result_message, parse_mode='Markdown')
                    await update.message.reply_text(
                        f"✅ Çekiliş başarıyla sonlandırıldı!\n\n{result_message}",
                        parse_mode='Markdown',
                        reply_markup=get_admin_keyboard()
                    )
                    db.delete_giveaway(giveaway_index)
                else:
                    await update.message.reply_text(
                        "❌ Bu çekilişte hiç katılımcı yok!",
                        parse_mode='Markdown',
                        reply_markup=get_admin_keyboard()
                    )
            else:
                await update.message.reply_text(
                    "❌ Geçersiz çekiliş numarası!",
                    parse_mode='Markdown',
                    reply_markup=get_admin_keyboard()
                )
            context.user_data["ending_giveaway"] = False

    elif text.isdigit() and not context.user_data.get("ending_giveaway") and 1 <= int(text) <= len(giveaways):
        try:
            giveaway_index = int(text) - 1
            giveaway = giveaways[giveaway_index]
            # giveaway bir dict ise, id ile katılımcıları çek
            giveaway_id = giveaway["id"] if isinstance(giveaway, dict) else giveaway[0]
            participants = db.get_participants(giveaway_id)
            
            # Kullanıcı puanını çek
            points = db.get_user_points(user_id)
            if points is None:
                logging.error(f"Kullanıcı puanı alınamadı: {user_id}")
                raise ValueError("Kullanıcı puanı alınamadı")

            # Çekiliş bitiş zamanı kontrolü
            end_time = giveaway["end_time"] if isinstance(giveaway, dict) else giveaway[4]
            if datetime.now() >= end_time:
                await update.message.reply_text(
                    "❌ Bu çekilişin süresi dolmuş!",
                    parse_mode='Markdown',
                    reply_markup=get_main_keyboard()
                )
                return

            # Katılım kontrolü
            if user_id in participants:
                await update.message.reply_text(
                    "❌ Bu çekilişe zaten katılmışsın!",
                    parse_mode='Markdown',
                    reply_markup=get_main_keyboard()
                )
                return

            # Puan kontrolü ve katılım
            cost = giveaway["cost"] if isinstance(giveaway, dict) else giveaway[2]
            if points >= cost:
                try:
                    db.set_user_points(user_id, points - cost)
                    db.add_participant(giveaway_id, user_id)
                    await update.message.reply_text(
                        f"✅ Çekiliş {giveaway_index+1}'e katıldın!\n"
                        f"💰 {cost} DMND Puanı düşüldü.\n"
                        f"💎 Kalan puanın: {db.get_user_points(user_id)} DMND",
                        parse_mode='Markdown',
                        reply_markup=get_main_keyboard()
                    )
                except Exception as e:
                    logging.error(f"Çekilişe katılım hatası (user {user_id}): {e}")
                    # Hata durumunda puanları geri yükle
                    try:
                        db.set_user_points(user_id, points)
                    except Exception:
                        pass
                    await update.message.reply_text(
                        "❌ Çekilişe katılırken bir hata oluştu. Lütfen daha sonra tekrar deneyin.",
                        parse_mode='Markdown',
                        reply_markup=get_main_keyboard()
                    )
            else:
                await update.message.reply_text(
                    f"❌ Bu çekilişe katılmak için yeterli DMND Puanın yok!\n"
                    f"💰 Gerekli: {cost} DMND\n"
                    f"💎 Mevcut: {points} DMND",
                    parse_mode='Markdown',
                    reply_markup=get_main_keyboard()
                )
        except Exception as e:
            logging.error(f"Çekilişe katılımda genel hata: {e}")
            await update.message.reply_text(
                "❌ Çekilişe katılırken bir hata oluştu. Lütfen daha sonra tekrar deneyin.",
                parse_mode='Markdown',
                reply_markup=get_main_keyboard()
            )

    elif context.user_data.get("transferring_points"):
        if text == "🔙 Geri Git":
            context.user_data["transferring_points"] = False
            context.user_data["transfer_step"] = TRANSFER_STEPS["waiting"]
            context.user_data.pop("target_username", None)
            await update.message.reply_text(
                "❌ Puan transfer işlemi iptal edildi.",
                parse_mode='Markdown',
                reply_markup=get_points_keyboard()
            )
            return
        step = context.user_data.get("transfer_step", TRANSFER_STEPS["username"])
        if step == TRANSFER_STEPS["username"]:
            if not text.startswith("@"):
                await update.message.reply_text(
                    "❌ Lütfen geçerli bir kullanıcı adı girin!\n"
                    "Örnek: @kullaniciadi\n\n"
                    "İptal etmek için '🔙 Geri Git' butonuna basın.",
                    parse_mode='Markdown',
                    reply_markup=get_transfer_keyboard()
                )
                return
            target_username = text[1:]
            context.user_data["target_username"] = target_username
            context.user_data["transfer_step"] = TRANSFER_STEPS["amount"]
            await update.message.reply_text(
                "2️⃣ Adım: Göndermek istediğin DMND puanı miktarını yazın\n"
                "Örnek: 50\n\n"
                "İptal etmek için '🔙 Geri Git' butonuna basın.",
                parse_mode='Markdown',
                reply_markup=get_transfer_keyboard()
            )
        elif step == TRANSFER_STEPS["amount"]:
            try:
                amount = int(text)
                if amount <= 0:
                    raise ValueError("Amount must be positive")
                sender_points = db.get_user_points(user_id)
                if amount > sender_points:
                    await update.message.reply_text(
                        f"❌ Yeterli puanın yok!\n"
                        f"Mevcut puanın: {sender_points} DMND\n\n"
                        "İptal etmek için '🔙 Geri Git' butonuna basın.",
                        parse_mode='Markdown',
                        reply_markup=get_transfer_keyboard()
                    )
                    return
                target_username = context.user_data["target_username"]
                target_user = None
                for uid in user_roles.keys():
                    try:
                        user = await context.bot.get_chat(uid)
                        if user.username and user.username.lower() == target_username.lower():
                            target_user = user
                            break
                    except Exception:
                        continue
                if not target_user:
                    await update.message.reply_text(
                        "❌ Kullanıcı bulunamadı!\n"
                        "Lütfen doğru kullanıcı adını girdiğinizden emin olun.\n\n"
                        "İptal etmek için '🔙 Geri Git' butonuna basın.",
                        parse_mode='Markdown',
                        reply_markup=get_transfer_keyboard()
                    )
                    return
                if target_user.id == user_id:
                    await update.message.reply_text(
                        "❌ Kendine puan transfer edemezsin!\n\n"
                        "İptal etmek için '🔙 Geri Git' butonuna basın.",
                        parse_mode='Markdown',
                        reply_markup=get_transfer_keyboard()
                    )
                    return
                db.set_user_points(user_id, sender_points - amount)
                db.set_user_points(target_user.id, db.get_user_points(target_user.id) + amount)
                keyboard = get_admin_keyboard() if user_id == ADMIN_ID else get_main_keyboard()
                await update.message.reply_text(
                    f"✅ Puan transferi başarılı!\n\n"
                    f"👤 Alıcı: @{target_username}\n"
                    f"💰 Transfer: {amount} DMND\n"
                    f"💎 Kalan puanın: {db.get_user_points(user_id)} DMND",
                    parse_mode='Markdown',
                    reply_markup=keyboard
                )
                await context.bot.send_message(
                    target_user.id,
                    f"💰 *Yeni Puan Transferi* 💰\n\n"
                    f"👤 Gönderen: {update.effective_user.first_name}\n"
                    f"💰 Miktar: {amount} DMND\n"
                    f"💎 Yeni bakiyen: {db.get_user_points(target_user.id)} DMND",
                    parse_mode='Markdown'
                )
            except ValueError:
                await update.message.reply_text(
                    "❌ Lütfen geçerli bir sayı girin!\n\n"
                    "İptal etmek için '🔙 Geri Git' butonuna basın.",
                    parse_mode='Markdown',
                    reply_markup=get_transfer_keyboard()
                )
            finally:
                context.user_data["transferring_points"] = False
                context.user_data["transfer_step"] = TRANSFER_STEPS["waiting"]

    elif context.user_data.get("requesting_points"):
        if text == "🔙 Geri Git":
            context.user_data["requesting_points"] = False
            context.user_data["request_step"] = POINT_REQUEST_STEPS["waiting"]
            context.user_data.pop("wallet_address", None)
            await update.message.reply_text(
                "❌ Puan talep işlemi iptal edildi.",
                parse_mode='Markdown',
                reply_markup=get_points_keyboard()
            )
            return
        step = context.user_data.get("request_step", POINT_REQUEST_STEPS["wallet"])
        if step == POINT_REQUEST_STEPS["wallet"]:
            if not text.startswith("0x") or len(text) != 42:
                await update.message.reply_text(
                    "❌ Lütfen geçerli bir cüzdan adresi girin!\n"
                    "Örnek: 0x1234...\n\n"
                    "İptal etmek için '🔙 Geri Git' butonuna basın.",
                    parse_mode='Markdown',
                    reply_markup=get_point_request_keyboard()
                )
                return
            context.user_data["wallet_address"] = text
            context.user_data["request_step"] = POINT_REQUEST_STEPS["amount"]
            await update.message.reply_text(
                "2️⃣ Adım: Gönderdiğiniz DMND Token miktarını yazın\n"
                "Örnek: 100\n\n"
                "İptal etmek için '🔙 Geri Git' butonuna basın.",
                parse_mode='Markdown',
                reply_markup=get_point_request_keyboard()
            )
        elif step == POINT_REQUEST_STEPS["amount"]:
            try:
                amount = int(text)
                if amount <= 0:
                    raise ValueError("Amount must be positive")
                wallet_address = context.user_data["wallet_address"]
                user = update.effective_user
                db.add_point_request({
                    "user_id": user.id,
                    "wallet_address": wallet_address,
                    "amount": amount,
                    "date": datetime.now()
                })
                admin_message = (
                    "📝 *Yeni Puan Talebi* 📝\n\n"
                    f"👤 *Kullanıcı:* {user.first_name} (@{user.username})\n"
                    f"🆔 *ID:* `{user.id}`\n"
                    f"📬 *Cüzdan:* `{wallet_address}`\n"
                    f"💰 *Miktar:* {amount} DMND Token\n"
                    f"⏰ *Tarih:* {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                )
                db.add_admin_message(admin_message)
                await update.message.reply_text(
                    "✅ *Puan Talebiniz Alındı!* ✅\n\n"
                    "📝 Talebiniz admin tarafından incelenecektir.\n"
                    "Onaylandığında puanlarınız otomatik olarak hesabınıza eklenecektir.",
                    parse_mode='Markdown',
                    reply_markup=get_points_keyboard()
                )
            except ValueError:
                await update.message.reply_text(
                    "❌ Lütfen geçerli bir sayı girin!\n"
                    "Sayı 0'dan büyük olmalıdır.\n\n"
                    "İptal etmek için '🔙 Geri Git' butonuna basın.",
                    parse_mode='Markdown',
                    reply_markup=get_point_request_keyboard()
                )
            finally:
                context.user_data["requesting_points"] = False
                context.user_data["request_step"] = POINT_REQUEST_STEPS["waiting"]

    elif text == "📝 Talepler":
        if user_id != ADMIN_ID:
            await update.message.reply_text("Sadece Adminler kullanabilir!", reply_markup=get_main_keyboard())
            return
        if not db.get_pending_requests():
            await update.message.reply_text(
                "📝 *Bekleyen Puan Talebi Yok* 📝\n\n"
                "Şu anda bekleyen puan talebi bulunmuyor.",
                parse_mode='Markdown',
                reply_markup=get_admin_keyboard()
            )
            return
        requests_list = []
        for i, request in enumerate(db.get_pending_requests(), 1):
            try:
                user = await context.bot.get_chat(request["user_id"])
                requests_list.append(
                    f"📝 *Talep #{i}*\n"
                    f"👤 *Kullanıcı:* {user.first_name} (@{user.username})\n"
                    f"🆔 *ID:* `{user.id}`\n"
                    f"📬 *Cüzdan:* `{request['wallet_address']}`\n"
                    f"💰 *Miktar:* {request['amount']} DMND Token\n"
                    f"⏰ *Tarih:* {request['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
                )
            except Exception as e:
                logging.error(f"Error getting user info for request {i}: {e}")
                continue
        chunk_size = 5
        for i in range(0, len(requests_list), chunk_size):
            chunk = requests_list[i:i + chunk_size]
            message = "📝 *Bekleyen Puan Talepleri* 📝\n\n" + "\n".join(chunk)
            await update.message.reply_text(
                message,
                parse_mode='Markdown',
                reply_markup=get_request_management_keyboard()
            )
        context.user_data["managing_requests"] = True

    elif context.user_data.get("managing_requests"):
        if text == "🔙 Geri Git":
            context.user_data["managing_requests"] = False
            await update.message.reply_text(
                "❌ Talep yönetimi iptal edildi.",
                parse_mode='Markdown',
                reply_markup=get_admin_keyboard()
            )
            return
        if text == "✅ Onayla" or text == "❌ Reddet":
            if not db.get_pending_requests():
                await update.message.reply_text(
                    "❌ İşlenecek talep kalmadı!",
                    parse_mode='Markdown',
                    reply_markup=get_admin_keyboard()
                )
                context.user_data["managing_requests"] = False
                return
            request = db.get_pending_requests()[0]
            user_id = request["user_id"]
            amount = request["amount"]
            wallet_address = request["wallet_address"]
            try:
                user = await context.bot.get_chat(user_id)
                if text == "✅ Onayla":
                    current_points = db.get_user_points(user_id)
                    db.set_user_points(user_id, current_points + amount)
                    await context.bot.send_message(
                        user_id,
                        f"✅ *Puan Talebiniz Onaylandı!* ✅\n\n"
                        f"💰 {amount} DMND puanı hesabınıza eklendi!\n"
                        f"💎 Yeni bakiyeniz: {db.get_user_points(user_id)} DMND",
                        parse_mode='Markdown'
                    )
                    await update.message.reply_text(
                        f"✅ *Talep Onaylandı* ✅\n\n"
                        f"👤 Kullanıcı: {user.first_name} (@{user.username})\n"
                        f"💰 Miktar: {amount} DMND\n"
                        f"💎 Yeni bakiye: {db.get_user_points(user_id)} DMND",
                        parse_mode='Markdown',
                        reply_markup=get_request_management_keyboard()
                    )
                else:
                    await context.bot.send_message(
                        user_id,
                        f"❌ *Puan Talebiniz Reddedildi* ❌\n\n"
                        f"📬 Cüzdan: `{wallet_address}`\n"
                        f"💰 Miktar: {amount} DMND Token\n\n"
                        "❓ Detaylı bilgi için admin ile iletişime geçin.",
                        parse_mode='Markdown'
                    )
                    await update.message.reply_text(
                        f"❌ *Talep Reddedildi* ❌\n\n"
                        f"👤 Kullanıcı: {user.first_name} (@{user.username})\n"
                        f"💰 Miktar: {amount} DMND Token",
                        parse_mode='Markdown',
                        reply_markup=get_request_management_keyboard()
                    )
                db.add_processed_request({
                    **request,
                    "status": "approved" if text == "✅ Onayla" else "rejected",
                    "processed_date": datetime.now()
                })
                db.delete_point_request(request["_id"])
                if not db.get_pending_requests():
                    await update.message.reply_text(
                        "📝 *Tüm Talepler İşlendi* 📝\n\n"
                        "Bekleyen başka talep kalmadı.",
                        parse_mode='Markdown',
                        reply_markup=get_admin_keyboard()
                    )
                    context.user_data["managing_requests"] = False
                else:
                    requests_list = []
                    for i, req in enumerate(db.get_pending_requests(), 1):
                        try:
                            usr = await context.bot.get_chat(req["user_id"])
                            requests_list.append(
                                f"📝 *Talep #{i}*\n"
                                f"👤 *Kullanıcı:* {usr.first_name} (@{usr.username})\n"
                                f"🆔 *ID:* `{usr.id}`\n"
                                f"📬 *Cüzdan:* `{req['wallet_address']}`\n"
                                f"💰 *Miktar:* {req['amount']} DMND Token\n"
                                f"⏰ *Tarih:* {req['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
                            )
                        except Exception as e:
                            logging.error(f"Error getting user info for request {i}: {e}")
                            continue
                    chunk_size = 5
                    for i in range(0, len(requests_list), chunk_size):
                        chunk = requests_list[i:i + chunk_size]
                        message = "📝 *Kalan Bekleyen Talepler* 📝\n\n" + "\n".join(chunk)
                        await update.message.reply_text(
                            message,
                            parse_mode='Markdown',
                            reply_markup=get_request_management_keyboard()
                        )
            except Exception as e:
                logging.error(f"Error processing request: {e}")
                await update.message.reply_text(
                    "❌ Talep işlenirken bir hata oluştu!",
                    parse_mode='Markdown',
                    reply_markup=get_admin_keyboard()
                )
                context.user_data["managing_requests"] = False

    elif text == "📢 Duyuru":
        if user_id != ADMIN_ID:
            await update.message.reply_text("Sadece Adminler kullanabilir!", reply_markup=get_main_keyboard())
            return
        context.user_data["sending_announcement"] = True
        context.user_data["announcement_step"] = ANNOUNCEMENT_STEPS["text"]
        await update.message.reply_text(
            "📢 *Duyuru Gönderme* 📢\n\n"
            "Lütfen göndermek istediğiniz duyuru metnini yazın.\n"
            "Mesajınız Markdown formatında olabilir.\n\n"
            "Örnek format:\n"
            "*Kalın*\n"
            "_İtalik_\n"
            "`Kod`\n"
            "[Link](url)\n\n"
            "Metni yazdıktan sonra, isterseniz bir resim gönderebilirsiniz.\n"
            "İptal etmek için '🔙 Geri Git' butonuna basın.",
            parse_mode='Markdown',
            reply_markup=get_announcement_keyboard()
        )

    elif context.user_data.get("sending_announcement"):
        if text == "🔙 Geri Git":
            context.user_data["sending_announcement"] = False
            context.user_data["announcement_step"] = ANNOUNCEMENT_STEPS["waiting"]
            context.user_data.pop("announcement_text", None)
            context.user_data.pop("announcement_photo", None)
            await update.message.reply_text(
                "❌ Duyuru gönderme iptal edildi.",
                parse_mode='Markdown',
                reply_markup=get_admin_keyboard()
            )
            return
        step = context.user_data.get("announcement_step", ANNOUNCEMENT_STEPS["text"])
        if step == ANNOUNCEMENT_STEPS["text"]:
            context.user_data["announcement_text"] = text
            context.user_data["announcement_step"] = ANNOUNCEMENT_STEPS["image"]
            await update.message.reply_text(
                "✅ Duyuru metni kaydedildi.\n\n"
                "İsterseniz bir resim gönderebilirsiniz.\n"
                "Resim göndermek istemiyorsanız, duyuruyu göndermek için '🔙 Geri Git' butonuna basın.",
                parse_mode='Markdown',
                reply_markup=get_announcement_keyboard()
            )

    elif update.message.photo and context.user_data.get("sending_announcement"):
        if context.user_data.get("announcement_step") == ANNOUNCEMENT_STEPS["image"]:
            photo = update.message.photo[-1]
            context.user_data["announcement_photo"] = photo
            await send_announcement(update, context, context.user_data["announcement_text"], photo)

    elif text == "📢 Duyurular":
        if not db.get_announcements():
            await update.message.reply_text(
                "📢 *Henüz Duyuru Yok* 📢\n\n"
                "Şu anda görüntülenecek duyuru bulunmuyor.",
                parse_mode='Markdown',
                reply_markup=get_main_keyboard()
            )
            return
        sorted_announcements = sorted(db.get_announcements(), key=lambda x: x["date"], reverse=True)
        recent_announcements = sorted_announcements[:5]
        announcement_list = []
        for i, announcement in enumerate(recent_announcements, 1):
            try:
                date_str = announcement["date"].strftime("%d.%m.%Y %H:%M")
                announcement_list.append(
                    f"📢 *Duyuru #{i}*\n"
                    f"⏰ *Tarih:* {date_str}\n"
                    f"📝 *İçerik:*\n{announcement['text']}\n"
                )
            except Exception as e:
                logging.error(f"Error formatting announcement {i}: {e}")
                continue
        context.user_data["viewing_announcements"] = True
        await update.message.reply_text(
            "📢 *Son Duyurular* 📢\n\n" + "\n".join(announcement_list),
            parse_mode='Markdown',
            reply_markup=get_announcement_list_keyboard()
        )

    elif text == "🔄 Yenile" and context.user_data.get("viewing_announcements"):
        if not db.get_announcements():
            await update.message.reply_text(
                "📢 *Henüz Duyuru Yok* 📢\n\n"
                "Şu anda görüntülenecek duyuru bulunmuyor.",
                parse_mode='Markdown',
                reply_markup=get_main_keyboard()
            )
            context.user_data["viewing_announcements"] = False
            return
        sorted_announcements = sorted(db.get_announcements(), key=lambda x: x["date"], reverse=True)
        recent_announcements = sorted_announcements[:5]
        announcement_list = []
        for i, announcement in enumerate(recent_announcements, 1):
            try:
                date_str = announcement["date"].strftime("%d.%m.%Y %H:%M")
                announcement_list.append(
                    f"📢 *Duyuru #{i}*\n"
                    f"⏰ *Tarih:* {date_str}\n"
                    f"📝 *İçerik:*\n{announcement['text']}\n"
                )
            except Exception as e:
                logging.error(f"Error formatting announcement {i}: {e}")
                continue
        await update.message.reply_text(
            "📢 *Son Duyurular* 📢\n\n" + "\n".join(announcement_list),
            parse_mode='Markdown',
            reply_markup=get_announcement_list_keyboard()
        )

async def send_announcement(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, photo=None):
    try:
        announcement = (
            "📢 *DUYURU* 📢\n\n"
            f"{text}\n\n"
            "💡 Bu bir otomatik duyuru mesajıdır."
        )
        announcement_data = {
            "text": text,
            "photo": photo.file_id if photo else None,
            "date": datetime.now(),
            "sent_by": update.effective_user.id
        }
        db.add_announcement(announcement_data)
        await update.message.reply_text(
            "📢 *Duyuru Gönderiliyor...* 📢\n\n"
            "Lütfen bekleyin, tüm kullanıcılara, gruplara ve kanallara gönderiliyor...",
            parse_mode='Markdown',
            reply_markup=get_announcement_keyboard()
        )
        sent_count = 0
        failed_count = 0
        chat_ids = set()
        for user_id in list(user_roles.keys()):
            if user_id != ADMIN_ID:
                try:
                    if photo:
                        await context.bot.send_photo(
                            user_id,
                            photo=photo.file_id,
                            caption=announcement,
                            parse_mode='Markdown'
                        )
                    else:
                        await context.bot.send_message(
                            user_id,
                            announcement,
                            parse_mode='Markdown'
                        )
                    sent_count += 1
                    chat_ids.add(user_id)
                except Exception as e:
                    logging.error(f"Error sending announcement to user {user_id}: {e}")
                    failed_count += 1
                    continue
        try:
            updates = await context.bot.get_updates()
            for update in updates:
                if update.message and update.message.chat:
                    chat = update.message.chat
                    if chat.type in ['group', 'supergroup', 'channel'] and chat.id not in chat_ids:
                        try:
                            if photo:
                                await context.bot.send_photo(
                                    chat.id,
                                    photo=photo.file_id,
                                    caption=announcement,
                                    parse_mode='Markdown'
                                )
                            else:
                                await context.bot.send_message(
                                    chat.id,
                                    announcement,
                                    parse_mode='Markdown'
                                )
                            sent_count += 1
                            chat_ids.add(chat.id)
                        except Exception as e:
                            logging.error(f"Error sending announcement to chat {chat.id}: {e}")
                            failed_count += 1
                            continue
        except Exception as e:
            logging.error(f"Error retrieving updates for chats: {e}")
        result_message = (
            f"✅ *Duyuru Gönderildi* ✅\n\n"
            f"📊 *Sonuç:*\n"
            f"✅ Başarılı: {sent_count}\n"
            f"❌ Başarısız: {failed_count}\n\n"
            f"📢 *Gönderilen Duyuru:*\n{announcement}"
        )
        if photo:
            result_message += "\n🖼️ *Resim:* Gönderildi"
        await update.message.reply_text(
            result_message,
            parse_mode='Markdown',
            reply_markup=get_admin_keyboard()
        )
    except Exception as e:
        logging.error(f"Error in send_announcement: {e}")
        await update.message.reply_text(
            "❌ Duyuru gönderilirken bir hata oluştu. Lütfen tekrar deneyin.",
            parse_mode='Markdown',
            reply_markup=get_admin_keyboard()
        )
    finally:
        context.user_data["sending_announcement"] = False
        context.user_data["announcement_step"] = ANNOUNCEMENT_STEPS["waiting"]
        context.user_data.pop("announcement_text", None)
        context.user_data.pop("announcement_photo", None)

async def handle_referral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    if context.args and len(context.args) > 0:
        try:
            referrer_id = int(context.args[0])
            # Veritabanında kullanıcı var mı kontrol et
            referrer_points = db.get_user_points(referrer_id)
            if referrer_id != user_id and referrer_points is not None:
                if user_id not in user_roles:
                    db.set_user_points(user_id, 10)
                    db.set_user_role(user_id, "Admin" if user_id == ADMIN_ID else "User")
                    db.set_user_points(referrer_id, referrer_points + 1)
                    db.add_referral(referrer_id, user_id)
                    # user_roles sözlüğünü güncelle
                    user_roles[user_id] = "Admin" if user_id == ADMIN_ID else "User"
                    await context.bot.send_message(
                        referrer_id,
                        f"🎉 Biri senin referans linkini kullandı!\n"
                        f"💰 1 DMND Puanı kazandın!",
                        parse_mode='Markdown'
                    )
                    await update.message.reply_text(
                        f"🎉 *Hoş geldin, {user.first_name}!*\n\n"
                        f"💰 Katıldığın için 10 DMND Puanı kazandın!",
                        parse_mode='Markdown',
                        reply_markup=get_main_keyboard()
                    )
                else:
                    await update.message.reply_text(
                        "❌ Zaten bota katılmışsın!",
                        parse_mode='Markdown',
                        reply_markup=get_main_keyboard()
                    )
            else:
                await update.message.reply_text(
                    "❌ Geçersiz referans linki.",
                    parse_mode='Markdown',
                    reply_markup=get_main_keyboard()
                )
        except ValueError:
            await update.message.reply_text(
                "❌ Geçersiz referans linki.",
                parse_mode='Markdown',
                reply_markup=get_main_keyboard()
            )
    else:
        await start(update, context)

def main() -> None:
    application = Application.builder().token(TOKEN).build()
    application.job_queue.run_repeating(check_giveaways, interval=60, first=10)
    application.add_handler(CommandHandler("start", handle_referral))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_message))
    application.add_error_handler(error_handler)
    application.run_polling()

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error("Exception while handling an update:", exc_info=context.error)
    if update and update.effective_message:
        error_message = (
            "❌ *Bir Hata Oluştu* ❌\n\n"
            "Lütfen aşağıdakileri kontrol edin:\n"
            "• İnternet bağlantınızın olduğundan emin olun\n"
            "• Botun çalışır durumda olduğunu kontrol edin\n"
            "• İşlemi tekrar deneyin\n\n"
            "Sorun devam ederse lütfen admin ile iletişime geçin."
        )
        await update.effective_message.reply_text(error_message, parse_mode='Markdown')

if __name__ == "__main__":
    main()
