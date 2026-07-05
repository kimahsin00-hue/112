import discord, aiohttp, json, asyncio, sqlite3, os
from discord.ext import commands, tasks
from thefuzz import process
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
bot = commands.Bot(command_prefix='!', intents=intents)

KST = timezone(timedelta(hours=9))
WEEKDAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]


# ==========================================
# ⚙️ [봇 설정 모음 - 여기서 ID와 링크를 수정하세요!]
# ==========================================
# 1. 역할 및 채널 ID 설정
ADMIN_ROLE_ID = 1421923985137864864       # 참모 및 관리자 역할 ID
NEWBIE_JOIN_ROLE_ID = 1508382595455647854 # 가입 승인 시 부여될 역할 ID
BROADCAST_CHANNEL_ID = 1506670935464345763 # 관리자가 공지를 '작성'하는 채널 ID

# 2. 티켓이 생성될 카테고리 채널 ID 
# (숫자 0으로 두면 봇이 '기타 문의' 카테고리를 자동 생성하여 사용합니다.)
TICKET_CATEGORY_JOIN   = 1509621761111621662  # 가입 상담
TICKET_CATEGORY_QNA    = 1522961865779712111  # 문의/건의
TICKET_CATEGORY_REPORT = 1522961865779712111  # 불편사항 제보
TICKET_CATEGORY_ANON   = 1520840183510204526  # 익명 제보
TICKET_CATEGORY_ATO    = 1509619272501166080  # ⚔️ 아토락시온 파티
TICKET_CATEGORY_SHRINE = 1523149959086473398  # ⚔️ 검은사당 파티
TICKET_CATEGORY_BLOOD  = 1517138990476562473  # ⚔️ 피의제단 파티

# 3. 공식 링크 패널
OFFICIAL_LINKS = [
    {"label": "공지사항",    "url": "https://www.kr.playblackdesert.com/ko-KR/News/Notice?boardType=1"},
    {"label": "업데이트",           "url": "https://www.kr.playblackdesert.com/ko-KR/News/Notice?boardType=2"},
    {"label": "이벤트",          "url": "https://www.kr.playblackdesert.com/ko-KR/News/Notice?boardType=3"},
    {"label": "펄상점",       "url": "https://payment.kr.playblackdesert.com/ko-KR/Pay/Home/?_gl=1*zz86sk*_gcl_au*MTY4MTA1NDczNC4xNzgyNTM3NzI1&_ga=2.263919813.813103790.1782537726-1813507788.1782537726"},
    {"label": "공식 홈페이지",        "url": "https://www.kr.playblackdesert.com/"},
    {"label": "연구소",        "url": "https://www.global-lab.playblackdesert.com/"},
    {"label": "쿠폰 확인",     "url": "https://www.kr.playblackdesert.com/ko-KR/News/Detail?groupContentNo=10748&countryType=ko-KR"},
    {"label": "최신 영상",           "url": "https://www.youtube.com/@BlackDesert_KR"},
    {"label": "검은사막 인벤",          "url": "https://black.inven.co.kr/"},
    {"label": "검통디",      "url": "https://korbdo.co.kr/"},
    {"label": "제작노트",      "url": "https://korbdo.co.kr/#craft"},
    {"label": "광명석조합식",      "url": "https://www.kr.playblackdesert.com/ko-KR/Wiki?wikiNo=273#t1"},
]
# ==========================================

ITEM_LIST = {}

# ==========================================
# [기본 유틸 함수 및 DB 초기화]
# ==========================================
def format_dt(dt):
    return f"{dt.year}년 {dt.month:02d}월 {dt.day:02d}일 {WEEKDAYS[dt.weekday()]} {dt.hour:02d}시 {dt.minute:02d}분"

def make_codeblock(text):
    return f"```\n{text}\n```"

def format_kr(num):
    res = []
    eok, man, rest = num // 100000000, (num % 100000000) // 10000, num % 10000
    if eok > 0: res.append(f"{eok}억")
    if man > 0: res.append(f"{man}만")
    if rest > 0:
        th, h, t, o = rest // 1000, (rest % 1000) // 100, (rest % 100) // 10, rest % 10
        if th > 0: res.append(f"{th}천")
        if h > 0: res.append(f"{h}백")
        if t > 0: res.append(f"{t}십")
        if o > 0: res.append(f"{o}")
    return " ".join(res) if res else str(num)

def schedule_ephemeral_delete(interaction: discord.Interaction, delay: int = 60):
    async def _delete_later():
        await asyncio.sleep(delay)
        try: await interaction.delete_original_response()
        except: pass
    bot.loop.create_task(_delete_later())

def init_db():
    conn = sqlite3.connect('bdo_data.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS pearl_history (item_id INTEGER, timestamp DATETIME, total_trades INTEGER, stock INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS rift_history (id INTEGER PRIMARY KEY CHECK(id=1), reporter_id INTEGER, reporter_name TEXT, kill_time DATETIME)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS item_cache (item_id INTEGER, sid INTEGER, price INTEGER, stock INTEGER, count INTEGER, last_updated DATETIME, PRIMARY KEY (item_id, sid))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS status_reports (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, user_id INTEGER, content TEXT, timestamp DATETIME, expire_time DATETIME)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS boss_alert_channels (guild_id INTEGER PRIMARY KEY, channel_id INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS status_notify_channels (s_type TEXT PRIMARY KEY, channel_id INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS boss_alert_users (user_id INTEGER PRIMARY KEY)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS status_alert_users (user_id INTEGER PRIMARY KEY)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS boss_alert_settings (user_id INTEGER, time_str TEXT, PRIMARY KEY (user_id, time_str))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS weekly_dm_settings (guild_id INTEGER PRIMARY KEY, title TEXT, message TEXT, enabled INTEGER DEFAULT 1)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS broadcast_channels (guild_id INTEGER PRIMARY KEY, channel_id INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS tts_settings (guild_id INTEGER PRIMARY KEY, text_ch_id INTEGER, voice_ch_id INTEGER, enabled INTEGER DEFAULT 1)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS music_channels (guild_id INTEGER PRIMARY KEY, channel_id INTEGER NOT NULL)''')
    conn.commit(); conn.close()


async def get_or_create_category(guild: discord.Guild, ticket_type: str):
    mapping = {
        "join": TICKET_CATEGORY_JOIN, 
        "qna": TICKET_CATEGORY_QNA, 
        "comp": TICKET_CATEGORY_REPORT,
        "anon": TICKET_CATEGORY_ANON, 
        "ato": TICKET_CATEGORY_ATO,
        "shrine": TICKET_CATEGORY_SHRINE, 
        "blood": TICKET_CATEGORY_BLOOD
    }
    cat_id = mapping.get(ticket_type, 0)
    if cat_id != 0:
        cat = guild.get_channel(cat_id)
        if cat and isinstance(cat, discord.CategoryChannel):
            return cat
    cat = discord.utils.get(guild.categories, name="기타 문의")
    if not cat: cat = await guild.create_category("기타 문의")
    return cat



# ==========================================
# [데이터베이스 데이터 압축]
# ==========================================
CAPHRAS_DB = {"주무기": {0:0,1:297,2:686,3:1167,4:1740,5:2645,6:3665,7:4800,8:6050,9:7415,10:8895,11:10417,12:12054,13:13806,14:15673,15:17655,16:19752,17:21964,18:24291,19:26733,20:29403}, "동 방어구": {0:0,1:153,2:383,3:690,4:997,5:1710,6:2424,7:3522,8:4716,9:5950,10:7224,11:8496,12:9808,13:11160,14:12552,15:13984,16:15456,17:16968,18:18520,19:20112,20:21744}}
AP_BRACKETS = [(100, 5), (140, 10), (170, 15), (184, 20), (209, 30), (235, 40), (245, 48), (249, 57), (253, 69), (257, 83), (261, 101), (265, 122), (269, 137), (273, 142), (277, 148), (281, 154), (285, 160), (289, 167), (293, 174), (297, 181), (301, 188), (305, 196), (309, 200), (316, 203), (321, 205), (328, 208), (332, 211), (337, 214), (342, 217), (347, 220), (352, 223), (358, 225), (364, 227), (369, 230), (375, 233), (381, 236), (386, 239), (392, 242), (397, 245)]
DP_BRACKETS = [(203, 1), (211, 2), (218, 3), (226, 4), (233, 5), (241, 6), (248, 7), (256, 8), (263, 9), (271, 10), (278, 11), (286, 12), (293, 13), (301, 14), (308, 15), (315, 16), (322, 17), (329, 18), (335, 19), (341, 20), (347, 21), (353, 22), (359, 23), (365, 24), (371, 25), (377, 26), (383, 27), (389, 28), (395, 29), (401, 30)]
BOSS_DB = {"월": [("02:00", "크자카, 불가살"), ("11:00", "누베르, 우투리"), ("14:00", "가모스"), ("16:00", "쿠툼, 금돼지왕"), ("20:00", "카란다, 산군"), ("23:15", "가모스"), ("23:30", "오핀, 불가살")], "화": [("02:00", "누베르, 우투리"), ("11:00", "쿠툼, 금돼지왕"), ("14:00", "가모스"), ("16:00", "누베르, 산군"), ("20:00", "크자카, 불가살"), ("23:15", "가모스"), ("23:30", "카란다, 우투리")], "수": [("02:00", "오핀, 금돼지왕"), ("14:00", "가모스"), ("16:00", "카란다, 산군"), ("19:00", "권트, 무라카"), ("20:00", "쿠툼, 불가살"), ("23:15", "가모스"), ("23:30", "크자카, 우투리")], "목": [("00:15", "벨"), ("02:00", "카란다, 금돼지왕"), ("11:00", "크자카, 산군"), ("14:00", "가모스"), ("16:00", "누베르, 불가살"), ("20:00", "누베르, 우투리"), ("23:15", "가모스"), ("23:30", "쿠툼, 금돼지왕")], "금": [("02:00", "쿠툼, 산군"), ("11:00", "카란다, 불가살"), ("14:00", "가모스"), ("16:00", "크자카, 우투리"), ("20:00", "누베르, 금돼지왕"), ("23:15", "가모스"), ("23:30", "오핀, 산군")], "토": [("02:00", "쿠툼, 불가살"), ("11:00", "카란다, 우투리"), ("14:00", "가모스"), ("16:00", "크자카, 금돼지왕"), ("17:00", "검은그림자"), ("19:00", "권트, 무라카"), ("23:30", "누베르, 금돼지왕")], "일": [("00:15", "가모스"), ("02:00", "누베르, 산군"), ("11:00", "쿠툼, 불가살"), ("14:00", "가모스"), ("16:00", "카란다, 우투리"), ("17:00", "벨"), ("20:00", "크자카, 산군"), ("23:15", "가모스"), ("23:30", "누베르, 금돼지왕")]}
DEKIA_DB = [{"name": "장 라이텐의 동력석", "id": 11630, "sid": 1, "light": 165}, {"name": "장 오우거의 반지", "id": 11607, "sid": 1, "light": 165}, {"name": "광 라이텐의 동력석", "id": 11630, "sid": 2, "light": 450}, {"name": "광 오우거의 반지", "id": 11607, "sid": 2, "light": 450}, {"name": "광 깨어난 달의 목걸이", "id": 11663, "sid": 2, "light": 450}, {"name": "장 깨어난 달의 목걸이", "id": 11663, "sid": 1, "light": 165}, {"name": "장 투로의 허리띠", "id": 12257, "sid": 1, "light": 165}, {"name": "장 툰그라드 귀걸이", "id": 11828, "sid": 1, "light": 165}, {"name": "고 라이텐의 동력석", "id": 11630, "sid": 3, "light": 1275}, {"name": "고 오우거의 반지", "id": 11607, "sid": 3, "light": 1275}, {"name": "장 바아의 새벽", "id": 11875, "sid": 1, "light": 165}, {"name": "광 툰그라드 귀걸이", "id": 11828, "sid": 2, "light": 450}, {"name": "장 검은 침식의 귀걸이", "id": 11853, "sid": 1, "light": 165}, {"name": "고 툰그라드 귀걸이", "id": 11828, "sid": 3, "light": 1275}, {"name": "장 툰그라드 목걸이", "id": 11629, "sid": 1, "light": 165}]
BLESS_DB = [{"name": "거대 멧돼지 머리 박제", "id": 6603, "residue": 3}, {"name": "회색 늑대 머리 박제", "id": 6614, "residue": 3}, {"name": "큰뿔사슴 머리 박제", "id": 6605, "residue": 3}, {"name": "곰 머리 박제", "id": 6602, "residue": 3}, {"name": "족제비 박제", "id": 6608, "residue": 3}, {"name": "여우 머리 박제", "id": 6601, "residue": 3}, {"name": "발렌시아 산양 머리 박제", "id": 6616, "residue": 3}, {"name": "서리 늑대 전신 박제", "id": 6632, "residue": 3}, {"name": "깃털 늑대 머리 박제", "id": 6618, "residue": 3}, {"name": "늑대 머리 박제", "id": 6604, "residue": 3}, {"name": "거대 사자 머리 박제", "id": 6617, "residue": 3}, {"name": "발렌시아 암사자 머리 박제", "id": 6629, "residue": 3}, {"name": "풀 코뿔소 머리 박제", "id": 6620, "residue": 3}, {"name": "멧돼지 머리 박제", "id": 6649, "residue": 75}, {"name": "예민한 곰 머리 박제", "id": 6648, "residue": 75}]
PEARL_OUTFIT_DB = [{"name": "[레인저] 실비아 세트", "id": 740263}, {"name": "[발키리] 세라핌 세트", "id": 740176}, {"name": "[란] 유혈비 세트", "id": 740441}, {"name": "[매구] 연향 세트", "id": 740754}, {"name": "[위치] 라브리프 세트", "id": 740209}, {"name": "[매화] 화선곡 세트", "id": 740330}, {"name": "[격투가] 황야의 결투 세트", "id": 740431}, {"name": "[우사] 은하 세트", "id": 740742}, {"name": "[도사] 호선 세트", "id": 740889}, {"name": "[다크나이트] 씬 테르나 세트", "id": 740400}, {"name": "[닌자] 나루사와 세트", "id": 740381}, {"name": "[쿠노이치] 아요 세트", "id": 740368}, {"name": "[가디언] 이닉스트라 세트", "id": 740529}, {"name": "[레인저] 고타렌사 세트", "id": 740032}, {"name": "[금수랑] 다루 세트", "id": 740124}]
FALLBACK_PRICES = {721003: (3000000, 0, 5291811), 44195: (4000000, 15, 9210452), 16001: (300000, 2410, 481951), 16002: (250000, 5210, 851042), 4998: (6000000, 0, 451025), 4997: (2000000, 114, 824015), 768: (4500000, 0, 14205), 773: (8500000, 0, 2451), 9681: (5200000, 410, 15024), 11630: (120000000, 12, 14510), 11607: (115000000, 8, 24510), 6603: (62000000, 10, 0), 6614: (105000000, 46, 0), 6605: (112000000, 70, 0), 6602: (125000000, 22, 0), 6608: (131000000, 103, 0), 6601: (165000000, 114, 0), 6616: (185000000, 106, 0), 6632: (220000000, 907, 0), 6618: (245000000, 75, 0), 6604: (275000000, 19, 0), 6617: (282000000, 251, 0), 6629: (295000000, 374, 0), 6649: (8550000000, 1127, 0), 6648: (8550000000, 437, 0), 6620: (430000000, 3077, 0)}
SNIPE_ITEMS_GROUPS = [["검은 결정 파편", "검은 결정", "응축된 마력의 검은 결정", "뾰족한 흑결정 조각"], ["아침의 숨결", "돼지 고기", "돼지 피", "돼지 가죽"], ["흉포한 야수의 내단", "카프라스의 돌", "척살의 결정", "숲의 결정"]]
SNIPE_ITEM_IDS = {"검은 결정 파편": 4901, "검은 결정": 4902, "응축된 마력의 검은 결정": 4903, "뾰족한 흑결정 조각": 4998, "아침의 숨결": 810014, "돼지 고기": 7901, "돼지 피": 7904, "돼지 가죽": 7905, "흉포한 야수의 내단": 9780, "카프라스의 돌": 721003, "척살의 결정": 820039, "숲의 결정": 820040}

# ==========================================
# [API 통신 및 핵심 엔진]
# ==========================================
def save_to_cache(item_id, sid, price, stock, count):
    try:
        conn = sqlite3.connect('bdo_data.db')
        c = conn.cursor()
        now_str = datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')
        c.execute("INSERT OR REPLACE INTO item_cache VALUES (?, ?, ?, ?, ?, ?)", (int(item_id), int(sid), int(price), int(stock), int(count), now_str))
        conn.commit(); conn.close()
    except: pass

