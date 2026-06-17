import sqlite3
from datetime import datetime, date
import os

DB_FILE = "tabel.db"

def get_conn():
    return sqlite3.connect(DB_FILE)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    
    # Xodimlar jadvali
    c.execute('''CREATE TABLE IF NOT EXISTS xodimlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ism TEXT NOT NULL,
        lavozim TEXT DEFAULT 'Tikuvchi',
        soatlik_maosh INTEGER DEFAULT 0,
        telegram_id TEXT DEFAULT '',
        faol INTEGER DEFAULT 1,
        qoshilgan_sana TEXT DEFAULT ''
    )''')
    
    # Tabel jadvali
    c.execute('''CREATE TABLE IF NOT EXISTS tabel (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        xodim_id INTEGER,
        sana TEXT,
        smen TEXT,
        holat TEXT,
        keldi_vaqt TEXT DEFAULT '',
        ketdi_vaqt TEXT DEFAULT '',
        kechikish_daqiqa INTEGER DEFAULT 0,
        izoh TEXT DEFAULT '',
        belgilagan TEXT DEFAULT '',
        FOREIGN KEY (xodim_id) REFERENCES xodimlar(id)
    )''')
    
    # Maosh jadvali
    c.execute('''CREATE TABLE IF NOT EXISTS maosh (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        xodim_id INTEGER,
        oy TEXT,
        jami_soat REAL DEFAULT 0,
        jami_kun INTEGER DEFAULT 0,
        kasallik_kun INTEGER DEFAULT 0,
        tatil_kun INTEGER DEFAULT 0,
        kechikish_daqiqa INTEGER DEFAULT 0,
        hisoblangan_maosh INTEGER DEFAULT 0,
        tolov_holati TEXT DEFAULT 'Tolanmagan',
        FOREIGN KEY (xodim_id) REFERENCES xodimlar(id)
    )''')
    
    # Sozlamalar
    c.execute('''CREATE TABLE IF NOT EXISTS sozlamalar (
        kalit TEXT PRIMARY KEY,
        qiymat TEXT
    )''')
    
    # Default sozlamalar
    sozlamalar = [
        ('smen1_boshi', '07:00'),
        ('smen1_oxiri', '19:00'),
        ('smen2_boshi', '19:00'),
        ('smen2_oxiri', '07:00'),
        ('kechikish_chegara', '15'),
        ('soatlik_maosh_default', '15000'),
    ]
    for k, v in sozlamalar:
        c.execute('INSERT OR IGNORE INTO sozlamalar VALUES (?, ?)', (k, v))
    
    conn.commit()
    conn.close()

def get_sozlama(kalit):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT qiymat FROM sozlamalar WHERE kalit=?', (kalit,))
    r = c.fetchone()
    conn.close()
    return r[0] if r else None

def set_sozlama(kalit, qiymat):
    conn = get_conn()
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO sozlamalar VALUES (?, ?)', (kalit, str(qiymat)))
    conn.commit()
    conn.close()

# ===== XODIMLAR =====
def xodim_qosh(ism, lavozim='Tikuvchi', soatlik_maosh=15000):
    conn = get_conn()
    c = conn.cursor()
    c.execute('INSERT INTO xodimlar (ism, lavozim, soatlik_maosh, qoshilgan_sana) VALUES (?, ?, ?, ?)',
              (ism, lavozim, soatlik_maosh, date.today().isoformat()))
    conn.commit()
    xid = c.lastrowid
    conn.close()
    return xid

def xodimlar_royxati(faqat_faol=True):
    conn = get_conn()
    c = conn.cursor()
    if faqat_faol:
        c.execute('SELECT * FROM xodimlar WHERE faol=1 ORDER BY ism')
    else:
        c.execute('SELECT * FROM xodimlar ORDER BY ism')
    r = c.fetchall()
    conn.close()
    return r

