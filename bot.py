import discord
from bs4 import BeautifulSoup
from discord.ext import commands
import asyncio
from playwright.async_api import async_playwright
from git import Repo
import json
import os
import re
from flask import Flask
import threading
import requests
import time
import subprocess

app = Flask(__name__)

LOCAL_PATH = "tmp/Altered-Rennes-Cup"
GITHUB_USER = "altered-rennes-cup"
GITHUB_EMAIL = "masquime.35@gmail.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GITHUB_REPO_URL = f"https://{GITHUB_TOKEN}@github.com/maxime-boussin/Altered-Rennes-Cup.git"

print("Démarrage...")
# Activer les intents
intents = discord.Intents.default()
intents.message_content = True

os.environ["GIT_ASKPASS"] = "echo"
os.environ["GIT_TERMINAL_PROMPT"] = "0"

bot = commands.Bot(command_prefix="!", intents=intents)

@app.route('/')
def home():
    return "Le bot est en ligne !"

@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user}")

@bot.command()
async def match(ctx, url: str):
    message = await scrapeBga(url)
    await ctx.send(message)

@bot.command()
async def matchIRL(ctx, player1: str, player2: str, winner: int):
    winner = winner - 1
    message = await setMatch([player1, player2], winner)
    await ctx.send(message)

async def scrapeBga(url):
    message = "Erreur lors de la réccupération du match."
    fond_table = re.search(r"(?:table=)?(\d{9,})", url)
    if not fond_table:
        return ":x:Table inexistante:x:"
    table = fond_table.group(1)
    url = f"https://boardgamearena.com/table?table={table}"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url)
        await page.wait_for_selector(".game_result", timeout=30000)
        html_content = await page.content()

        soup = BeautifulSoup(html_content, "html.parser")
        game_result = soup.select_one(".game_result")

        if game_result:
            players = game_result.select(".score-entry .name a")
            rank = game_result.select_one(".score-entry .rank").get_text()[0]
            players_obj = update_json([players[0].get_text(), players[1].get_text()], players[0].get_text() if rank == "1" else players[1].get_text(), table)
            if players_obj[0][0] == None:
                await browser.close()
                return players_obj[1]
            winner = players_obj[0][0] if rank == "1" else players_obj[0][1]
            message = f"{players_obj[0][0]['name']} :crossed_swords: {players_obj[0][1]['name']}\n"
            message += f"**Gagnant:** {winner['name']}\n{players_obj[1]}"
        else:
            message = "Match introuvable. :question:"
        await browser.close()
        return message

async def setMatch(players, win):
    res = update_json(players, players[win], "x")[1]
    message = f"{players[0]} :crossed_swords: {players[1]}\n"
    message += f"**Gagnant:** {players[win]}\n{res}"
    return message

def update_json(players, winner, table):
    message = ""
    # Cloner le repo si ce n'est pas déjà fait
    if not os.path.exists(LOCAL_PATH):
        Repo.clone_from(GITHUB_REPO_URL, LOCAL_PATH)
    repo = Repo(LOCAL_PATH)
    origin = repo.remotes.origin
    origin.pull()

    # Charger le JSON existant
    json_info = os.path.join(LOCAL_PATH, "data/info.json")
    with open(json_info, "r", encoding="utf-8") as f:
        data = json.load(f)
    season = data[-1]["season"]
    main_repo = f"{LOCAL_PATH}/data/saison-{season}"

    json_players = os.path.join(main_repo, "players.json")
    with open(json_players, "r", encoding="utf-8") as f:
        data = json.load(f)
    player1 = next((item for item in data if item.get("bga") == players[0]), None)
    if player1 == None:
        player1 = next((item for item in data if item.get("name") == players[0]), None)
    player2 = next((item for item in data if item.get("bga") == players[1]), None)
    if player2 == None:
        player2 = next((item for item in data if item.get("name") == players[1]), None)
    if not player1 or not player2:
        return [[None, None], "Joueurs inconnus :prohibited:"]
    winner = player1 if player1.get("bga") == winner else (player1 if player1.get("name") == winner else player2)
    json_groups = os.path.join(main_repo, "groups.json")
    match_found = False
    with open(json_groups, "r", encoding="utf-8") as f:
        data = json.load(f)
    for param in data:
        for duel in param.get("matches"):
            if sorted(duel.get("opponents")) == sorted([player1.get("id"), player2.get("id")]) and duel.get("winner") == 0:
                if duel.get("winner") == 0:
                    duel["winner"] = winner.get("id")
                    duel["link"] = table
                    match_found = True
                    message = "Match de poule enregistré."
                    with open(json_groups, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)
                    break
                else:
                    message = "Match déjà enregistré. :floppy_disk:"
        else:
            continue
        break
    if not match_found:
        json_tournament = os.path.join(main_repo, "tournament.json")
        with open(json_tournament, "r", encoding="utf-8") as f:
            data = json.load(f)
        j = 0
        for phase in data:
            i = 0
            j = j + 1
            for duel in phase:
                if sorted(duel.get("opponents")) == sorted([player1.get("id"), player2.get("id")]):
                    if duel.get("winner") == 0:
                        duel["winner"] = winner.get("id")
                        duel["link"] = table
                        if j < len(data):
                            data[j][i // 2]["opponents"][i % 2] = winner.get("id")
                        match_found = True
                        message = "Match du tournoi enregistré. "
                        with open(json_tournament, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=4, ensure_ascii=False)
                        break
                    else:
                        message = "Match déjà enregistré. :floppy_disk:"
                i = i + 1
            else:
                continue
            break
    if not match_found and message != "Match déjà enregistré. :floppy_disk:":
        message = "Aucun match trouvé."
    if repo.is_dirty():
        repo.git.add(json_groups.replace("\\", "/").replace("tmp/Altered-Rennes-Cup/", ""))
        repo.git.add(json_tournament.replace("\\", "/").replace("tmp/Altered-Rennes-Cup/", ""))
        repo.index.commit("📊 Mise à jour automatique des scores via bot Discord 🤖")
        repo.git.push(GITHUB_REPO_URL, "main")
        print("commit et pushed")
    else:
        print(f"rien à commit")

    return [[player1, player2], message]


def run_flask():
    app.run(host="0.0.0.0", port=os.getenv("PORT"))

def keep_awake():
    while True:
        try:
            requests.get("https://arc-bot.onrender.com")
            print("Ping envoyé à l'application")
        except Exception as e:
            print("Erreur lors du ping :", e)
        time.sleep(300)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=keep_awake, daemon=True).start()
    asyncio.run(bot.start(DISCORD_TOKEN))