async def get_fallback_value(item_id, sid=0):
    try:
        conn = sqlite3.connect('bdo_data.db')
        c = conn.cursor()
        c.execute("SELECT price, stock, count FROM item_cache WHERE item_id=? AND sid=?", (int(item_id), int(sid)))
        row = c.fetchone()
        conn.close()
        if row and row[0] is not None and int(row[0]) > 0: return int(row[0]), int(row[1]), int(row[2])
    except: pass 
    return FALLBACK_PRICES.get(int(item_id), (0,0,0))

async def fetch_arsha_sublist(item_id):
    url = "https://api.arsha.io/v2/kr/GetWorldMarketSubList"
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}) as session:
        async with session.get(url, params={"id": item_id, "lang": "kr"}, timeout=15) as response:
            if response.status != 200: raise RuntimeError(f"arsha API status {response.status}")
            data = await response.json(content_type=None)
            if isinstance(data, dict):
                for wrap_key in ("data", "items", "result", "list", "subList", "content"):
                    if isinstance(data.get(wrap_key), list): data = data[wrap_key]; break
                else:
                    if any(k in data for k in ("basePrice", "price", "sid", "count")): data = [data]
            if not isinstance(data, list): raise RuntimeError(f"응답 오류: {type(data)}")
            entries = []
            for row in data:
                try:
                    entries.append({
                        "item_id": int(row.get("mainKey") or row.get("id") or item_id),
                        "min_enhance": int(row.get("sid") or row.get("minEnhance") or 0),
                        "base_price": int(row.get("basePrice") or row.get("price") or 0),
                        "current_stock": int(row.get("count") or row.get("currentStock") or 0),
                        "total_trades": int(row.get("totalTrades") or 0)
                    })
                except: continue
            return entries

async def fetch_pa_sublist(item_id):
    url = "https://trade.kr.playblackdesert.com/Trademarket/GetWorldMarketSubList"
    async with aiohttp.ClientSession(headers={"User-Agent": "BlackDesert", "Content-Type": "application/json"}) as session:
        async with session.post(url, json={"keyType": 0, "mainKey": item_id}, timeout=8) as response:
            if response.status != 200: raise RuntimeError(f"PA API status {response.status}")
            raw = await response.read()
            try: text = raw.decode("utf-16", errors="surrogatepass").encode("utf-8").decode("utf-8")
            except: text = raw.decode("utf-8", errors="ignore")
            data = json.loads(text)
            if data.get("resultCode") != 0: raise RuntimeError("PA API 에러")
            entries = []
            for chunk in data.get("resultMsg", "").split('|'):
                parts = chunk.split('-')
                if len(parts) >= 6:
                    try: entries.append({"item_id": int(parts[0]), "min_enhance": int(parts[1]), "base_price": int(parts[3]), "current_stock": int(parts[4]), "total_trades": int(parts[5])})
                    except: pass
            return entries

async def fetch_market_sublist(item_id):
    try:
        entries = await fetch_arsha_sublist(item_id)
        if entries: return entries
        raise RuntimeError("arsha 빈결과")
    except: return await fetch_pa_sublist(item_id)

async def get_market_price(item_id, sid=0):
    try: item_id, sid = int(item_id), int(sid)
    except: return 0, 0, 0
    try:
        entries = await fetch_market_sublist(item_id)
        if not entries: return await get_fallback_value(item_id, sid)
        for e in entries:
            if e["min_enhance"] == sid:
                p, s, t = e["base_price"], e["current_stock"], e["total_trades"]
                if p > 0: save_to_cache(item_id, sid, p, s, t); return p, s, t
        if sid == 0 and entries:
            p, s, t = entries[0]["base_price"], entries[0]["current_stock"], entries[0]["total_trades"]
            if p > 0: save_to_cache(item_id, sid, p, s, t); return p, s, t
        return await get_fallback_value(item_id, sid)
    except: return await get_fallback_value(item_id, sid)

# ==========================================
# 🚨 [포식 완벽 수정 로직] 🚨
# ==========================================
DEVOUR_GAIN_TABLES = {
    "어둠": [
        (100,101,26),(102,105,25),(106,108,24),(109,111,23),(112,115,22),(116,119,21),
        (120,124,20),(125,129,19),(130,135,18),(136,141,17),(142,148,16),(149,156,15),
        (157,165,14),(166,175,13),(176,187,12),(188,196,11),(197,206,10),(207,217,9),
        (218,235,8),(236,254,7),(255,269,6),(270,291,5),(292,296,4),(297,297,3),(298,298,2),(299,299,1)
    ],
    "은은한": [
        (100,104,13), (105,109,12), (110,117,11), (118,124,10), (125,134,9), (135,146,8),
        (147,163,7), (164,179,6), (180,205,5), (206,228,4), (229,267,3), (268,298,2), (299,299,1)
    ],
    "정제된": [
        (100,101,52), (102,105,50), (106,108,48), (109,111,46), (112,115,44), (116,119,42),
        (120,124,40), (125,129,38), (130,135,36), (136,141,34), (142,148,32), (149,156,30),
        (157,165,28), (166,175,26), (176,187,24), (188,196,22), (197,206,20), (207,217,18),
        (218,235,16), (236,254,14), (255,269,12), (270,291,10), (292,292,8), (293,293,7),
        (294,294,6), (295,295,5), (296,296,4), (297,297,3), (298,298,2), (299,299,1)
    ]
}

def _devour_gain(stack, devour_type):
    # 이제 수식이 아니라 정확히 매핑된 테이블을 100% 참조합니다.
    table = DEVOUR_GAIN_TABLES.get(devour_type, DEVOUR_GAIN_TABLES["어둠"])
    for lo, hi, g in table:
        if lo <= stack <= hi:
            return g
    return 1

def calculate_devour_type(start: int, target: int, devour_type: str):
    cur, count = start, 0
    while cur < target:
        cur += _devour_gain(cur, devour_type)
        count += 1
        if cur >= 300: cur = 300; break
    return count, cur

def get_bracket_info(value, brackets, is_dp=False):
    current_bonus, next_req, next_bonus = 0, None, None
    for i, (req, bonus) in enumerate(brackets):
        if value >= req:
            current_bonus = bonus
            if i + 1 < len(brackets): next_req, next_bonus = brackets[i+1][0], brackets[i+1][1]
            else: next_req, next_bonus = None, None
        else:
            if current_bonus == 0 and i == 0: next_req, next_bonus = brackets[0][0], brackets[0][1]
            break
    unit = "%" if is_dp else ""
    t_name = "피해감소" if is_dp else "공격력"
    if current_bonus == 0 and next_req: return f"현재 보너스 없음\n▶ 다음 구간(**{next_req}**)까지: **{next_req - value}** 필요 (보너스 {next_bonus}{unit})"
    elif next_req: return f"현재 보너스 {t_name}: **+{current_bonus}{unit}**\n▶ 다음 구간(**{next_req}**)까지: **{next_req - value}** 필요 (보너스 +{next_bonus}{unit})"
    else: return f"현재 보너스 {t_name}: **+{current_bonus}{unit}**\n▶ (최고 보너스 구간 도달)"

def get_bdo_time():
    BASE_DT = datetime(2026, 6, 27, 17, 19, 33, tzinfo=KST)
    now = datetime.now(KST)
    elapsed_min = (now - BASE_DT).total_seconds() / 60.0
    real_min_in_cycle = elapsed_min % 240
    if real_min_in_cycle < 0: real_min_in_cycle += 240
    if real_min_in_cycle < 200: game_min_since_7am = real_min_in_cycle * 4.5; is_night = False; remain_m = 200 - real_min_in_cycle
    else: game_min_since_7am = 900 + (real_min_in_cycle - 200) * 13.5; is_night = True; remain_m = 240 - real_min_in_cycle
    total_game_min = (7 * 60 + game_min_since_7am) % 1440
    return f"{int(total_game_min // 60):02d}:{int(total_game_min % 60):02d}", "밤" if is_night else "낮", int(round(remain_m))

# ==========================================
# [군왕 무기 계산기 특수 로직]
# ==========================================
SOV_WEAPON_NAME_PATTERNS = {
    "동 검은별 주무기":     (["검은별"], ["각성", "투구", "갑옷", "장갑", "신발", "방패", "단검", "노리개", "장식매듭", "타리스만", "완갑", "각궁", "고검", "라곤", "수리검", "표창", "금계", "비초아리", "크라톤"]),
    "동 크자카 주무기":     (["크자카"], ["방패", "단검", "노리개", "장식매듭", "타리스만", "완갑", "각궁", "고검", "라곤", "수리검", "표창", "금계", "비초아리", "크라톤", "추종세력"]),
    "동 검은별 각성무기":   (["검은별"], ["투구", "갑옷", "장갑", "신발", "방패", "단검", "노리개", "장식매듭", "타리스만", "완갑", "각궁", "고검", "라곤", "수리검", "표창", "금계", "비초아리", "크라톤", "장검", "장궁", "부적", "도끼", "소검", "도검", "지팡이", "태도", "권갑", "반월추", "석궁", "플로랑", "전투도끼", "사곡도"]),
    "동 단델리온 각성무기": (["단델리온"], []),
    "동 검은별 보조무기":   (["검은별"], ["각성", "투구", "갑옷", "장갑", "신발", "장검", "장궁", "부적", "도끼", "소검", "도검", "지팡이", "태도", "권갑", "반월추", "석궁", "플로랑", "전투도끼", "사곡도"]),
    "동 누베르 보조무기":   (["누베르"], ["조각상"]),
    "동 쿠툼 보조무기":     (["쿠툼"],   ["조명들"]),
}
SOV_RECIPES = {
    "주무기": [
        ("동 검은별 주무기 + 동 검은별 주무기",
         [("동 검은별 주무기", 2), ("마력의 파편", 1), ("카프라스의 돌", 1)]),
        ("동 검은별 주무기 + 동 크자카 주무기 + 황혼의 보석",
         [("동 검은별 주무기", 1), ("동 크자카 주무기", 1), ("황혼의 보석", 1), ("마력의 파편", 1), ("카프라스의 돌", 1)]),
    ],
    "각성무기": [
        ("동 검은별 각성무기 + 동 검은별 각성무기",
         [("동 검은별 각성무기", 2), ("마력의 파편", 1), ("카프라스의 돌", 1)]),
        ("동 검은별 각성무기 + 동 단델리온 각성무기 + 황혼의 보석",
         [("동 검은별 각성무기", 1), ("동 단델리온 각성무기", 1), ("황혼의 보석", 1), ("마력의 파편", 1), ("카프라스의 돌", 1)]),
    ],
    "보조무기": [
        ("동 검은별 보조무기 + 동 검은별 보조무기 + 황혼의 보석",
         [("동 검은별 보조무기", 2), ("황혼의 보석", 1), ("마력의 파편", 1), ("카프라스의 돌", 1)]),
        ("동 검은별 보조무기 + 동 누베르/쿠툼 보조무기",
         [("동 검은별 보조무기", 1), ("동 누베르 보조무기", 1), ("동 쿠툼 보조무기", 1), ("마력의 파편", 1), ("카프라스의 돌", 1)]),
        ("동 검은별 + 황혼의 보석 + 태초의 보석",
         [("동 검은별 보조무기", 1), ("황혼의 보석", 1), ("태초의 보석", 1), ("마력의 파편", 1), ("카프라스의 돌", 1)]),
    ],
}

async def get_sov_weapon_price(item_key: str):
    req, exc = SOV_WEAPON_NAME_PATTERNS.get(item_key, ([], []))
    if not req: return (0, 0, 0)
    m_ids = [iid for n, iid in ITEM_LIST.items() if not any(e in n for e in exc) and all(r in n for r in req)]
    if not m_ids: return (0, 0, 0)
    results = await asyncio.gather(*[fetch_market_sublist(i) for i in m_ids], return_exceptions=True)
    bp, bs, bt = 0, 0, 0
    for entries in results:
        if isinstance(entries, Exception) or not entries: continue
        for e in entries:
            if e.get("min_enhance", 0) == 20 and e.get("base_price", 0) > 0 and (bp == 0 or e.get("base_price", 0) < bp):
                bp, bs, bt = e.get("base_price", 0), e.get("current_stock", 0), e.get("total_trades", 0)
    return (bp, bs, bt)

async def fetch_sov_prices(weapon_type: str):
    needed = set(name for _, ings in SOV_RECIPES[weapon_type] for name, _ in ings)
    # 황혼/태초 보석은 API 조회 대신 마력의 파편×100 + 카프라스의 돌×20,000으로 역산
    # 마력의 파편/카프라스의 돌은 모든 레시피에 필요하므로 항상 needed에 포함
    needed.update(["마력의 파편", "카프라스의 돌"])
    async def _f(n):
        if n in ["황혼의 보석", "태초의 보석"]: return (0, 0, 0)
        if n in SOV_WEAPON_NAME_PATTERNS: return await get_sov_weapon_price(n)
        for d in [{"name":"마력의 파편","id":44195,"sid":0}, {"name":"카프라스의 돌","id":721003,"sid":0}]:
            if d["name"] == n: return await get_market_price(d["id"], d["sid"])
        return (0, 0, 0)
    needed_list = list(needed)
    results = await asyncio.gather(*[_f(n) for n in needed_list], return_exceptions=True)
    prices = {n: res if not isinstance(res, Exception) and res else (0,0,0) for n, res in zip(needed_list, results)}
    # 황혼의 보석 / 태초의 보석 역산 (둘 다 동일한 제작 재료)
    calc_p = prices.get("마력의 파편",(0,0,0))[0]*100 + prices.get("카프라스의 돌",(0,0,0))[0]*20000
    if "황혼의 보석" in needed: prices["황혼의 보석"] = (calc_p, 0, 0)
    if "태초의 보석" in needed: prices["태초의 보석"] = (calc_p, 0, 0)
    return prices

# ==========================================
# [각종 UI 패널들 (Views, Modals)]
# ==========================================
class AvgPriceSelectView(discord.ui.View):
    def __init__(self, options, raw_input):
        super().__init__(timeout=None)
        self.select = discord.ui.Select(placeholder="아이템을 선택해주세요.", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)
    async def select_callback(self, interaction: discord.Interaction):
        val = self.select.values[0]
        item_id, sid = map(int, val.split('_'))
        b_name = next(opt.label for opt in self.select.options if opt.value == val)
        await interaction.response.defer(ephemeral=True); schedule_ephemeral_delete(interaction)
        price, stock, _ = await get_market_price(item_id, sid)
        embed = discord.Embed(title="아이템 평균가 조회", color=0x3498db)
        embed.description = f"**선택한 아이템:** `{b_name}`\n\n**가격:** **{price:,}** 은화 ({format_kr(price)})\n**매물:** {stock:,}개" if price > 0 else f"**선택한 아이템:** `{b_name}`\n\n매물 없거나 시세 조회 불가."
        await interaction.edit_original_response(embed=embed, view=self)

class AvgPriceModal(discord.ui.Modal, title='아이템 평균가 조회'):
    item_input = discord.ui.TextInput(label='아이템 이름 (비슷하게 쳐도 됩니다)', required=True, max_length=30)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); schedule_ephemeral_delete(interaction)
        raw = self.item_input.value.strip()
        if not ITEM_LIST: await interaction.followup.send("데이터베이스 로드 중입니다. 잠시 후 다시 시도해주세요.", ephemeral=True); return
        matches = [(n, i) for n, i in ITEM_LIST.items() if raw.replace(" ","") in n.replace(" ","")]
        if not matches:
            bests = process.extractBests(raw, ITEM_LIST.keys(), limit=5)
            matches = [(b, ITEM_LIST[b]) for b, s in bests if s >= 50]
        if not matches: await interaction.followup.send(f"'{raw}'을(를) 찾을 수 없습니다.", ephemeral=True); return
        matches = sorted(matches, key=lambda m: len(m[0]))[:15]
        results = await asyncio.gather(*[fetch_market_sublist(iid) for _, iid in matches], return_exceptions=True)
        options = []
        for (b_name, b_id), entries in zip(matches, results):
            if isinstance(entries, Exception) or not entries: continue
            for e in sorted(entries, key=lambda x: x.get("min_enhance",0)):
                sid = e.get("min_enhance",0)
                prefix = {"16":"장 ","17":"광 ","18":"고 ","19":"유 ","20":"동 "}.get(str(sid), f"+{sid} ") if 16<=sid<=20 else f"+{sid} " if sid>0 else ""
                options.append(discord.SelectOption(label=f"{prefix}{b_name}".strip()[:100], value=f"{b_id}_{sid}"))
        if not options: await interaction.followup.send("매물 데이터를 찾을 수 없습니다.", ephemeral=True); return
        await interaction.followup.send(embed=discord.Embed(title="아이템 평균가 조회", description="조회할 아이템을 선택해주세요.", color=0x2b2d31), view=AvgPriceSelectView(options[:25], raw), ephemeral=True)