def xodim_olish(xodim_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM xodimlar WHERE id=?', (xodim_id,))
    r = c.fetchone()
    conn.close()
    return r

def xodim_yangilash(xodim_id, soatlik_maosh):
    conn = get_conn()
    c = conn.cursor()
    c.execute('UPDATE xodimlar SET soatlik_maosh=? WHERE id=?', (soatlik_maosh, xodim_id))
    conn.commit()
    conn.close()

def xodim_ochirish(xodim_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute('UPDATE xodimlar SET faol=0 WHERE id=?', (xodim_id,))
    conn.commit()
    conn.close()

# ===== TABEL =====
def tabel_belgilash(xodim_id, sana, smen, holat, keldi_vaqt='', ketdi_vaqt='', 
                     kechikish=0, izoh='', belgilagan=''):
    conn = get_conn()
    c = conn.cursor()
    # Mavjud yozuvni tekshirish
    c.execute('SELECT id FROM tabel WHERE xodim_id=? AND sana=? AND smen=?',
              (xodim_id, sana, smen))
    mavjud = c.fetchone()
    
    if mavjud:
        c.execute('''UPDATE tabel SET holat=?, keldi_vaqt=?, ketdi_vaqt=?,
                     kechikish_daqiqa=?, izoh=?, belgilagan=?
                     WHERE id=?''',
                  (holat, keldi_vaqt, ketdi_vaqt, kechikish, izoh, belgilagan, mavjud[0]))
    else:
        c.execute('''INSERT INTO tabel 
                     (xodim_id, sana, smen, holat, keldi_vaqt, ketdi_vaqt,
                      kechikish_daqiqa, izoh, belgilagan)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (xodim_id, sana, smen, holat, keldi_vaqt, ketdi_vaqt,
                   kechikish, izoh, belgilagan))
    conn.commit()
    conn.close()

def bugungi_tabel(sana=None, smen=None):
    if not sana:
        sana = date.today().isoformat()
    conn = get_conn()
    c = conn.cursor()
    if smen:
        c.execute('''SELECT t.*, x.ism, x.lavozim FROM tabel t
                     JOIN xodimlar x ON t.xodim_id=x.id
                     WHERE t.sana=? AND t.smen=? ORDER BY x.ism''', (sana, smen))
    else:
        c.execute('''SELECT t.*, x.ism, x.lavozim FROM tabel t
                     JOIN xodimlar x ON t.xodim_id=x.id
                     WHERE t.sana=? ORDER BY x.ism''', (sana,))
    r = c.fetchall()
    conn.close()
    return r

def xodim_oylik_tabel(xodim_id, oy):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''SELECT * FROM tabel WHERE xodim_id=? AND sana LIKE ?
                 ORDER BY sana''', (xodim_id, f'{oy}%'))
    r = c.fetchall()
    conn.close()
    return r

def tabel_belgilanganmi(xodim_id, sana, smen):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT holat FROM tabel WHERE xodim_id=? AND sana=? AND smen=?',
              (xodim_id, sana, smen))
    r = c.fetchone()
    conn.close()
    return r[0] if r else None

# ===== MAOSH HISOBLASH =====
def oylik_maosh_hisoblash(oy):
    conn = get_conn()
    c = conn.cursor()
    xodimlar = xodimlar_royxati()
    
    for xodim in xodimlar:
        xid = xodim[0]
        soatlik = xodim[3]
        
        c.execute('''SELECT holat, COUNT(*) as soni, 
                     SUM(kechikish_daqiqa) as kechikish
                     FROM tabel WHERE xodim_id=? AND sana LIKE ?
                     GROUP BY holat''', (xid, f'{oy}%'))
        holatlar = c.fetchall()
        
        jami_kun = 0
        kasallik = 0
        tatil = 0
        kechikish_jami = 0
        
        for h in holatlar:
            if h[0] == 'Keldi':
                jami_kun += h[1]
                kechikish_jami += (h[2] or 0)
            elif h[0] == 'Kasallik':
                kasallik += h[1]
            elif h[0] == "Ta'til":
                tatil += h[1]
        
        # 1 smen = 12 soat
        jami_soat = jami_kun * 12
        # Kechikish uchun ayirish
        kechikish_soat = kechikish_jami / 60
        sof_soat = max(0, jami_soat - kechikish_soat)
        hisoblangan = int(sof_soat * soatlik)
        
        # Mavjudini yangilash yoki yangi qo'shish
        c.execute('SELECT id FROM maosh WHERE xodim_id=? AND oy=?', (xid, oy))
        mavjud = c.fetchone()
        if mavjud:
            c.execute('''UPDATE maosh SET jami_soat=?, jami_kun=?, kasallik_kun=?,
                         tatil_kun=?, kechikish_daqiqa=?, hisoblangan_maosh=?
                         WHERE id=?''',
                      (sof_soat, jami_kun, kasallik, tatil, kechikish_jami,
                       hisoblangan, mavjud[0]))
        else:
            c.execute('''INSERT INTO maosh 
                         (xodim_id, oy, jami_soat, jami_kun, kasallik_kun,
                          tatil_kun, kechikish_daqiqa, hisoblangan_maosh)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                      (xid, oy, sof_soat, jami_kun, kasallik, tatil,
                       kechikish_jami, hisoblangan))
    
    conn.commit()
    conn.close()

def oylik_maosh_olish(oy):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''SELECT m.*, x.ism, x.lavozim, x.soatlik_maosh 
                 FROM maosh m JOIN xodimlar x ON m.xodim_id=x.id
                 WHERE m.oy=? ORDER BY x.ism''', (oy,))
    r = c.fetchall()
    conn.close()
    return r
