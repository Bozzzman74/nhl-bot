import telebot
import requests
import time
from datetime import datetime, timedelta

TOKEN = "8575181767:AAGQkZFgEuo1gZI0WL0F08JjeNgahGU0ZgI"
MY_CHAT_ID = 1219361161
API_BASE = "https://api-web.nhle.com/v1"

def fetch(url):
    headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"}
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                return r.json()
            time.sleep(1)
        except Exception:
            if attempt == 2:
                return None
            time.sleep(1)
    return None

# --- Сбор истории за 60 дней ---
team_recent_goals = {}
h2h_stats = {}
days_back = 60

end = datetime.now()
start = end - timedelta(days=days_back)
current = start

while current <= end:
    date_str = current.strftime("%Y-%m-%d")
    data = fetch(f"{API_BASE}/schedule/{date_str}")
    if data and "gameWeek" in data:
        for day in data["gameWeek"]:
            if day.get("date") == date_str:
                for g in day.get("games", []):
                    if g.get("gameState") in ["FINAL", "OFF"]:
                        game_id = g["id"]
                        home_abb = g["homeTeam"].get("abbrev", "")
                        away_abb = g["awayTeam"].get("abbrev", "")

                        landing = fetch(f"{API_BASE}/gamecenter/{game_id}/landing")
                        if landing and "homeTeam" in landing:
                            h_score = landing["homeTeam"].get("score", 0)
                            a_score = landing["awayTeam"].get("score", 0)

                            if home_abb:
                                team_recent_goals.setdefault(home_abb, []).append(h_score)
                            if away_abb:
                                team_recent_goals.setdefault(away_abb, []).append(a_score)

                            period_bts = {"1": 0, "2": 0, "3": 0}
                            if "summary" in landing and "scoring" in landing["summary"]:
                                for p_data in landing["summary"]["scoring"]:
                                    p_num = str(p_data["periodDescriptor"]["number"])
                                    if p_num in ["1", "2", "3"]:
                                        scorers = set()
                                        for goal in p_data.get("goals", []):
                                            scorers.add(goal.get("teamAbbrev", {}).get("default", ""))
                                        if home_abb in scorers and away_abb in scorers:
                                            period_bts[p_num] = 1

                            pairs = [(home_abb, away_abb), (away_abb, home_abb)]
                            for pair in pairs:
                                if pair[0] and pair[1]:
                                    if pair not in h2h_stats:
                                        h2h_stats[pair] = {"1": [], "2": [], "3": []}
                                    for p in ["1", "2", "3"]:
                                        h2h_stats[pair][p].append(period_bts[p_num] if p == p_num else 0)
    current += timedelta(days=1)
    time.sleep(0.1)

# Обрезаем до последних 5 матчей
for team in team_recent_goals:
    team_recent_goals[team] = team_recent_goals[team][-5:]
for pair in h2h_stats:
    for p in ["1", "2", "3"]:
        h2h_stats[pair][p] = h2h_stats[pair][p][-5:]

# --- Усталость (B2B) ---
yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
yesterday_teams = set()
data_yesterday = fetch(f"{API_BASE}/schedule/{yesterday_str}")
if data_yesterday and "gameWeek" in data_yesterday:
    for day in data_yesterday["gameWeek"]:
        if day.get("date") == yesterday_str:
            for g in day.get("games", []):
                if g.get("gameState") in ["FINAL", "OFF"]:
                    yesterday_teams.add(g["homeTeam"].get("abbrev", ""))
                    yesterday_teams.add(g["awayTeam"].get("abbrev", ""))
# --- Матчи на сегодня ---
today_str = datetime.now().strftime("%Y-%m-%d")
data_today = fetch(f"{API_BASE}/schedule/{today_str}")
games_today = []
if data_today and "gameWeek" in data_today:
    for day in data_today["gameWeek"]:
        if day.get("date") == today_str:
            games_today = day.get("games", [])
            break

if not games_today:
    message = " Сегодня матчей НХЛ нет. Отдыхаем!"
else:
    lines = [f"🧠  **FULL GAME ПРОГНОЗ НХЛ на {today_str}**\n"]
    base_probs = {"1": 35.4, "2": 32.3, "3": 38.5}

    for g in games_today:
        home_name = g["homeTeam"].get("placeName", {}).get("default", g["homeTeam"].get("abbrev", "HOME"))
        away_name = g["awayTeam"].get("placeName", {}).get("default", g["awayTeam"].get("abbrev", "AWAY"))
        home_abb = g["homeTeam"].get("abbrev", "")
        away_abb = g["awayTeam"].get("abbrev", "")

        home_avg = sum(team_recent_goals.get(home_abb, [3.0])) / len(team_recent_goals.get(home_abb, [3.0]))
        away_avg = sum(team_recent_goals.get(away_abb, [3.0])) / len(team_recent_goals.get(away_abb, [3.0]))
        combined_avg = home_avg + away_avg

        probs = {}
        h2h_texts = {}
        for p in ["1", "2", "3"]:
            prob = base_probs[p] + (combined_avg - 6.0) * 4.0
            h2h_list = h2h_stats.get((home_abb, away_abb), {}).get(p, [])
            if h2h_list:
                h2h_prob = (sum(h2h_list) / len(h2h_list)) * 100
                prob = (prob * 0.7) + (h2h_prob * 0.3)
                h2h_texts[p] = f"{int(h2h_prob)}%"
            else:
                h2h_texts[p] = "н/д"

            is_b2b = (home_abb in yesterday_teams) or (away_abb in yesterday_teams)
            if is_b2b:
                prob -= 6.0 if p == "3" else 3.0
            probs[p] = max(10.0, min(85.0, prob))

        b2b_text = "️ B2B" if is_b2b else "✅ OK"
        form_text = f"⚡ {away_avg:.1f} vs {home_avg:.1f} г/м"

        lines.append(f"🏒  **{away_name} @ {home_name}**")
        lines.append(f"   📊  1-й: **{probs['1']:.1f}%** | 2-й: **{probs['2']:.1f}%** | 3-й: **{probs['3']:.1f}%**")
        lines.append(f"   ℹ️  {form_text} | H2H: 1-й({h2h_texts['1']}) 2-й({h2h_texts['2']}) 3-й({h2h_texts['3']}) | {b2b_text}")
        lines.append("")

    message = "\n".join(lines)

# --- Отправка в Telegram ---
bot = telebot.TeleBot(TOKEN)
try:
    bot.send_message(MY_CHAT_ID, message, parse_mode='Markdown')
except Exception:
    pass