class CaphrasStepModal(discord.ui.Modal, title='단계 입력'):
    start_lvl = discord.ui.TextInput(label='현재 단계', placeholder='현재 단계를 입력하세요..', required=True, max_length=2)
    target_lvl = discord.ui.TextInput(label='목표 단계', placeholder='목표 단계를 입력하세요..', required=True, max_length=2)
    def __init__(self, display_name: str, eq: str, gr: str): super().__init__(); self.display_name = display_name; self.eq = eq; self.gr = gr
    async def on_submit(self, interaction: discord.Interaction):
        try: start, target = int(self.start_lvl.value.strip()), int(self.target_lvl.value.strip())
        except ValueError: await interaction.response.send_message("숫자만 입력해 주세요!", ephemeral=True); schedule_ephemeral_delete(interaction); return
        db = CAPHRAS_DB.get(self.eq)
        if not db or start not in db or target not in db or start >= target: await interaction.response.send_message("올바른 단계 범위를 입력해 주세요.", ephemeral=True); schedule_ephemeral_delete(interaction); return
        req_stones = db[target] - db[start]
        c_price, _, _ = await get_market_price(721003, 0)
        total_silver = req_stones * (c_price if c_price > 0 else 3000000)
        embed = discord.Embed(color=0x2ecc71, title="카프라스 계산기", description=f"**{self.display_name}** {start}단계에서 {target}단계:\n\n필요한 카프라스: **{req_stones:,}개**\n필요 금액: **{total_silver:,}** ({format_kr(total_silver)})")
        await interaction.response.send_message(embed=embed, ephemeral=True); schedule_ephemeral_delete(interaction)

class CaphrasSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        opts = [discord.SelectOption(label=d, value=str(i)) for i, (d, _, _) in enumerate([("주무기", "주무기", ""), ("동 방어구", "동 방어구", "")])]
        self.s = discord.ui.Select(placeholder="장비를 선택해주세요.", options=opts); self.s.callback = self.cb; self.add_item(self.s)
    async def cb(self, interaction: discord.Interaction):
        d, eq, gr = [("주무기", "주무기", ""), ("동 방어구", "동 방어구", "")][int(self.s.values[0])]
        await interaction.response.send_modal(CaphrasStepModal(d, eq, gr))

class ApDpModal(discord.ui.Modal, title='공/방 보너스 구간 계산기'):
    ap_input = discord.ui.TextInput(label='현재 공격력 (생략가능)', required=False, max_length=3)
    dp_input = discord.ui.TextInput(label='현재 방어력 (생략가능)', required=False, max_length=3)
    async def on_submit(self, interaction: discord.Interaction):
        a, d = self.ap_input.value.strip(), self.dp_input.value.strip()
        if not a and not d: await interaction.response.send_message("최소 하나는 입력해 주세요!", ephemeral=True); schedule_ephemeral_delete(interaction); return
        embed = discord.Embed(title="공/방 보너스 계산 결과", color=0xe74c3c)
        if a and a.isdigit(): embed.add_field(name=f"공격력 ({int(a)})", value=get_bracket_info(int(a), AP_BRACKETS, False), inline=False)
        if d and d.isdigit(): embed.add_field(name=f"방어력 ({int(d)})", value=get_bracket_info(int(d), DP_BRACKETS, True), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True); schedule_ephemeral_delete(interaction)

class DevourTradeModal(discord.ui.Modal):
    def __init__(self, devour_type: str): super().__init__(title=f'{devour_type} 포식'); self.devour_type = devour_type
    s_st = discord.ui.TextInput(label='현재스택 (순수스택)', required=True, max_length=3)
    t_st = discord.ui.TextInput(label='희망스택 (101~300)', required=True, max_length=3)
    async def on_submit(self, interaction: discord.Interaction):
        try: start, target = int(self.s_st.value), int(self.t_st.value)
        except ValueError: await interaction.response.send_message("숫자만 입력해 주세요!", ephemeral=True); schedule_ephemeral_delete(interaction); return
        if not (100 <= start <= 299) or not (101 <= target <= 300) or start >= target: await interaction.response.send_message("올바른 스택 범위를 입력하세요.", ephemeral=True); schedule_ephemeral_delete(interaction); return
        await interaction.response.defer(ephemeral=True); schedule_ephemeral_delete(interaction)
        count, f_stack = calculate_devour_type(start, target, self.devour_type)
        iid = {"어둠": 65319, "은은한": 767102, "정제된": 768000}.get(self.devour_type, 0)
        price, _, _ = await get_market_price(iid) if iid else (0,0,0)
        embed = discord.Embed(color=0x3498db, title=f"{self.devour_type} 포식 (거래소)")
        embed.add_field(name=f"{start}~{target}까지", value=f"필요한 포식: {count}개", inline=False)
        embed.add_field(name="적용후", value=f"{f_stack}스택", inline=True)
        embed.add_field(name="필요 금액", value=f"{count*price:,} ({format_kr(count*price)})" if price > 0 else "시세 조회 실패", inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

class DevourEfficiencyModal(discord.ui.Modal, title='어둠 포식 효율 계산'):
    s_st = discord.ui.TextInput(label='현재스택 (순수스택)', required=True, max_length=3)
    t_st = discord.ui.TextInput(label='희망스택 (101~300)', required=True, max_length=3)
    async def on_submit(self, interaction: discord.Interaction):
        try: start, target = int(self.s_st.value), int(self.t_st.value)
        except ValueError: await interaction.response.send_message("숫자만 입력해 주세요!", ephemeral=True); schedule_ephemeral_delete(interaction); return
        if not (100 <= start <= 299) or not (101 <= target <= 300) or start >= target: await interaction.response.send_message("올바른 범위 입력.", ephemeral=True); schedule_ephemeral_delete(interaction); return
        await interaction.response.defer(ephemeral=True); schedule_ephemeral_delete(interaction)
        pd, _, _ = await get_market_price(65319)
        ps, _, _ = await get_market_price(767102)
        pr, _, _ = await get_market_price(768000)
        prices = {"어둠": pd, "은은한": ps, "정제된": pr}
        cur, counts, segments = start, {"어둠": 0, "은은한": 0, "정제된": 0}, []
        seg_start, seg_type = cur, None
        while cur < target:
            cands = {t: (prices.get(t,0) / _devour_gain(cur, t) if prices.get(t,0)>0 else float('inf')) for t in ["어둠", "은은한", "정제된"]}
            best = min(cands, key=lambda k: cands[k])
            if cands[best] == float('inf'): best = "어둠"
            if best != seg_type:
                if seg_type: segments.append((seg_start, cur, seg_type))
                seg_type, seg_start = best, cur
            cur += _devour_gain(cur, best); counts[best] += 1
            if cur >= 300: cur = 300; break
        segments.append((seg_start, min(cur, target), seg_type))
        embed = discord.Embed(color=0x2b2d31, title="어둠 포식 효율 계산", description=f"시작 스택: {start}\n희망 스택: {target}\n최종 스택: {min(cur, 300)}")
        embed.add_field(name="구간별 효율적인 포식", value="\n".join([f"{s} → {e} : {t} 포식" for s, e, t in segments if s != e]) or "계산 불가", inline=False)
        grand = sum(counts[t] * prices[t] for t in counts)
        for t in counts:
            if counts[t] > 0: embed.add_field(name=f"{t} 포식", value=f"{counts[t]}개\n{counts[t]*prices[t]:,}은화", inline=False)
        embed.add_field(name="최종 결과", value=f"총 비용: {grand:,} ({format_kr(grand)})", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

class DevourSelectView(discord.ui.View):
    def __init__(self): super().__init__(timeout=180)
    @discord.ui.button(label="어둠 포식 (거래소)", style=discord.ButtonStyle.success)
    async def b_d(self, i: discord.Interaction, b: discord.ui.Button): await i.response.send_modal(DevourTradeModal("어둠"))
    @discord.ui.button(label="은은한 포식 (거래소)", style=discord.ButtonStyle.success)
    async def b_s(self, i: discord.Interaction, b: discord.ui.Button): await i.response.send_modal(DevourTradeModal("은은한"))
    @discord.ui.button(label="정제된 포식 (거래소)", style=discord.ButtonStyle.success)
    async def b_r(self, i: discord.Interaction, b: discord.ui.Button): await i.response.send_modal(DevourTradeModal("정제된"))
    @discord.ui.button(label="효율계산", style=discord.ButtonStyle.primary)
    async def b_eff(self, i: discord.Interaction, b: discord.ui.Button): await i.response.send_modal(DevourEfficiencyModal())

class SovResultView(discord.ui.View):
    def __init__(self, w_type: str, prices: dict): super().__init__(timeout=None); self.wt = w_type; self.p = prices
    def build_embed(self) -> discord.Embed:
        e = discord.Embed(title=f"군왕 무기 계산({self.wt})", color=0x2b2d31)
        e.description = "\n".join([f"**{rn}**\n> {format_kr(sum(self.p.get(n,(0,))[0]*q for n,q in ings))}\n" for rn, ings in SOV_RECIPES[self.wt]])
        return e
    @discord.ui.button(label="평균가 확인", style=discord.ButtonStyle.primary)
    async def btn_avg(self, interaction: discord.Interaction, button: discord.ui.Button):
        order = []
        for _, ings in SOV_RECIPES[self.wt]:
            for n, _ in ings:
                if n not in order: order.append(n)
        fo = [n for n in order if "무기" in n]
        if any("보석" in n for n in order): fo.extend(["마력의 파편", "카프라스의 돌"])
        fo.extend([n for n in order if "보석" in n])
        e = discord.Embed(title="군왕 무기 계산기", color=0x2b2d31)
        e.description = "\n".join([f"**{n}**\n> {self.p.get(n,(0,))[0]:,} ({format_kr(self.p.get(n,(0,))[0])})\n" for n in fo])
        await interaction.response.send_message(embed=e, ephemeral=True); schedule_ephemeral_delete(interaction)

class SovWeaponSelectView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    async def _calc(self, interaction: discord.Interaction, w_type: str):
        await interaction.response.defer(ephemeral=True); schedule_ephemeral_delete(interaction)
        view = SovResultView(w_type, await fetch_sov_prices(w_type))
        await interaction.followup.send(embed=view.build_embed(), view=view, ephemeral=True)
    @discord.ui.button(label="주무기", style=discord.ButtonStyle.secondary)
    async def b_m(self, i: discord.Interaction, b: discord.ui.Button): await self._calc(i, "주무기")
    @discord.ui.button(label="각성무기", style=discord.ButtonStyle.secondary)
    async def b_a(self, i: discord.Interaction, b: discord.ui.Button): await self._calc(i, "각성무기")
    @discord.ui.button(label="보조무기", style=discord.ButtonStyle.secondary)
    async def b_s(self, i: discord.Interaction, b: discord.ui.Button): await self._calc(i, "보조무기")

class TaxModal(discord.ui.Modal, title='거래소 실수령액 계산기'):
    price_input = discord.ui.TextInput(label='판매 가격', required=True)
    qty_input = discord.ui.TextInput(label='개수', required=True)
    def __init__(self, bonus_rate): super().__init__(); self.bonus_rate = bonus_rate
    async def on_submit(self, interaction: discord.Interaction):
        try: p, q = int(self.price_input.value.replace(",","")), int(self.qty_input.value.replace(",",""))
        except ValueError: await interaction.response.send_message("숫자만 입력!", ephemeral=True); schedule_ephemeral_delete(interaction); return
        tot = p * q
        res = int(tot * 0.65 * (1 + self.bonus_rate))
        embed = discord.Embed(color=0x3498db, title="거래소 실수령액 계산기", description=f"**판매 가격:** {p:,}\n**개수:** {q:,}개\n**총 판매가격:** {tot:,}\n\n**실제 수령액:** **{res:,}** ({format_kr(res)})")
        await interaction.response.send_message(embed=embed, ephemeral=True); schedule_ephemeral_delete(interaction)

class TaxSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.v = discord.ui.Select(placeholder="밸류 패키지", options=[discord.SelectOption(label="O", value="O"), discord.SelectOption(label="X", value="X")])
        self.f = discord.ui.Select(placeholder="가문 명성", options=[discord.SelectOption(label="없음", value="0"), discord.SelectOption(label="1단계", value="1"), discord.SelectOption(label="2단계", value="2"), discord.SelectOption(label="3단계", value="3")])
        self.r = discord.ui.Select(placeholder="거상의 반지", options=[discord.SelectOption(label="O", value="O"), discord.SelectOption(label="X", value="X")])
        async def dc(i): await i.response.defer()
        self.v.callback, self.f.callback, self.r.callback = dc, dc, dc
        self.add_item(self.v); self.add_item(self.f); self.add_item(self.r)
    @discord.ui.button(label="계산하기", style=discord.ButtonStyle.primary)
    async def btn_calc(self, interaction: discord.Interaction, button: discord.ui.Button):
        v, f, r = (self.v.values[0] if self.v.values else "X"), (self.f.values[0] if self.f.values else "0"), (self.r.values[0] if self.r.values else "X")
        b = sum([0.3 if v=="O" else 0, {"1":0.005, "2":0.01, "3":0.015}.get(f, 0), 0.05 if r=="O" else 0])
        await interaction.response.send_modal(TaxModal(bonus_rate=b))

class PearlTimeView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    async def fs(self, interaction: discord.Interaction, hours: int, tl: str):
        await interaction.response.defer(ephemeral=True); schedule_ephemeral_delete(interaction)
        conn = sqlite3.connect('bdo_data.db'); c = conn.cursor(); now = datetime.now(KST); tt = (now - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
        rk = []
        for i in PEARL_OUTFIT_DB:
            l = c.execute("SELECT total_trades, stock, timestamp FROM pearl_history WHERE item_id=? ORDER BY timestamp DESC LIMIT 1", (i['id'],)).fetchone()
            o = c.execute("SELECT total_trades FROM pearl_history WHERE item_id=? AND timestamp >= ? ORDER BY timestamp ASC LIMIT 1", (i['id'], tt)).fetchone()
            if l and o:
                rt = l[0] - o[0]
                est = f"{int((l[1]/rt)*hours)}시간" if rt > 0 else "계산 불가"
                rk.append({"name": i["name"], "trades": rt, "preorder": l[1], "last": l[2][5:16], "est": est})
        conn.close()
        if not rk: await interaction.followup.send("DB 수집 중입니다.", ephemeral=True); return
        d = f"**{tl} 펄 의상 판매 개수**\n\n" + "".join([f" {r['name']}\n거래수: {r['trades']} / 예약구매: {r['preorder']}\n예상: {r['est']}\n\n" for r in sorted(rk, key=lambda x: x["trades"], reverse=True)])
        await interaction.followup.send(embed=discord.Embed(color=0x9b59b6, description=d[:4000]), ephemeral=True)
    @discord.ui.button(label="3일간")
    async def b3d(self, i: discord.Interaction, b: discord.ui.Button): await self.fs(i, 72, "3일간")
    @discord.ui.button(label="1일간")
    async def b1d(self, i: discord.Interaction, b: discord.ui.Button): await self.fs(i, 24, "1일간")
    @discord.ui.button(label="12시간")
    async def b12(self, i: discord.Interaction, b: discord.ui.Button): await self.fs(i, 12, "12시간")
    @discord.ui.button(label="6시간")
    async def b6(self, i: discord.Interaction, b: discord.ui.Button): await self.fs(i, 6, "6시간")

class SnipeCalcView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None); self.d = {n: 0 for g in SNIPE_ITEMS_GROUPS for n in g}
    async def upd(self, i: discord.Interaction): await i.response.edit_message(embed=discord.Embed(title="저격 수렵 계산기", description="".join([f" {n} : `{c}`\n" for n, c in self.d.items()]), color=0x2b2d31), view=self)
    @discord.ui.button(label="입력1", style=discord.ButtonStyle.secondary)
    async def bi1(self, i: discord.Interaction, b: discord.ui.Button):
        class SnipeInputModal(discord.ui.Modal, title='저격 1'):
            v1=discord.ui.TextInput(label=SNIPE_ITEMS_GROUPS[0][0],required=False); v2=discord.ui.TextInput(label=SNIPE_ITEMS_GROUPS[0][1],required=False)
            v3=discord.ui.TextInput(label=SNIPE_ITEMS_GROUPS[0][2],required=False); v4=discord.ui.TextInput(label=SNIPE_ITEMS_GROUPS[0][3],required=False)
            async def on_submit(self, interaction: discord.Interaction):
                for idx, t in enumerate([self.v1, self.v2, self.v3, self.v4]):
                    val = t.value.strip().replace(",","")
                    self.view_ref.d[SNIPE_ITEMS_GROUPS[0][idx]] = int(val) if val.isdigit() else 0
                await self.view_ref.upd(interaction)
        m = SnipeInputModal(); m.view_ref = self; await i.response.send_modal(m)
    @discord.ui.button(label="입력2", style=discord.ButtonStyle.secondary)
    async def bi2(self, i: discord.Interaction, b: discord.ui.Button):
        class SnipeInputModal(discord.ui.Modal, title='저격 2'):
            v1=discord.ui.TextInput(label=SNIPE_ITEMS_GROUPS[1][0],required=False); v2=discord.ui.TextInput(label=SNIPE_ITEMS_GROUPS[1][1],required=False)
            v3=discord.ui.TextInput(label=SNIPE_ITEMS_GROUPS[1][2],required=False); v4=discord.ui.TextInput(label=SNIPE_ITEMS_GROUPS[1][3],required=False)
            async def on_submit(self, interaction: discord.Interaction):
                for idx, t in enumerate([self.v1, self.v2, self.v3, self.v4]):
                    val = t.value.strip().replace(",","")
                    self.view_ref.d[SNIPE_ITEMS_GROUPS[1][idx]] = int(val) if val.isdigit() else 0
                await self.view_ref.upd(interaction)
        m = SnipeInputModal(); m.view_ref = self; await i.response.send_modal(m)
    @discord.ui.button(label="입력3", style=discord.ButtonStyle.secondary)
    async def bi3(self, i: discord.Interaction, b: discord.ui.Button):
        class SnipeInputModal(discord.ui.Modal, title='저격 3'):
            v1=discord.ui.TextInput(label=SNIPE_ITEMS_GROUPS[2][0],required=False); v2=discord.ui.TextInput(label=SNIPE_ITEMS_GROUPS[2][1],required=False)
            v3=discord.ui.TextInput(label=SNIPE_ITEMS_GROUPS[2][2],required=False); v4=discord.ui.TextInput(label=SNIPE_ITEMS_GROUPS[2][3],required=False)
            async def on_submit(self, interaction: discord.Interaction):
                for idx, t in enumerate([self.v1, self.v2, self.v3, self.v4]):
                    val = t.value.strip().replace(",","")
                    self.view_ref.d[SNIPE_ITEMS_GROUPS[2][idx]] = int(val) if val.isdigit() else 0
                await self.view_ref.upd(interaction)
        m = SnipeInputModal(); m.view_ref = self; await i.response.send_modal(m)
    @discord.ui.button(label="계산하기", style=discord.ButtonStyle.success)
    async def bc(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.defer(ephemeral=True); schedule_ephemeral_delete(i)
        ts = 0; dt = []
        for n, c in self.d.items():
            if c > 0:
                p, _, _ = await get_market_price(SNIPE_ITEM_IDS.get(n,0))
                ts += p*c; dt.append(f"**{n}** : {p:,} x {c} = **{p*c:,}**")
        await i.followup.send(embed=discord.Embed(title="저격 수렵 최종 수익", description="\n".join(dt) + f"\n\n**총 수익:** **{ts:,}** 은화" if dt else "입력 없음", color=0x2ecc71), ephemeral=True)

class SnipeMainView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="계산하기", style=discord.ButtonStyle.success)
    async def bc(self, i: discord.Interaction, b: discord.ui.Button):
        v = SnipeCalcView()
        await i.response.send_message(embed=discord.Embed(title="저격 수렵 계산기", description="초기화 됨", color=0x2b2d31), view=v, ephemeral=True); schedule_ephemeral_delete(i)

def build_rift_status_embed(spawn_time, reporter_name=None):
    diff = spawn_time - datetime.now(KST)
    e = discord.Embed(title="어둠의 틈", color=0x2b2d31)
    if diff.total_seconds() > 0:
        d, r = divmod(diff.total_seconds(), 86400); h, r = divmod(r, 3600); m, _ = divmod(r, 60)
        e.description = f"다음 젠 까지 {int(d)}일 {int(h)}시간 {int(m)}분 남음\n\n**예정 시간:** {format_dt(spawn_time)}"
    else: e.description = f"**현재 젠 완료 상태입니다!**\n\n**예정 시간:** {format_dt(spawn_time)}"
    if reporter_name: e.set_footer(text=f"제보자: {reporter_name}")
    return e

class DarkRiftActionView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="현재 시간으로 등록", style=discord.ButtonStyle.success)
    async def bn(self, interaction: discord.Interaction, button: discord.ui.Button):
        conn = sqlite3.connect('bdo_data.db'); ex = conn.execute("SELECT kill_time, reporter_name FROM rift_history WHERE id=1").fetchone()
        if ex:
            conn.close()
            e = build_rift_status_embed(datetime.strptime(ex[0], '%Y-%m-%d %H:%M:%S').replace(tzinfo=KST) + timedelta(days=5), ex[1])
            e.description = "⚠️ 이미 제보된 정보가 있습니다.\n\n" + e.description
            await interaction.response.send_message(embed=e, ephemeral=True); schedule_ephemeral_delete(interaction); return
        now = datetime.now(KST)
        conn.execute("INSERT OR REPLACE INTO rift_history (id, reporter_id, reporter_name, kill_time) VALUES (1, ?, ?, ?)", (interaction.user.id, interaction.user.display_name, now.strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit(); conn.close()
        await interaction.response.send_message("✅ 어둠의 틈 처치 시간이 등록되었습니다!", ephemeral=True); schedule_ephemeral_delete(interaction)
        await interaction.channel.send(f"[ {interaction.user.mention} ]\n어둠의 틈 처치 시간 등록 — 다음 젠 예정: {format_dt(now + timedelta(days=5))}")
    @discord.ui.button(label="시간 직접 입력", style=discord.ButtonStyle.secondary)
    async def bm(self, i: discord.Interaction, b: discord.ui.Button):
        conn = sqlite3.connect('bdo_data.db'); ex = conn.execute("SELECT kill_time, reporter_name FROM rift_history WHERE id=1").fetchone(); conn.close()
        if ex:
            e = build_rift_status_embed(datetime.strptime(ex[0], '%Y-%m-%d %H:%M:%S').replace(tzinfo=KST) + timedelta(days=5), ex[1])
            e.description = "⚠️ 이미 제보된 정보가 있습니다.\n\n" + e.description
            await i.response.send_message(embed=e, ephemeral=True); schedule_ephemeral_delete(i); return
        class M(discord.ui.Modal, title='시간 입력'):
            d=discord.ui.TextInput(label='일', required=True); h=discord.ui.TextInput(label='시', required=True); m=discord.ui.TextInput(label='분', required=True)
            async def on_submit(self, interaction: discord.Interaction):
                try: kt = datetime.now(KST).replace(day=int(self.d.value), hour=int(self.h.value), minute=int(self.m.value), second=0, microsecond=0)
                except: await interaction.response.send_message("숫자를 입력해 주세요.", ephemeral=True); schedule_ephemeral_delete(interaction); return
                conn = sqlite3.connect('bdo_data.db')
                conn.execute("INSERT OR REPLACE INTO rift_history VALUES (1, ?, ?, ?)", (interaction.user.id, interaction.user.display_name, kt.strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit(); conn.close()
                await interaction.response.send_message("✅ 어둠의 틈 등록됨!", ephemeral=True); schedule_ephemeral_delete(interaction)
                await interaction.channel.send(f"[ {interaction.user.mention} ]\n다음 젠 예정: {format_dt(kt + timedelta(days=5))}")
        await i.response.send_modal(M())

class BdoTimeView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="현재 시간 확인", style=discord.ButtonStyle.primary, custom_id="bdo_time_check")
    async def btn_check(self, interaction: discord.Interaction, button: discord.ui.Button):
        nt, s, rm = get_bdo_time()
        embed = discord.Embed(title="검은사막 인게임 시간", description=f"현재 인게임 시간: **{nt}**\n상태: **{s}**\n{'밤' if s=='낮' else '낮'} 전환까지 (현실) **{rm}분** 남음", color=0x2b2d31)
        await interaction.response.send_message(embed=embed, ephemeral=True); schedule_ephemeral_delete(interaction)

def _get_status_rows(s_type):
    conn = sqlite3.connect('bdo_data.db')
    rows = conn.execute("SELECT content, timestamp, expire_time FROM status_reports WHERE type=? AND (expire_time IS NULL OR expire_time >= ?) ORDER BY timestamp DESC LIMIT 8", (s_type, (datetime.now(KST) - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S'))).fetchall()
    conn.close()
    return rows

class StatusViewPanel(discord.ui.View):
    def __init__(self, s_type, s_title):
        super().__init__(timeout=None); self.st = s_type; self.stitle = s_title
    @discord.ui.button(label="새 버튼", style=discord.ButtonStyle.primary, custom_id="위치 제보하기")
    async def br(self, i: discord.Interaction, b: discord.ui.Button): await i.response.send_message("제보 기능은 단축 명령을 이용해주세요", ephemeral=True); schedule_ephemeral_delete(i)
    @discord.ui.button(label="위치 현황 보기", style=discord.ButtonStyle.primary, custom_id="status_view_btn")
    async def bf(self, i: discord.Interaction, b: discord.ui.Button):
        rows = _get_status_rows(self.st)
        act = []
        for c, _, ex in rows:
            if not ex: continue
            rs = (datetime.strptime(ex, '%Y-%m-%d %H:%M:%S').replace(tzinfo=KST) - datetime.now(KST)).total_seconds()
            if rs > 0: act.append((c.split(" | ")[0], c.split(" | ")[1] if " | " in c else "-", int(rs)))
        e = discord.Embed(title=f"{self.stitle} 현황", color=0x9b59b6)
        if not act: e.description = "현재 활성화된 제보가 없습니다."
        else: e.description = "\n\n".join([f"**{k}** | {s}\n남은 시간: **{rs//60}분**" for k, s, rs in act])
        await i.response.send_message(embed=e, ephemeral=True); schedule_ephemeral_delete(i)

class SetupUtilityView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    # ── Row 0: 강화 및 공/방 계산
    @discord.ui.button(label="카프라스 계산기", style=discord.ButtonStyle.success, custom_id="util_cap", row=0)
    async def uc(self, i: discord.Interaction, b: discord.ui.Button): await i.response.send_message(embed=discord.Embed(title="카프라스 계산기", description="아래 버튼을 클릭해주세요.", color=0x2ecc71), view=CaphrasSelectView(), ephemeral=True); schedule_ephemeral_delete(i)
    @discord.ui.button(label="공/방 구간 계산기", style=discord.ButtonStyle.danger, custom_id="util_apdp", row=0)
    async def uap(self, i: discord.Interaction, b: discord.ui.Button): await i.response.send_modal(ApDpModal())
    @discord.ui.button(label="포식 계산기", style=discord.ButtonStyle.primary, custom_id="util_devour", row=0)
    async def ud(self, i: discord.Interaction, b: discord.ui.Button): await i.response.send_message(embed=discord.Embed(title="포식 계산기", description="아래 버튼을 클릭해주세요.", color=0x2b2d31), view=DevourSelectView(), ephemeral=True); schedule_ephemeral_delete(i)
    @discord.ui.button(label="군왕 무기 계산기", style=discord.ButtonStyle.secondary, custom_id="util_sov", row=0)
    async def usov(self, i: discord.Interaction, b: discord.ui.Button): await i.response.send_message(embed=discord.Embed(title="군왕 무기 계산기", description="부위를 선택해주세요.", color=0x2b2d31), view=SovWeaponSelectView(), ephemeral=True); schedule_ephemeral_delete(i)
    # ── Row 1: 펄의상 및 거래소 효율
    @discord.ui.button(label="데키아 등불", style=discord.ButtonStyle.secondary, custom_id="util_dekia", row=1)
    async def udek(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.defer(ephemeral=True); schedule_ephemeral_delete(i)
        tasks = [get_market_price(it["id"], it["sid"]) for it in DEKIA_DB]; res = await asyncio.gather(*tasks)
        rk = sorted([{"n":it["name"], "l":it["light"], "p":p, "s":s, "u":p//it["light"]} for it, (p,s,_) in zip(DEKIA_DB, res) if p>0], key=lambda x:x["u"])
        d = "".join([f"**{idx+1}. {r['n']}**\n불빛: {r['l']} | 가격: {r['p']:,}\n**1개당: `{r['u']:,}`**\n\n" for idx, r in enumerate(rk)])
        await i.followup.send(embed=discord.Embed(title="데키아 랭킹", description=d[:4000] or "데이터 없음", color=0xf1c40f), ephemeral=True)
    @discord.ui.button(label="영물의 축복", style=discord.ButtonStyle.secondary, custom_id="util_bless", row=1)
    async def ubless(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.defer(ephemeral=True); schedule_ephemeral_delete(i)
        tasks = [get_market_price(it["id"]) for it in BLESS_DB]; res = await asyncio.gather(*tasks)
        rk = sorted([{"n":it["name"], "r":it["residue"], "p":p, "s":s, "u":p//it["residue"]} for it, (p,s,_) in zip(BLESS_DB, res) if p>0], key=lambda x:x["u"])
        d = "".join([f"**{idx+1}. {r['n']}**\n잔재: {r['r']} | 가격: {r['p']:,}\n**1개당: `{r['u']:,}`**\n\n" for idx, r in enumerate(rk)])
        await i.followup.send(embed=discord.Embed(title="영물 랭킹", description=d[:4000] or "데이터 없음", color=0x2ecc71), ephemeral=True)
    @discord.ui.button(label="펄 의상", style=discord.ButtonStyle.secondary, custom_id="util_pearl", row=1)
    async def upe(self, i: discord.Interaction, b: discord.ui.Button): await i.response.send_message(embed=discord.Embed(title="펄 의상", color=0x2b2d31), view=PearlTimeView(), ephemeral=True); schedule_ephemeral_delete(i)
    @discord.ui.button(label="거래소 실수령액", style=discord.ButtonStyle.secondary, custom_id="util_tax", row=1)
    async def utx(self, i: discord.Interaction, b: discord.ui.Button): await i.response.send_message(embed=discord.Embed(title="거래소 실수령액", color=0x2b2d31), view=TaxSelectView(), ephemeral=True); schedule_ephemeral_delete(i)
    @discord.ui.button(label="아이템 평균가", style=discord.ButtonStyle.secondary, custom_id="util_avg", row=1)
    async def uavg(self, i: discord.Interaction, b: discord.ui.Button): await i.response.send_modal(AvgPriceModal())
    # ── Row 2: 기타
    @discord.ui.button(label="어둠의 틈", style=discord.ButtonStyle.secondary, custom_id="util_rift", row=2)
    async def urift(self, i: discord.Interaction, b: discord.ui.Button):
        conn = sqlite3.connect('bdo_data.db'); row = conn.execute("SELECT kill_time, reporter_name FROM rift_history WHERE id=1").fetchone(); conn.close()
        if row: e = build_rift_status_embed(datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S').replace(tzinfo=KST) + timedelta(days=5), row[1])
        else: e = discord.Embed(title="어둠의 틈", description="기록 없음.", color=0x2b2d31)
        await i.response.send_message(embed=e, view=DarkRiftActionView(), ephemeral=True); schedule_ephemeral_delete(i)
    @discord.ui.button(label="저격 수렵 계산기", style=discord.ButtonStyle.secondary, custom_id="util_snipe", row=2)
    async def usn(self, i: discord.Interaction, b: discord.ui.Button): await i.response.send_message(embed=discord.Embed(title="저격 수렵", color=0x2b2d31), view=SnipeMainView(), ephemeral=True); schedule_ephemeral_delete(i)
    @discord.ui.button(label="제작노트 🔗", style=discord.ButtonStyle.secondary, custom_id="util_craftnote", row=2)
    async def ucn(self, i: discord.Interaction, b: discord.ui.Button): await i.response.send_message("https://bdocodex.com/kr/recipe/", ephemeral=True); schedule_ephemeral_delete(i)

class CloseTicketModal(discord.ui.Modal, title="티켓 종료"):
    comment = discord.ui.TextInput(label="종료 사유 / 코멘트", style=discord.TextStyle.paragraph, required=True, placeholder="처리 결과 등을 적어주세요")
    async def on_submit(self, interaction: discord.Interaction):
        # 생성자 ID 찾기
        creator_id = None
        if interaction.channel.topic and interaction.channel.topic.isdigit():
            creator_id = int(interaction.channel.topic)
        else:
            # fallback: 채널 첫 메시지에서 멘션 찾기
            try:
                async for msg in interaction.channel.history(limit=10, oldest_first=True):
                    if msg.mentions:
                        creator_id = msg.mentions[0].id
                        break
            except: pass
        
        if creator_id:
            user = interaction.guild.get_member(creator_id) or bot.get_user(creator_id)
            if user:
                try:
                    embed = discord.Embed(title="티켓이 종료되었습니다", description=self.comment.value, color=0x95a5a6)
                    embed.add_field(name="처리자", value=interaction.user.mention, inline=False)
                    embed.add_field(name="채널", value=interaction.channel.name, inline=False)
                    await user.send(embed=embed)
                except Exception:
                    pass
        
        await interaction.response.send_message(f"**티켓을 종료합니다. 5초 후 채널이 삭제됩니다.**\n사유: {self.comment.value}")
        await asyncio.sleep(5)
        try: await interaction.channel.delete()
        except: pass

class CloseTicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="티켓 닫기", style=discord.ButtonStyle.danger, custom_id="close_ticket_button_v2")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not (getattr(interaction.user.guild_permissions, 'administrator', False) or interaction.user.get_role(ADMIN_ROLE_ID)):
            await interaction.response.send_message("관리자만 사용 가능합니다.", ephemeral=True); schedule_ephemeral_delete(interaction); return
        await interaction.response.send_modal(CloseTicketModal())


class JoinProcessModal(discord.ui.Modal, title='가입 처리결과 전송'):
    def __init__(self, t_uid: int, is_app: bool): super().__init__(); self.tid = t_uid; self.is_app = is_app
    msg = discord.ui.TextInput(label='전달 내용', style=discord.TextStyle.paragraph, required=True)
    async def on_submit(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True); schedule_ephemeral_delete(i)
        tm = i.guild.get_member(self.tid)
        if not tm: return await i.followup.send("유저 없음", ephemeral=True)
        e = discord.Embed(title="가입 승인됨" if self.is_app else "가입 거절됨", description=self.msg.value, color=0x2ecc71 if self.is_app else 0xe74c3c)
        if self.is_app:
            r = i.guild.get_role(NEWBIE_JOIN_ROLE_ID)
            if r:
                try: await tm.add_roles(r)
                except: await i.followup.send("권한 오류", ephemeral=True); return
        try: await tm.send(embed=e)
        except: pass
        try: await i.channel.delete()
        except: pass

class JoinAdminView(discord.ui.View):
    def __init__(self, t_uid: int): super().__init__(timeout=None); self.tid = t_uid
    @discord.ui.button(label="가입 승인", style=discord.ButtonStyle.success)
    async def ba(self, i: discord.Interaction, b: discord.ui.Button):
        if getattr(i.user.guild_permissions, 'administrator', False) or i.user.get_role(ADMIN_ROLE_ID): await i.response.send_modal(JoinProcessModal(self.tid, True))
        else: await i.response.send_message("관리자 전용", ephemeral=True); schedule_ephemeral_delete(i)
    @discord.ui.button(label="가입 거절", style=discord.ButtonStyle.danger)
    async def br(self, i: discord.Interaction, b: discord.ui.Button):
        if getattr(i.user.guild_permissions, 'administrator', False) or i.user.get_role(ADMIN_ROLE_ID): await i.response.send_modal(JoinProcessModal(self.tid, False))
        else: await i.response.send_message("관리자 전용", ephemeral=True); schedule_ephemeral_delete(i)

class SetupJoinView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @staticmethod
    async def _get_ticket_category(guild: discord.Guild, category_id: int = 0) -> discord.CategoryChannel:
        """지정된 category_id로 카테고리를 찾고, 없거나 0이면 "기타 문의" 카테고리 사용(자동 생성)"""
        if category_id:
            cat = guild.get_channel(category_id)
            if cat and isinstance(cat, discord.CategoryChannel):
                return cat
        cat = discord.utils.get(guild.categories, name="기타 문의")
        if not cat:
            cat = await guild.create_category("기타 문의")
        return cat

    @discord.ui.button(label="가입 상담", style=discord.ButtonStyle.primary, custom_id="join_panel_btn")
    async def bj(self, i: discord.Interaction, b: discord.ui.Button):
        class TicketInputModal(discord.ui.Modal, title='가입 상담 폼'):
            f = discord.ui.TextInput(label='가문명', required=True); s = discord.ui.TextInput(label='플레이 성향 (PVP/PVE/초식)', required=True)
            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=True); schedule_ephemeral_delete(interaction)
                cat = await SetupJoinView._get_ticket_category(interaction.guild, TICKET_CATEGORY_JOIN)
                ch = await cat.create_text_channel(name=f"가입상담-{interaction.user.name}")
                e = discord.Embed(title="가입 상담", description="운영진과 대화 후 처리됩니다.", color=0x2b2d31)
                e.add_field(name="정보", value=f"가문명: {self.f.value}\n성향: {self.s.value}")
                await ch.send(content=interaction.user.mention, embed=e, view=JoinAdminView(interaction.user.id))
                await interaction.followup.send(f"티켓 생성됨: {ch.mention}", ephemeral=True)
        await i.response.send_modal(TicketInputModal())

class CouponInputModal(discord.ui.Modal, title='신규 쿠폰 등록'):
    code = discord.ui.TextInput(label='쿠폰 번호', required=True)
    desc = discord.ui.TextInput(label='쿠폰 내용', style=discord.TextStyle.paragraph, required=False)
    async def on_submit(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True); schedule_ephemeral_delete(i)
        e = discord.Embed(title="🎁 [신규 쿠폰 알림]", color=0x2ecc71)
        e.add_field(name="쿠폰 번호", value=f"`{self.code.value}`", inline=False)
        e.add_field(name="구성품", value=self.desc.value or "내용 없음", inline=False)
        for m in i.guild.members:
            if not m.bot:
                try: await m.send(embed=e)
                except: pass
                await asyncio.sleep(0.1)
        await i.followup.send("쿠폰 전송 완료", ephemeral=True)

class CouponPanelView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="쿠폰 등록", style=discord.ButtonStyle.success, custom_id="admin_coupon_btn")
    async def bc(self, i: discord.Interaction, b: discord.ui.Button):
        if getattr(i.user.guild_permissions, 'administrator', False) or i.user.get_role(ADMIN_ROLE_ID): await i.response.send_modal(CouponInputModal())
        else: await i.response.send_message("관리자 전용", ephemeral=True); schedule_ephemeral_delete(i)

class WeeklyDMModal(discord.ui.Modal, title='주간 DM 수정'):
    def __init__(self, t, m):
        super().__init__()
        self.t = discord.ui.TextInput(label='제목', default=t, required=True)
        self.m = discord.ui.TextInput(label='내용', style=discord.TextStyle.paragraph, default=m, required=True)
        self.add_item(self.t); self.add_item(self.m)
    async def on_submit(self, i: discord.Interaction):
        conn = sqlite3.connect('bdo_data.db')
        conn.execute("INSERT OR REPLACE INTO weekly_dm_settings (guild_id, title, message, enabled) VALUES (?, ?, ?, 1)", (i.guild.id, self.t.value, self.m.value))
        conn.commit(); conn.close()
        await i.response.send_message("주간 DM 설정 저장 완료!", ephemeral=True); schedule_ephemeral_delete(i)

class QnaAdminView(discord.ui.View):
    def __init__(self, t_uid: int): super().__init__(timeout=None); self.tid = t_uid
    @discord.ui.button(label="답변 전송", style=discord.ButtonStyle.success, custom_id="qna_reply_btn")
    async def br(self, i: discord.Interaction, b: discord.ui.Button):
        if not getattr(i.user.guild_permissions, 'administrator', False): return await i.response.send_message("관리자 전용", ephemeral=True); schedule_ephemeral_delete(i)
        class QnaReplyModal(discord.ui.Modal, title='답변 전송'):
            rm = discord.ui.TextInput(label='답변 내용', style=discord.TextStyle.paragraph, required=True)
            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=True); schedule_ephemeral_delete(interaction)
                tm = interaction.guild.get_member(i.view.tid)
                if tm:
                    try: await tm.send(embed=discord.Embed(title="답변", description=self.rm.value, color=0x3498db))
                    except: pass
                try: await interaction.channel.delete()
                except: pass
        await i.response.send_modal(QnaReplyModal())

class ReportCloseModal(discord.ui.Modal, title='불편제보 처리 결과 전송'):
    """불편사항 제보 티켓을 닫으면서 제보자에게 처리 결과를 DM으로 발송"""
    def __init__(self, requester_id: int):
        super().__init__()
        self.requester_id = requester_id
    msg = discord.ui.TextInput(label='처리 결과 / 코멘트', style=discord.TextStyle.paragraph, required=True, placeholder='제보자에게 전달할 내용을 입력하세요')
    async def on_submit(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        member = i.guild.get_member(self.requester_id)
        embed = discord.Embed(title="📋 불편사항 제보 처리 결과", description=self.msg.value, color=0xe67e22)
        embed.set_footer(text=f"처리: {i.user.display_name}")
        if member:
            try: await member.send(embed=embed)
            except Exception: pass
        try: await i.channel.delete()
        except Exception: pass

class ReportAdminView(discord.ui.View):
    """불편사항 제보 티켓 관리 뷰 — 코멘트와 함께 닫기"""
    def __init__(self, requester_id: int):
        super().__init__(timeout=None)
        self.requester_id = requester_id
    @discord.ui.button(label="✅ 처리 완료 및 닫기", style=discord.ButtonStyle.success, custom_id="report_close_btn")
    async def close_with_comment(self, i: discord.Interaction, b: discord.ui.Button):
        if not (getattr(i.user.guild_permissions, 'administrator', False) or i.user.get_role(ADMIN_ROLE_ID)):
            await i.response.send_message("관리자만 사용 가능합니다.", ephemeral=True); return
        await i.response.send_modal(ReportCloseModal(self.requester_id))
    @discord.ui.button(label="🗑 그냥 닫기", style=discord.ButtonStyle.danger, custom_id="report_force_close_btn")
    async def force_close(self, i: discord.Interaction, b: discord.ui.Button):
        if not (getattr(i.user.guild_permissions, 'administrator', False) or i.user.get_role(ADMIN_ROLE_ID)):
            await i.response.send_message("관리자만 사용 가능합니다.", ephemeral=True); return
        await i.response.send_message("5초 후 채널이 삭제됩니다.")
        await asyncio.sleep(5)
        await i.channel.delete()

class AnonCloseModal(discord.ui.Modal, title='익명제보 처리 결과 전송'):
    """익명 제보 티켓을 닫으면서 제보자에게 처리 결과를 DM으로 발송 (익명성 유지)"""
    def __init__(self, requester_id: int):
        super().__init__()
        self.requester_id = requester_id
    msg = discord.ui.TextInput(label='처리 결과 / 코멘트', style=discord.TextStyle.paragraph, required=True, placeholder='제보자에게 전달할 내용을 입력하세요 (발신자 정보 미표시)')
    async def on_submit(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        member = i.guild.get_member(self.requester_id)
        embed = discord.Embed(title="📋 익명 제보 처리 결과", description=self.msg.value, color=0x9b59b6)
        embed.set_footer(text="익명으로 처리된 결과입니다")
        if member:
            try: await member.send(embed=embed)
            except Exception: pass
        try: await i.channel.delete()
        except Exception: pass

class AnonAdminView(discord.ui.View):
    """익명 제보 티켓 관리 뷰 — 제보자 익명성 유지하면서 DM 발송 후 닫기"""
    def __init__(self, t_uid: int):
        super().__init__(timeout=None)
        self.tid = t_uid
    @discord.ui.button(label="✅ 처리 완료 및 닫기", style=discord.ButtonStyle.success, custom_id="anon_close_btn")
    async def close_with_comment(self, i: discord.Interaction, b: discord.ui.Button):
        if not (getattr(i.user.guild_permissions, 'administrator', False) or i.user.get_role(ADMIN_ROLE_ID)):
            await i.response.send_message("관리자만 사용 가능합니다.", ephemeral=True); return
        await i.response.send_modal(AnonCloseModal(self.tid))
    @discord.ui.button(label="🗑 그냥 닫기", style=discord.ButtonStyle.danger, custom_id="anon_force_close_btn")
    async def force_close(self, i: discord.Interaction, b: discord.ui.Button):
        if not (getattr(i.user.guild_permissions, 'administrator', False) or i.user.get_role(ADMIN_ROLE_ID)):
            await i.response.send_message("관리자만 사용 가능합니다.", ephemeral=True); return
        await i.response.send_message("5초 후 채널이 삭제됩니다.")
        await asyncio.sleep(5)
        await i.channel.delete()

class BossAlertSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1시간 전", value="60", description="보스 60분 전 DM"),
            discord.SelectOption(label="30분 전", value="30", description="보스 30분 전 DM"),
            discord.SelectOption(label="10분 전", value="10", description="보스 10분 전 DM"),
        ]
        super().__init__(placeholder="필드보스 알림 시간 선택 (복수 선택 가능)", min_values=1, max_values=3, options=options, custom_id="boss_alert_select")

    async def callback(self, interaction: discord.Interaction):
        conn = sqlite3.connect('bdo_data.db')
        conn.execute("DELETE FROM boss_alert_settings WHERE user_id=?", (interaction.user.id,))
        for v in self.values:
            conn.execute("INSERT OR REPLACE INTO boss_alert_settings (user_id, time_str) VALUES (?,?)", (interaction.user.id, v))
        # 구버전 호환용
        conn.execute("INSERT OR REPLACE INTO boss_alert_users (user_id) VALUES (?)", (interaction.user.id,))
        conn.commit(); conn.close()
        await interaction.response.send_message(f"✅ 알림 설정 완료: {', '.join([v+'분' for v in self.values])} 전에 DM을 보내드립니다.", ephemeral=True)
        schedule_ephemeral_delete(interaction)

class SetupBossView(discord.ui.View):
    def __init__(self): 
        super().__init__(timeout=None)
        self.add_item(BossAlertSelect())
    @discord.ui.button(label="월드보스 시간", style=discord.ButtonStyle.primary, custom_id="boss_time_btn")
    async def bt(self, i: discord.Interaction, b: discord.ui.Button): 
        now = datetime.now(KST)
        day_short = ["월","화","수","목","금","토","일"][now.weekday()]
        bosses = BOSS_DB.get(day_short, [])
        desc = "\n".join([f"`{t}` - {n}" for t,n in bosses]) or "오늘 일정 없음"
        embed = discord.Embed(title=f"오늘({day_short}) 월드보스", description=desc, color=0x3498db)
        await i.response.send_message(embed=embed, ephemeral=True); schedule_ephemeral_delete(i)


class BossTimeSelectView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

class QnaTicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="문의/건의", style=discord.ButtonStyle.primary, custom_id="qna_ticket_btn")
    async def bq(self, i: discord.Interaction, b: discord.ui.Button):
        class TicketInputModal(discord.ui.Modal, title='문의 폼'):
            d = discord.ui.TextInput(label='내용', style=discord.TextStyle.paragraph, required=True)
            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=True); schedule_ephemeral_delete(interaction)
                cat = await SetupJoinView._get_ticket_category(interaction.guild, TICKET_CATEGORY_QNA)
                ch = await cat.create_text_channel(name=f"문의-{interaction.user.name}")
                await ch.send(content=interaction.user.mention, embed=discord.Embed(description=self.d.value), view=QnaAdminView(interaction.user.id))
                await interaction.followup.send(f"티켓 생성됨: {ch.mention}", ephemeral=True)
        await i.response.send_modal(TicketInputModal())

class ReportTicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="불편사항 제보", style=discord.ButtonStyle.danger, custom_id="comp_ticket_btn")
    async def bc(self, i: discord.Interaction, b: discord.ui.Button):
        class TicketInputModal(discord.ui.Modal, title='제보 폼'):
            d = discord.ui.TextInput(label='내용', style=discord.TextStyle.paragraph, required=True)
            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=True); schedule_ephemeral_delete(interaction)
                cat = await SetupJoinView._get_ticket_category(interaction.guild, TICKET_CATEGORY_REPORT)
                ch = await cat.create_text_channel(name=f"불편제보-{interaction.user.name}")
                await ch.send(content=interaction.user.mention, embed=discord.Embed(description=self.d.value), view=ReportAdminView(interaction.user.id))
                await interaction.followup.send(f"티켓 생성됨: {ch.mention}", ephemeral=True)
        await i.response.send_modal(TicketInputModal())

class AnonTicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="익명 제보", style=discord.ButtonStyle.primary, custom_id="anon_ticket_btn")
    async def ba(self, i: discord.Interaction, b: discord.ui.Button):
        class TicketInputModal(discord.ui.Modal, title='익명 제보 폼'):
            d = discord.ui.TextInput(label='내용', style=discord.TextStyle.paragraph, required=True)
            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=True); schedule_ephemeral_delete(interaction)
                cat = await SetupJoinView._get_ticket_category(interaction.guild, TICKET_CATEGORY_ANON)
                ch = await cat.create_text_channel(name=f"익명제보-{datetime.now(KST).strftime('%m%d-%H%M')}")
                await ch.send(embed=discord.Embed(description=self.d.value), view=AnonAdminView(interaction.user.id))
                await interaction.followup.send(f"익명으로 전송되었습니다.", ephemeral=True)
        await i.response.send_modal(TicketInputModal())

class PartyTicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    
    @discord.ui.button(label="아토락시온", style=discord.ButtonStyle.primary, custom_id="party_ato")
    async def ato_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(self.PartyModal("ato"))

    @discord.ui.button(label="검은사당", style=discord.ButtonStyle.primary, custom_id="party_shrine")
    async def shrine_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(self.PartyModal("shrine"))

    @discord.ui.button(label="피의제단", style=discord.ButtonStyle.primary, custom_id="party_blood")
    async def blood_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(self.PartyModal("blood"))

    class PartyModal(discord.ui.Modal):
        def __init__(self, kind: str):
            names = {"ato": "아토락시온", "shrine": "검은사당", "blood": "피의제단"}
            super().__init__(title=f'{names[kind]} 파티 신청')
            self.kind = kind
            self.content = discord.ui.TextInput(label='신청 내용', style=discord.TextStyle.paragraph, required=True, placeholder='역할, 희망 시간대 등')
            self.add_item(self.content)

        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True); schedule_ephemeral_delete(interaction)
            cat_id = {"ato": TICKET_CATEGORY_ATO, "shrine": TICKET_CATEGORY_SHRINE, "blood": TICKET_CATEGORY_BLOOD}[self.kind]
            cat = await SetupJoinView._get_ticket_category(interaction.guild, cat_id)
            names = {"ato": "아토락시온", "shrine": "검은사당", "blood": "피의제단"}
            ch_name = f"{self.kind}-{interaction.user.name}-{datetime.now(KST).strftime('%m%d%H%M')}"
            ch = await cat.create_text_channel(name=ch_name, topic=str(interaction.user.id))
            embed = discord.Embed(title=f"{names[self.kind]} 파티 신청", description=self.content.value, color=0x9b59b6)
            embed.add_field(name="신청자", value=interaction.user.mention, inline=False)
            await ch.send(content=interaction.user.mention, embed=embed, view=CloseTicketView())
            await interaction.followup.send(f"티켓 생성됨: {ch.mention}", ephemeral=True)


class DarkRiftManualModal(discord.ui.Modal, title='어둠의 틈 시간 입력'):
    day_input = discord.ui.TextInput(label='잡은 날짜 (일)', placeholder='예: 27', required=True, max_length=2)
    hour_input = discord.ui.TextInput(label='잡은 시각 (시)', placeholder='예: 14', required=True, max_length=2)
    minute_input = discord.ui.TextInput(label='잡은 시각 (분)', placeholder='예: 30', required=True, max_length=2)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            d, h, m = int(self.day_input.value), int(self.hour_input.value), int(self.minute_input.value)
            now = datetime.now(KST)
            kill_time = now.replace(day=d, hour=h, minute=m, second=0, microsecond=0)
            conn = sqlite3.connect('bdo_data.db')
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO rift_history (id, reporter_id, reporter_name, kill_time) VALUES (1, ?, ?, ?)",
                      (interaction.user.id, interaction.user.display_name, kill_time.strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit(); conn.close()
            spawn_time = kill_time + timedelta(days=5)
            await interaction.response.send_message("✅ 어둠의 틈 처치 시간이 등록되었습니다!", ephemeral=True)
            schedule_ephemeral_delete(interaction)
            await interaction.channel.send(
                f"[ {interaction.user.mention} ]\n어둠의 틈 처치 시간 등록 — 다음 젠 예정: {format_dt(spawn_time)}"
            )
        except ValueError:
            await interaction.response.send_message("날짜와 시간을 올바른 숫자로 입력해 주세요.", ephemeral=True)
            schedule_ephemeral_delete(interaction)


# ==========================================
# [현황 제보 시스템 - 버튼 체인 (종류 -> 서버 -> 시간)]
# ==========================================
STATUS_KIND_OPTIONS = {
    "blessing": ["해축", "달축", "땅축"],
    "edana": ["아에테리온", "님파마레", "오르비타", "테네브라움", "제피로스"],
}
STATUS_SERVER_REGIONS = [
    "발레노스", "세렌디아", "칼페온", "메디아", "발렌시아", "카마실비아",
    "드라간", "오딜리타", "끝없는 겨울의 산", "아침의 나라", "엘비아"
]
# 지역별 번호 수가 다름: 발레노스~카마실비아=1/2/3, 나머지=1/2
STATUS_SERVER_NUMBERS = {
    "발레노스": ["1","2","3"], "세렌디아": ["1","2","3"], "칼페온": ["1","2","3"],
    "메디아": ["1","2","3"], "발렌시아": ["1","2","3"], "카마실비아": ["1","2","3"],
    "드라간": ["1","2"], "오딜리타": ["1","2"], "끝없는 겨울의 산": ["1","2"],
    "아침의 나라": ["1","2"], "엘비아": ["1","2"],
}
STATUS_DEFAULT_MINUTES = {"blessing": 180, "edana": 60}
STATUS_TITLES = {"blessing": "아침의 축복", "edana": "에다니아"}

async def get_status_notify_channel(s_type, fallback_channel):
    conn = sqlite3.connect('bdo_data.db')
    c = conn.cursor()
    c.execute("SELECT channel_id FROM status_notify_channels WHERE s_type=?", (s_type,))
    row = c.fetchone()
    conn.close()
    if row:
        channel = bot.get_channel(row[0])
        if channel:
            return channel
    return fallback_channel

async def finalize_status_report(interaction: discord.Interaction, s_type, kind, server, minutes):
    s_title = STATUS_TITLES[s_type]
    now = datetime.now(KST)
    expire_time = now + timedelta(minutes=minutes)
    report_content = f"{kind} | {server} | 남은시간: {minutes}분"

    conn = sqlite3.connect('bdo_data.db')
    c = conn.cursor()
    c.execute(
        "INSERT INTO status_reports (type, user_id, content, timestamp, expire_time) VALUES (?, ?, ?, ?, ?)",
        (s_type, interaction.user.id, report_content, now.strftime('%Y-%m-%d %H:%M:%S'), expire_time.strftime('%Y-%m-%d %H:%M:%S'))
    )
    c.execute("SELECT user_id FROM status_alert_users")
    alert_users = c.fetchall()
    conn.commit(); conn.close()

    await interaction.response.send_message(f"✅ {s_title} 제보가 등록되었습니다! (**{kind}** / **{server}** / {minutes}분)", ephemeral=True)

    target_channel = await get_status_notify_channel(s_type, interaction.channel)
    expire_ts = int(expire_time.timestamp())
    report_text = f"[ {interaction.user.mention} ]\n@{kind} {server} <t:{expire_ts}:t>까지"
    try:
        public_msg = await target_channel.send(report_text)
        async def _delete_later(msg):
            await asyncio.sleep(180)
            try: await msg.delete()
            except: pass
        bot.loop.create_task(_delete_later(public_msg))
    except: pass

    dm_embed = discord.Embed(title=f"새로운 {s_title} 제보 도착!", color=0x3498db)
    dm_embed.description = f"**종류:** {kind}\n**서버:** {server}\n**남은 시간:** {minutes}분"
    for (u_id,) in alert_users:
        user = bot.get_user(u_id)
        if user and user.id != interaction.user.id:
            try: await user.send(embed=dm_embed)
            except: pass

class StatusManualTimeModal(discord.ui.Modal, title="시간 직접 입력"):
    hour_input = discord.ui.TextInput(label='남은 시간 (시)', placeholder='예: 1  (없으면 0)', required=True, max_length=2)
    minute_input = discord.ui.TextInput(label='남은 시간 (분)', placeholder='예: 30  (없으면 0)', required=True, max_length=2)

    def __init__(self, s_type, kind, server):
        super().__init__()
        self.s_type, self.kind, self.server = s_type, kind, server

    async def on_submit(self, interaction: discord.Interaction):
        try:
            hours = int(self.hour_input.value)
            mins = int(self.minute_input.value)
            total_minutes = hours * 60 + mins
            if total_minutes <= 0: raise ValueError
        except ValueError:
            await interaction.response.send_message("시간과 분을 올바른 숫자로 입력해주세요. (합산 1분 이상)", ephemeral=True)
            return
        await finalize_status_report(interaction, self.s_type, self.kind, self.server, total_minutes)

class StatusTimeSelectView(discord.ui.View):
    def __init__(self, s_type, kind, server):
        super().__init__(timeout=120)
        self.s_type, self.kind, self.server = s_type, kind, server
        default_min = STATUS_DEFAULT_MINUTES[s_type]
        label = f"{default_min // 60}시간" if default_min % 60 == 0 else f"{default_min}분"

        btn_default = discord.ui.Button(label=label, style=discord.ButtonStyle.success)
        btn_default.callback = self.btn_default_callback
        self.add_item(btn_default)

        btn_manual = discord.ui.Button(label="직접 시간 작성", style=discord.ButtonStyle.secondary)
        btn_manual.callback = self.btn_manual_callback
        self.add_item(btn_manual)

    async def btn_default_callback(self, interaction: discord.Interaction):
        await finalize_status_report(interaction, self.s_type, self.kind, self.server, STATUS_DEFAULT_MINUTES[self.s_type])

    async def btn_manual_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(StatusManualTimeModal(self.s_type, self.kind, self.server))

class StatusServerNumberSelectView(discord.ui.View):
    def __init__(self, s_type, kind, region):
        super().__init__(timeout=120)
        self.s_type, self.kind, self.region = s_type, kind, region
        # 지역별 번호 목록을 딕셔너리에서 가져옴 (없으면 기본 1/2/3)
        numbers = STATUS_SERVER_NUMBERS.get(region, ["1","2","3"])
        for num in numbers:
            btn = discord.ui.Button(label=f"{region}{num}", style=discord.ButtonStyle.primary)
            btn.callback = self._make_callback(f"{region}{num}")
            self.add_item(btn)

    def _make_callback(self, server):
        async def callback(interaction: discord.Interaction):
            s_title = STATUS_TITLES[self.s_type]
            embed = discord.Embed(title=f"{s_title} 제보", description=f"**종류:** {self.kind}\n**서버:** {server}\n\n남은 시간을 선택해주세요.", color=0x2b2d31)
            await interaction.response.edit_message(embed=embed, view=StatusTimeSelectView(self.s_type, self.kind, server))
        return callback

class StatusServerSelectView(discord.ui.View):
    def __init__(self, s_type, kind):
        super().__init__(timeout=120)
        self.s_type, self.kind = s_type, kind
        for region in STATUS_SERVER_REGIONS:
            btn = discord.ui.Button(label=region, style=discord.ButtonStyle.primary)
            btn.callback = self._make_callback(region)
            self.add_item(btn)

    def _make_callback(self, region):
        async def callback(interaction: discord.Interaction):
            s_title = STATUS_TITLES[self.s_type]
            embed = discord.Embed(title=f"{s_title} 제보", description=f"**종류:** {self.kind}\n**지역:** {region}\n\n서버 번호를 선택해주세요.", color=0x2b2d31)
            await interaction.response.edit_message(embed=embed, view=StatusServerNumberSelectView(self.s_type, self.kind, region))
        return callback

class StatusKindSelectView(discord.ui.View):
    def __init__(self, s_type):
        super().__init__(timeout=120)
        self.s_type = s_type
        for kind in STATUS_KIND_OPTIONS[s_type]:
            btn = discord.ui.Button(label=kind, style=discord.ButtonStyle.primary)
            btn.callback = self._make_callback(kind)
            self.add_item(btn)

    def _make_callback(self, kind):
        async def callback(interaction: discord.Interaction):
            s_title = STATUS_TITLES[self.s_type]
            embed = discord.Embed(title=f"{s_title} 제보", description=f"**종류:** {kind}\n\n서버를 선택해주세요.", color=0x2b2d31)
            await interaction.response.edit_message(embed=embed, view=StatusServerSelectView(self.s_type, kind))
        return callback


def build_status_view_embed(s_type, s_title, rows):
    embed = discord.Embed(title=f"아침의 축복 현황" if s_type == "blessing" else f"{s_title} 현황", color=0x9b59b6)
    now = datetime.now(KST)

    active = []
    for content, timestamp_str, expire_str in rows:
        if not expire_str:
            continue
        expire_time = datetime.strptime(expire_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=KST)
        remain_sec = (expire_time - now).total_seconds()
        if remain_sec <= 0:
            continue
        parts = content.split(" | ")
        kind = parts[0] if len(parts) >= 1 else content
        server = parts[1] if len(parts) >= 2 else "-"
        active.append((kind, server, int(remain_sec)))

    if not active:
        embed.description = "현재 활성화된 제보가 없습니다."
    else:
        desc = ""
        for kind, server, remain_sec in active:
            h, m = divmod(remain_sec // 60, 60)
            if h > 0:
                remain_text = f"{h}시간 {m}분"
            else:
                remain_text = f"{m}분"
            desc += f"**{kind}** | {server}\n남은 시간: **{remain_text}**\n\n"
        embed.description = desc

    embed.set_footer(text=f"갱신 시각: {now.strftime('%H:%M:%S')} · 1분마다 자동 갱신")
    return embed


def _get_status_rows(s_type):
    conn = sqlite3.connect('bdo_data.db')
    c = conn.cursor()
    cutoff = (datetime.now(KST) - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
    c.execute(
        "SELECT content, timestamp, expire_time FROM status_reports WHERE type=? AND (expire_time IS NULL OR expire_time >= ?) ORDER BY timestamp DESC LIMIT 8",
        (s_type, cutoff)
    )
    rows = c.fetchall()
    conn.close()
    return rows

class QnaReplyModal(discord.ui.Modal, title='문의/건의 답변 전송'):
    reply_message = discord.ui.TextInput(label='답변 내용', style=discord.TextStyle.paragraph, required=True, max_length=1500)

    def __init__(self, target_user_id: int):
        super().__init__()
        self.target_user_id = target_user_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        target_member = interaction.guild.get_member(self.target_user_id)
        if not target_member:
            await interaction.followup.send("유저를 찾을 수 없어 처리를 중단합니다.", ephemeral=True)
            return
        embed = discord.Embed(title="문의/건의 답변이 도착했습니다.", description="관리자의 답변 메시지입니다.", color=0x3498db)
        embed.add_field(name="답변 내용", value=make_codeblock(self.reply_message.value), inline=False)
        try:
            await target_member.send(embed=embed)
        except:
            await interaction.followup.send("DM 전송에 실패했습니다. (상대방이 DM을 막았을 수 있습니다.)", ephemeral=True)
            return
        try:
            await interaction.channel.delete(reason="문의/건의 처리 완료")
        except:
            pass

class AnonReplyModal(discord.ui.Modal, title='익명 제보 답변 전송'):
    reply_message = discord.ui.TextInput(label='답변 내용', style=discord.TextStyle.paragraph, required=True, max_length=1500)

    def __init__(self, target_user_id: int):
        super().__init__()
        self.target_user_id = target_user_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        target_user = bot.get_user(self.target_user_id)
        if not target_user:
            await interaction.followup.send("제보자 정보를 찾을 수 없습니다.", ephemeral=True)
            return
        embed = discord.Embed(title="익명 제보에 대한 답변이 도착했습니다.", description="관리자의 답변 메시지입니다. (익명 처리된 채널을 통해 전달됩니다.)", color=0x2c3e50)
        embed.add_field(name="답변 내용", value=make_codeblock(self.reply_message.value), inline=False)
        try:
            await target_user.send(embed=embed)
        except:
            await interaction.followup.send("DM 전송에 실패했습니다. (상대방이 DM을 막았을 수 있습니다.)", ephemeral=True)
            return
        try:
            await interaction.channel.delete(reason="익명 제보 처리 완료")
        except:
            pass

class AnonymousReportModal(discord.ui.Modal, title='익명 제보 작성'):
    report_title = discord.ui.TextInput(label='제목', required=True, max_length=50)
    report_content = discord.ui.TextInput(label='내용 (관리자만 볼 수 있습니다)', style=discord.TextStyle.paragraph, required=True, max_length=1500)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        category = await get_or_create_category(interaction.guild, "anon")
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        admin_role = interaction.guild.get_role(ADMIN_ROLE_ID)
        if admin_role: overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        now_str = datetime.now(KST).strftime('%m%d-%H%M')
        try:
            channel = await category.create_text_channel(name=f"익명제보-{now_str}", overwrites=overwrites, topic="익명 제보 채널")
            embed = discord.Embed(title="새로운 익명 제보", color=0x2c3e50)
            embed.add_field(name="제목", value=self.report_title.value, inline=False)
            embed.add_field(name="내용", value=make_codeblock(self.report_content.value), inline=False)
            embed.set_footer(text=f"제보자 식별 정보는 관리자 채널에만 기록됩니다. | uid:{interaction.user.id}")
            await channel.send(embed=embed, view=AnonAdminView(interaction.user.id))
            await interaction.followup.send("제보가 100% 익명으로 관리자에게 전달되었습니다.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send("채널 생성 오류가 발생했습니다.", ephemeral=True)

class TicketInputModal(discord.ui.Modal):
    def __init__(self, ticket_type: str):
        self.ticket_type = ticket_type
        titles = {
            "join": "가입 상담 폼", "qna": "문의 및 건의 폼", "comp": "불편 사항 제보 폼", "error": "오류 제보 폼",
            "ato": "아토락시온 파티 구인", "shrine": "검은사당 파티 구인", "blood": "피의제단 파티 구인"
        }
        super().__init__(title=titles.get(ticket_type, "정보 입력"))
        self.inputs = {}
        
        if ticket_type in ["ato", "shrine", "blood"]:
            self.inputs['family'] = discord.ui.TextInput(label='가문명/캐릭터명', required=True)
            self.inputs['stats'] = discord.ui.TextInput(label='공/방합계', required=True)
            self.inputs['desc'] = discord.ui.TextInput(label='신청 내용', style=discord.TextStyle.paragraph, required=True)
            self.add_item(self.inputs['family']); self.add_item(self.inputs['stats']); self.add_item(self.inputs['desc'])

        elif ticket_type == "join":
            self.inputs['family'] = discord.ui.TextInput(label='가문명', required=True)
            self.inputs['style'] = discord.ui.TextInput(label='플레이 성향 (PVP/PVE/초식)', required=True)
            self.add_item(self.inputs['family']); self.add_item(self.inputs['style'])

        elif ticket_type == "comp":
            self.inputs['target'] = discord.ui.TextInput(label='신고자(대상)', required=True)
            self.inputs['time'] = discord.ui.TextInput(label='사건 발생 시간', required=True)
            self.inputs['desc'] = discord.ui.TextInput(label='상황 설명 및 증거 (로그 요청 가능)', style=discord.TextStyle.paragraph, required=True)
            self.add_item(self.inputs['target']); self.add_item(self.inputs['time']); self.add_item(self.inputs['desc'])
            
        elif ticket_type in ["qna", "error"]:
            self.inputs['title'] = discord.ui.TextInput(label='제목', required=True)
            self.inputs['desc'] = discord.ui.TextInput(label='내용', style=discord.TextStyle.paragraph, required=True)
            self.add_item(self.inputs['title']); self.add_item(self.inputs['desc'])

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        category = await get_or_create_category(interaction.guild, self.ticket_type)
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True, attach_files=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        admin_role = interaction.guild.get_role(ADMIN_ROLE_ID)
        if admin_role: overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        embed = discord.Embed(color=0x2b2d31)
        view_to_attach = CloseTicketView() 
        
        if self.ticket_type == "join":
            channel_name = f"가입상담-{interaction.user.name}"
            embed.title = "가입 상담"
            embed.description = "가입 상담이 시작되었습니다. 운영진과 대화 후 가입 승인 또는 거절됩니다."
            embed.add_field(name="제목", value="가입 상담", inline=False)
            embed.add_field(name="요청자", value=interaction.user.mention, inline=False)
            embed.add_field(name="정리 기준", value="봇이 만든 임시 문의 채널만 닫기/삭제합니다.", inline=False)
            embed.add_field(name="가입 처리", value="승인 시 매핑된 일반 멤버 역할을 지급합니다.", inline=False)
            join_info = "**가문명:** " + self.inputs['family'].value + "\n**성향:** " + self.inputs['style'].value
            embed.add_field(name="제출 정보", value=join_info, inline=False)
            view_to_attach = JoinAdminView(interaction.user.id) 
            
        elif self.ticket_type == "qna":
            channel_name = f"문의건의-{interaction.user.name}"
            embed.title = "문의 / 건의"
            embed.add_field(name="제목", value=self.inputs['title'].value, inline=False)
            embed.add_field(name="요청자", value=interaction.user.mention, inline=False)
            embed.add_field(name="상세 내용", value=make_codeblock(self.inputs['desc'].value), inline=False)
            view_to_attach = QnaAdminView(interaction.user.id)
            
        elif self.ticket_type == "error":
            channel_name = f"오제보-{interaction.user.name}"
            embed.title = "오제보 / 젠타임 오류"
            embed.description = "오제보 내용확인"
            embed.add_field(name="제목", value=self.inputs['title'].value, inline=False)
            embed.add_field(name="요청자", value=interaction.user.mention, inline=False)
            embed.add_field(name="정리 기준", value="봇이 만든 임시 문의 채널만 닫기/삭제합니다.", inline=False)
            embed.add_field(name="상세 내용", value=make_codeblock(self.inputs['desc'].value), inline=False)
            
        elif self.ticket_type == "comp":
            channel_name = f"불편제보-{interaction.user.name}"
            embed.title = "불편 사항 제보"
            embed.description = "서버 규칙 위반이나 불편사항 제보입니다."
            embed.add_field(name="제목", value="불편 사항 제보", inline=False)
            embed.add_field(name="요청자", value=interaction.user.mention, inline=False)
            embed.add_field(name="정리 기준", value="봇이 만든 임시 문의 채널만 닫기/삭제합니다.", inline=False)
            comp_info = "**신고자/대상:** " + self.inputs['target'].value + "\n**발생 시간:** " + self.inputs['time'].value + "\n**상황 설명:**\n" + make_codeblock(self.inputs['desc'].value)
            embed.add_field(name="제출 정보", value=comp_info, inline=False)
            
        elif self.ticket_type in ["ato", "shrine", "blood"]:
            if self.ticket_type == "ato":
                channel_name = f"아토락시온-{interaction.user.name}"
                embed.title = "아토락시온 파티 신청"
                embed.add_field(name="제목", value="아토락시온 파티", inline=False)
            elif self.ticket_type == "shrine":
                channel_name = f"검은사당-{interaction.user.name}"
                embed.title = "검은사당 파티 신청"
                embed.add_field(name="제목", value="검은사당 파티", inline=False)
            elif self.ticket_type == "blood":
                channel_name = f"피의제단-{interaction.user.name}"
                embed.title = "피의제단 파티 신청"
                embed.add_field(name="제목", value="피의제단 파티", inline=False)

            embed.add_field(name="요청자", value=interaction.user.mention, inline=False)
            party_info = f"**가문명/캐릭터명:** {self.inputs['family'].value}\n**공/방합계:** {self.inputs['stats'].value}\n**신청 내용:**\n" + make_codeblock(self.inputs['desc'].value)
            embed.add_field(name="제출 정보", value=party_info, inline=False)

        try:
            channel = await category.create_text_channel(name=channel_name, overwrites=overwrites)
            await channel.send(content=interaction.user.mention, embed=embed, view=view_to_attach)
            await interaction.followup.send(f"티켓 생성이 완료되었습니다: {channel.mention}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send("채널 생성 오류가 발생했습니다.", ephemeral=True)

class BossDaySelectView(discord.ui.View):
    """요일을 드롭다운으로 선택해서 해당 요일의 필드보스 시간표를 보여준다."""
    def __init__(self):
        super().__init__(timeout=120)
        today_str = WEEKDAYS[datetime.now(KST).weekday()][0]
        options = [
            discord.SelectOption(label=f"{day}요일{' (오늘)' if day == today_str else ''}", value=day)
            for day in ["월", "화", "수", "목", "금", "토", "일"]
        ]
        self.select = discord.ui.Select(placeholder="요일을 선택해주세요", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        day = self.select.values[0]
        today_str = WEEKDAYS[datetime.now(KST).weekday()][0]
        title_suffix = " (오늘)" if day == today_str else ""
        embed = discord.Embed(title=f"{day}요일 월드 보스 시간표{title_suffix}", color=0xf39c12)
        bosses = BOSS_DB.get(day, [])
        if bosses:
            embed.description = "".join([f"**{t}** : {b}\n\n" for t, b in bosses])
        else:
            embed.description = "등록된 보스 일정이 없습니다."
        await interaction.response.edit_message(embed=embed, view=self)

class WeeklyDmEditModal(discord.ui.Modal, title='주간 DM 내용 수정'):
    dm_title = discord.ui.TextInput(
        label='제목',
        placeholder='예: 이번 주 길드 공지',
        required=True,
        max_length=100
    )
    dm_description = discord.ui.TextInput(
        label='본문',
        style=discord.TextStyle.paragraph,
        placeholder='DM으로 보낼 내용을 입력하세요.',
        required=True,
        max_length=2000
    )
    dm_footer = discord.ui.TextInput(
        label='푸터 (선택)',
        placeholder='예: 시나모롤 길드',
        required=False,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        conn = sqlite3.connect('bdo_data.db')
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO weekly_dm_content (id, title, description, footer) VALUES (1, ?, ?, ?)",
            (self.dm_title.value, self.dm_description.value, self.dm_footer.value or None)
        )
        conn.commit(); conn.close()
        embed = discord.Embed(title="✅ 주간 DM 내용 저장 완료", color=0x2ecc71)
        embed.add_field(name="제목", value=self.dm_title.value, inline=False)
        embed.add_field(name="본문 미리보기", value=self.dm_description.value[:500], inline=False)
        if self.dm_footer.value:
            embed.set_footer(text=self.dm_footer.value)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class OfficialLinksView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for link in OFFICIAL_LINKS:
            self.add_item(discord.ui.Button(
                label=link["label"],
                style=discord.ButtonStyle.link,
                url=link["url"]
            ))

# ==========================================
# [루프 및 이벤트]
# ==========================================
@tasks.loop(minutes=1)
async def weekly_dm_loop():
    now = datetime.now(KST)
    if now.weekday() != 5 or now.hour != 18 or now.minute != 0: return
    conn = sqlite3.connect('bdo_data.db')
    rows = conn.execute("SELECT guild_id, title, message FROM weekly_dm_settings WHERE enabled=1").fetchall()
    conn.close()
    sent_users = set()
    for g_id, title, msg in rows:
        guild = bot.get_guild(g_id)
        if not guild: continue
        embed = discord.Embed(title=title, description=msg, color=0xf39c12)
        await guild.chunk()
        for m in guild.members:
            if m.bot or m.id in sent_users: continue
            try:
                await m.send(embed=embed)
                sent_users.add(m.id)
                await asyncio.sleep(0.1)
            except: sent_users.add(m.id)

@tasks.loop(seconds=60)
async def boss_alert_loop():
    """매분 필드보스 알림 체크 — 설정된 시간(60/30/10분 전)에 DM 발송"""
    now = datetime.now(KST)
    day_short = ["월","화","수","목","금","토","일"][now.weekday()]
    bosses_today = BOSS_DB.get(day_short, [])

    for time_str, boss_name in bosses_today:
        bh, bm = map(int, time_str.split(":"))
        boss_dt = now.replace(hour=bh, minute=bm, second=0, microsecond=0)
        if boss_dt < now:
            continue
        diff_min = int((boss_dt - now).total_seconds() // 60)
        
        for minutes in [60, 30, 10]:
            if diff_min == minutes:
                conn = sqlite3.connect('bdo_data.db')
                alert_users = conn.execute("SELECT user_id FROM boss_alert_settings WHERE time_str=?", (str(minutes),)).fetchall()
                # 구버전 사용자도 10분은 받게
                if minutes == 10:
                    legacy = conn.execute("SELECT user_id FROM boss_alert_users").fetchall()
                    alert_users += legacy
                conn.close()
                
                # 중복 제거
                uids = list({uid for (uid,) in alert_users})
                if not uids:
                    continue
                    
                embed = discord.Embed(
                    title=f"⚔️ 필드보스 {minutes}분 전 알림",
                    description=f"**{boss_name}** 등장까지 약 {minutes}분 남았습니다!\n⏰ 등장 시각: **{time_str}**",
                    color=0xe74c3c
                )
                for uid in uids:
                    user = bot.get_user(uid)
                    if user:
                        try:
                            await user.send(embed=embed)
                        except Exception:
                            pass


@tasks.loop(seconds=60)
async def rift_alert_loop():
    """어둠의 틈 예정 시간 1시간 전 알림"""
    now = datetime.now(KST)
    conn = sqlite3.connect('bdo_data.db')
    row = conn.execute("SELECT kill_time FROM rift_history WHERE id=1").fetchone()
    conn.close()
    if not row:
        return
    kill_time = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S').replace(tzinfo=KST)
    spawn_time = kill_time + timedelta(days=5)
    diff = spawn_time - now
    # 1시간 전 1분 윈도우
    if not (timedelta(minutes=59) < diff <= timedelta(hours=1)):
        return

    embed = discord.Embed(
        title="🌑 어둠의 틈 1시간 전 알림",
        description=f"어둠의 틈 출현 예정 시각: **{spawn_time.strftime('%m/%d %H:%M')}**\n약 1시간 후 출현 예정입니다!",
        color=0x2c2f33
    )
    for guild in bot.guilds:
        conn = sqlite3.connect('bdo_data.db')
        row2 = conn.execute("SELECT channel_id FROM boss_alert_channels WHERE guild_id=?", (guild.id,)).fetchone()
        conn.close()
        if row2:
            ch = bot.get_channel(row2[0])
            if ch:
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass

@tasks.loop(minutes=10)
async def pearl_tracker():
    """펄 의상 거래 수 추적 — 10분마다 PEARL_OUTFIT_DB 아이템 거래소 데이터 수집"""
    conn = sqlite3.connect('bdo_data.db')
    now_str = datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')
    for item in PEARL_OUTFIT_DB:
        try:
            entries = await fetch_market_sublist(item['id'])
            if not entries:
                continue
            entry = entries[0]
            conn.execute(
                "INSERT INTO pearl_history (item_id, timestamp, total_trades, stock) VALUES (?,?,?,?)",
                (item['id'], now_str, entry.get('total_trades', 0), entry.get('current_stock', 0))
            )
        except Exception:
            pass
    conn.commit()
    conn.close()

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.guild and message.channel.id == BROADCAST_CHANNEL_ID:
        if getattr(message.author.guild_permissions, 'administrator', False) or message.guild.get_role(ADMIN_ROLE_ID) in message.author.roles:
            embed = discord.Embed(title="📢 [길드 공지사항]", description=message.content, color=0xe74c3c)
            if message.attachments: embed.set_image(url=message.attachments[0].url)
            sent_u = set()
            await message.guild.chunk()
            for m in message.guild.members:
                if not m.bot and m.id not in sent_u:
                    try: await m.send(embed=embed); sent_u.add(m.id)
                    except: pass
                    await asyncio.sleep(0.1)
            await message.add_reaction("✅")
    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    if member.bot: return
    try: await member.send(embed=discord.Embed(title="환영합니다!", color=0x87CEEB))
    except: pass

@bot.event
async def on_ready():
    init_db()
    if not boss_alert_loop.is_running(): boss_alert_loop.start()
    if not rift_alert_loop.is_running(): rift_alert_loop.start()
    if not pearl_tracker.is_running(): pearl_tracker.start()
    if not weekly_dm_loop.is_running(): weekly_dm_loop.start()
    await bot.change_presence(activity=discord.Game("시나모롤 길드 도우미 V2"))
    print(f'봇 로그인 성공: {bot.user.name}')

@bot.tree.command(name="내용수정", description="[관리자] 매주 토요일 18:00 자동 DM 메시지를 수정합니다.")
async def edit_weekly_dm(interaction: discord.Interaction):
    if not getattr(interaction.user.guild_permissions, 'administrator', False) and not interaction.user.get_role(ADMIN_ROLE_ID):
        await interaction.response.send_message("관리자만 사용 가능합니다.", ephemeral=True); schedule_ephemeral_delete(interaction); return
    conn = sqlite3.connect('bdo_data.db')
    row = conn.execute("SELECT title, message FROM weekly_dm_settings WHERE guild_id=?", (interaction.guild.id,)).fetchone()
    conn.close()
    await interaction.response.send_modal(WeeklyDMModal(row[0] if row else "이번 주 길드 공지", row[1] if row else "내용을 입력하세요"))


# --- 설치-필드보스 ---
@bot.tree.command(name="설치-필드보스", description="필드보스 채널용 패널 설치")
@discord.app_commands.default_permissions(administrator=True)
async def setup_boss(interaction: discord.Interaction):
    embed = discord.Embed(title="월드보스 시간표", description="월드보스 출현 일정 조회 및 개인 DM 알림 설정을 제공합니다.", color=0x2b2d31)
    await interaction.channel.send(embed=embed, view=SetupBossView())
    await interaction.response.send_message("설치 완료", ephemeral=True)

# --- 설치-축복제보 ---
@bot.tree.command(name="설치-축복제보", description="아침의 축복 제보 채널용 패널 설치")
@discord.app_commands.default_permissions(administrator=True)
async def setup_bless(interaction: discord.Interaction):
    embed = discord.Embed(title="아침의 축복 현황", description="하단 버튼을 통해 새로운 위치를 제보하거나 현황을 확인하세요.", color=0x2b2d31)
    await interaction.channel.send(embed=embed, view=StatusViewPanel("blessing", "아침의 축복"))
    await interaction.response.send_message("설치 완료", ephemeral=True)

# --- 설치-에다니아제보 ---
@bot.tree.command(name="설치-에다니아제보", description="에다니아 제보 채널용 패널 설치")
@discord.app_commands.default_permissions(administrator=True)
async def setup_edana(interaction: discord.Interaction):
    embed = discord.Embed(title="에다니아 현황", description="하단 버튼을 통해 새로운 위치를 제보하거나 현황을 확인하세요.", color=0x2b2d31)
    await interaction.channel.send(embed=embed, view=StatusViewPanel("edana", "에다니아"))
    await interaction.response.send_message("설치 완료", ephemeral=True)

# --- 제보채널확인 ---
@bot.tree.command(name="제보채널확인", description="[관리자] 현재 설정된 축복/에다니아 제보 채널을 확인합니다")
@discord.app_commands.default_permissions(administrator=True)
async def check_status_notify_channel(interaction: discord.Interaction):
    conn = sqlite3.connect('bdo_data.db')
    c = conn.cursor()
    c.execute("SELECT s_type, channel_id FROM status_notify_channels")
    rows = dict(c.fetchall())
    conn.close()
    lines = []
    for s_type, label in [("blessing", "아침의 축복"), ("edana", "에다니아")]:
        if s_type in rows:
            ch = bot.get_channel(rows[s_type])
            lines.append(f"**{label}**: {ch.mention if ch else f'(알 수 없음, id={rows[s_type]})'}")
        else:
            lines.append(f"**{label}**: 지정 안 됨 (패널이 설치된 채널로 전송됩니다)")
    embed = discord.Embed(title="제보 알림 채널 설정 현황", description="\n".join(lines), color=0x2b2d31)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- 설치-인게임시간 ---
@bot.tree.command(name="설치-인게임시간", description="검은사막 인게임 시간 확인 패널 설치")
@discord.app_commands.default_permissions(administrator=True)
async def setup_bdo_time(interaction: discord.Interaction):
    embed = discord.Embed(title="검은사막 인게임시간", color=0x2b2d31)
    await interaction.channel.send(embed=embed, view=BdoTimeView())
    await interaction.response.send_message("인게임 시간 패널 설치 완료", ephemeral=True)

# --- 아이템디버그 ---
@bot.tree.command(name="아이템디버그", description="[관리자] ITEM_LIST에 등록된 실제 이름/ID를 검색합니다")
@discord.app_commands.default_permissions(administrator=True)
async def debug_item_list(interaction: discord.Interaction, 키워드: str):
    await interaction.response.defer(ephemeral=True)
    if not ITEM_LIST:
        await interaction.followup.send("ITEM_LIST가 아직 로드되지 않았습니다.", ephemeral=True); return

    key = 키워드.replace(" ", "")
    # 1) 부분일치 전부
    exact_hits = [(n, i) for n, i in ITEM_LIST.items() if key in n.replace(" ", "")]
    # 2) fuzzy 매칭 (컷오프 없이 점수 그대로 보여줌, 디버그용)
    fuzzy_hits = process.extractBests(키워드, ITEM_LIST.keys(), limit=10)

    lines = [f"🔎 `{키워드}` 검색 결과 (ITEM_LIST 총 {len(ITEM_LIST)}개)\n"]
    lines.append(f"**부분일치: {len(exact_hits)}건**")
    for n, i in exact_hits[:15]:
        lines.append(f"  - `{n}` → id={i}")
    if not exact_hits:
        lines.append("  (없음)")

    lines.append(f"\n**유사도 매칭 (thefuzz, 컷오프 없음, 상위 10개)**")
    for n, score in fuzzy_hits:
        lines.append(f"  - `{n}` ({score}점) → id={ITEM_LIST[n]}")

    text = "\n".join(lines)
    if len(text) > 1900: text = text[:1900] + "\n...(생략)"
    await interaction.followup.send(make_codeblock(text), ephemeral=True)

# ==========================================
# [신규 유저 자동 DM 환영 시스템]
# ==========================================


class UtilContainer(discord.ui.Container):
    def __init__(self, *, id=None):
        super().__init__(id=id, accent_color=0x2b2d31)
        self.add_item(discord.ui.TextDisplay("**[편의기능]**"))
        self.add_item(discord.ui.TextDisplay("🗡️ 강화 및 공/방 계산"))
        row1 = discord.ui.ActionRow()
        row1.add_item(discord.ui.Button(label="카프라스 계산기", style=discord.ButtonStyle.success, custom_id="util_cap"))
        row1.add_item(discord.ui.Button(label="공/방 구간 계산기", style=discord.ButtonStyle.danger, custom_id="util_apdp"))
        row1.add_item(discord.ui.Button(label="포식 계산기", style=discord.ButtonStyle.primary, custom_id="util_devour"))
        row1.add_item(discord.ui.Button(label="군왕 무기 계산기", style=discord.ButtonStyle.secondary, custom_id="util_sov"))
        self.add_item(row1)
        self.add_item(discord.ui.Separator(spacing=1))
        self.add_item(discord.ui.TextDisplay("💰 펄의상 및 거래소 효율 계산"))
        row2 = discord.ui.ActionRow()
        for label, cid in [("데키아 등불","util_dekia"), ("영물의 축복","util_spirit"), ("펄 의상","util_pearl"), ("거래소 실수령액","util_tax"), ("아이템 평가액","util_avg")]:
            row2.add_item(discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, custom_id=cid))
        self.add_item(row2)
        self.add_item(discord.ui.Separator(spacing=1))
        self.add_item(discord.ui.TextDisplay("📋 기타"))
        row3 = discord.ui.ActionRow()
        row3.add_item(discord.ui.Button(label="어둠의 틈", style=discord.ButtonStyle.secondary, custom_id="util_rift"))
        row3.add_item(discord.ui.Button(label="저격 수렵 계산기", style=discord.ButtonStyle.secondary, custom_id="util_snipe"))
        row3.add_item(discord.ui.Button(label="제작노트", style=discord.ButtonStyle.link, url="https://korbdo.co.kr/#craft"))
        self.add_item(row3)

class UtilView(discord.ui.LayoutView):
    container = UtilContainer(id=1)

@bot.tree.command(name="설치-편의기능", description="[관리자] 편의기능 패널 설치 v2 (Components V2)")
async def cmd_install_util(interaction: discord.Interaction):
    if not getattr(interaction.user.guild_permissions, 'administrator', False) and not interaction.user.get_role(ADMIN_ROLE_ID):
        await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True); schedule_ephemeral_delete(interaction); return
    await interaction.channel.send(view=UtilView())
    await interaction.response.send_message("✅ 편의기능 패널(v2) 설치 완료", ephemeral=True); schedule_ephemeral_delete(interaction)
@bot.tree.command(name="설치-쿠폰등록", description="[관리자] 쿠폰 등록 패널 설치")
async def cmd_install_coupon(interaction: discord.Interaction):
    if not getattr(interaction.user.guild_permissions, 'administrator', False) and not interaction.user.get_role(ADMIN_ROLE_ID):
        await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True); schedule_ephemeral_delete(interaction); return
    await interaction.channel.send(view=CouponPanelView())
    await interaction.response.send_message("✅ 쿠폰 등록 패널 설치 완료", ephemeral=True); schedule_ephemeral_delete(interaction)

@bot.tree.command(name="설치-가입상담", description="[관리자] 가입 상담 티켓 패널 설치")
async def cmd_install_join(interaction: discord.Interaction):
    if not getattr(interaction.user.guild_permissions, 'administrator', False) and not interaction.user.get_role(ADMIN_ROLE_ID):
        await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True); schedule_ephemeral_delete(interaction); return
    embed = discord.Embed(title="📋 가입 상담", description="가입을 원하시면 아래 버튼을 눌러 상담 티켓을 생성해주세요.", color=0x3498db)
    await interaction.channel.send(embed=embed, view=SetupJoinView())
    await interaction.response.send_message("✅ 가입 상담 패널 설치 완료", ephemeral=True); schedule_ephemeral_delete(interaction)

@bot.tree.command(name="설치-문의건의", description="[관리자] 문의/건의 티켓 패널 설치")
async def cmd_install_qna(interaction: discord.Interaction):
    if not getattr(interaction.user.guild_permissions, 'administrator', False) and not interaction.user.get_role(ADMIN_ROLE_ID):
        await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True); schedule_ephemeral_delete(interaction); return
    embed = discord.Embed(title="💬 문의/건의", description="문의나 건의사항이 있으시면 아래 버튼을 눌러 티켓을 생성해주세요.", color=0x2ecc71)
    await interaction.channel.send(embed=embed, view=QnaTicketView())
    await interaction.response.send_message("✅ 문의/건의 패널 설치 완료", ephemeral=True); schedule_ephemeral_delete(interaction)

@bot.tree.command(name="설치-불편제보", description="[관리자] 불편사항 제보 티켓 패널 설치")
async def cmd_install_report(interaction: discord.Interaction):
    if not getattr(interaction.user.guild_permissions, 'administrator', False) and not interaction.user.get_role(ADMIN_ROLE_ID):
        await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True); schedule_ephemeral_delete(interaction); return
    embed = discord.Embed(title="🚨 불편사항 제보", description="불편사항이 있으시면 아래 버튼을 눌러 제보해주세요.", color=0xe74c3c)
    await interaction.channel.send(embed=embed, view=ReportTicketView())
    await interaction.response.send_message("✅ 불편제보 패널 설치 완료", ephemeral=True); schedule_ephemeral_delete(interaction)

@bot.tree.command(name="설치-익명제보", description="[관리자] 익명 제보 티켓 패널 설치")
async def cmd_install_anon(interaction: discord.Interaction):
    if not getattr(interaction.user.guild_permissions, 'administrator', False) and not interaction.user.get_role(ADMIN_ROLE_ID):
        await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True); schedule_ephemeral_delete(interaction); return
    embed = discord.Embed(title="🕵️ 익명 제보", description="익명으로 제보하시려면 아래 버튼을 눌러주세요.", color=0x95a5a6)
    await interaction.channel.send(embed=embed, view=AnonTicketView())
    await interaction.response.send_message("✅ 익명제보 패널 설치 완료", ephemeral=True); schedule_ephemeral_delete(interaction)

@bot.tree.command(name="설치-파티신청", description="[관리자] 파티 신청 티켓 패널 설치")
async def cmd_install_party(interaction: discord.Interaction):
    if not getattr(interaction.user.guild_permissions, 'administrator', False) and not interaction.user.get_role(ADMIN_ROLE_ID):
        await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True); schedule_ephemeral_delete(interaction); return
    embed = discord.Embed(title="⚔️ 파티 신청", description="파티에 참가하려면 아래 버튼을 눌러 신청해주세요.", color=0x9b59b6)
    await interaction.channel.send(embed=embed, view=PartyTicketView())
    await interaction.response.send_message("✅ 파티신청 패널 설치 완료", ephemeral=True); schedule_ephemeral_delete(interaction)

@bot.tree.command(name="설치-공식링크", description="[관리자] 공식 링크 패널 설치")
async def cmd_install_links(interaction: discord.Interaction):
    if not getattr(interaction.user.guild_permissions, 'administrator', False) and not interaction.user.get_role(ADMIN_ROLE_ID):
        await interaction.response.send_message("관리자만 사용할 수 있습니다.", ephemeral=True); schedule_ephemeral_delete(interaction); return
    embed = discord.Embed(title="🔗 공식 링크", description="검은사막 공식 사이트 바로가기", color=0x2b2d31)
    await interaction.channel.send(embed=embed, view=OfficialLinksView())
    await interaction.response.send_message("✅ 공식링크 패널 설치 완료", ephemeral=True); schedule_ephemeral_delete(interaction)

# ==========================================
# [아이템 DB 로드 함수]
# ==========================================
async def load_item_dump(force: bool = False) -> str:
    """
    force=False : items_v2.json 파일이 있으면 바로 로컬 파일 사용 (시간 무관)
    force=True  : arsha dump를 새로 받아서 ITEM_LIST와 items_v2.json 갱신 (/아이템디비갱신 명령어)
    반환값: 결과 요약 문자열 (로그/응답용)
    """
    global ITEM_LIST
    HARDCODED = {"카프라스의 돌": 721003, "기억의 파편": 44195, "블랙스톤 (무기)": 16001,
                 "블랙스톤 (방어구)": 16002, "뾰족한 흑결정 조각": 4998, "단단한 흑결정 조각": 4997,
                 "크론석": 16080, "고대 정령의 가루": 721002, "데보레카 목걸이": 11653,
                 "프리오네 반지": 705535, "프리오네 귀걸이": 705534}

    # force=False 이고 items_v2.json이 있으면 로컬 백업으로 바로 로드
    if not force and os.path.exists("items_v2.json"):
        with open("items_v2.json", "r", encoding="utf-8") as f:
            backup = json.load(f)
        ITEM_LIST.update(backup)
        ITEM_LIST.update(HARDCODED)
        msg = f"↩️ 로컬 백업(items_v2.json) 사용: {len(backup)}개 로드됨. 현재 ITEM_LIST 총 {len(ITEM_LIST)}개"
        print(msg)
        return msg

    # arsha dump 시도
    try:
        url = "https://api.arsha.io/util/db/dump?lang=kr"
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        async with aiohttp.ClientSession(headers=headers, connector=aiohttp.TCPConnector(ssl=False)) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status != 200:
                    raise RuntimeError(f"dump API status {response.status}")
                data = await response.json()
                if not isinstance(data, list) or not data:
                    raise RuntimeError(f"dump 응답 비정상: type={type(data)}")

                temp = {}
                skipped = 0
                for item in data:
                    name = item.get("name")
                    id_raw = item.get("id")
                    if not name or id_raw is None:
                        skipped += 1; continue
                    iid = int(id_raw)
                    if name not in temp or iid < temp[name]:
                        temp[name] = iid
                ITEM_LIST.update(temp)
                ITEM_LIST.update(HARDCODED)

                with open("items_v2.json", "w", encoding="utf-8") as f:
                    json.dump(ITEM_LIST, f, ensure_ascii=False, indent=2)

                msg = f"✅ dump 갱신 완료: {len(data)}건 수신, {skipped}건 스킵\n현재 ITEM_LIST 총 {len(ITEM_LIST)}개"
                print(msg)
                return msg

    except Exception as e:
        print(f"⚠️ dump 로드 실패: {type(e).__name__}: {e}")
        if os.path.exists("items_v2.json"):
            with open("items_v2.json", "r", encoding="utf-8") as f:
                backup = json.load(f)
            ITEM_LIST.update(backup)
            ITEM_LIST.update(HARDCODED)
            msg = f"↩️ dump 실패, 로컬 백업 사용: {len(backup)}개 로드됨\n현재 ITEM_LIST 총 {len(ITEM_LIST)}개"
            print(msg)
            return msg
        else:
            msg = f"❌ dump 실패 + 로컬 백업 없음. HARDCODED {len(HARDCODED)}개만 사용 중"
            print(msg)
            ITEM_LIST.update(HARDCODED)
            return msg

# ==========================================
# [최종 봇 구동 (에러 방지)]
# ==========================================
async def setup_hook():
    global ITEM_LIST
    HARDCODED = {"카프라스의 돌": 721003, "기억의 파편": 44195, "블랙스톤 (무기)": 16001, "블랙스톤 (방어구)": 16002, "뾰족한 흑결정 조각": 4998, "단단한 흑결정 조각": 4997, "크론석": 16080, "고대 정령의 가루": 721002, "데보레카 목걸이": 11653, "프리오네 반지": 705535, "프리오네 귀걸이": 705534}
    ITEM_LIST.update(HARDCODED)
    print("📥 검은사막 아이템 DB 다운로드 중...")
    await load_item_dump(force=False)

    try:
        await bot.load_extension("cogs.music")
        await bot.load_extension("cogs.tts")
        print("🎵 music / tts 코그 로드 완료")
    except Exception as e:
        print(f"⚠️ 코그 로드 실패 (폴더나 파일이 없는지 확인하세요): {e}")

    bot.add_view(SetupJoinView())
    bot.add_view(SetupBossView())
    bot.add_view(BossTimeSelectView())
    bot.add_view(SetupUtilityView())
    bot.add_view(UtilView())
    bot.add_view(ReportTicketView())
    bot.add_view(AnonTicketView())
    bot.add_view(QnaTicketView())
    bot.add_view(CloseTicketView())
    bot.add_view(QnaAdminView(0))
    bot.add_view(ReportAdminView(0))
    bot.add_view(AnonAdminView(0))
    bot.add_view(StatusViewPanel("blessing", "아침의 축복"))
    bot.add_view(StatusViewPanel("edana", "에다니아"))
    bot.add_view(PartyTicketView())
    bot.add_view(BdoTimeView())
    bot.add_view(CouponPanelView())
    bot.add_view(OfficialLinksView())
    
    await bot.tree.sync()


bot.setup_hook = setup_hook

# 봇 실행
token = os.getenv('DISCORD_TOKEN')
if not token:
    print("❌ 오류: .env 파일에서 DISCORD_TOKEN을 찾을 수 없습니다!")
    exit()
bot.run(token)