# UPL Tower Bot

A Discord bot for managing a ladder system with challenges, match reporting, and betting.

This bot allows players to join a ladder, challenge each other, report match results, and place bets on matches.

---

# Requirements

- Python **3.10+**
- A Discord bot application
- Dependencies listed in `requirements.txt`

---

# Installation

## 1. Clone the repository

```bash
git clone https://github.com/GeforceTesla/UPL-Tower-Bot.git
cd UPL-Tower-Bot
```

## 2. Create a virtual environment

### Linux / macOS
```
python3 -m venv venv
source venv/bin/activate
```

## 3. Install dependencies`
Dependencies are listed in `requirements.txt`.
```bash
pip install -r requirements.txt
```

# Discord Bot Setup

## 1. Discord Permissions

```
bot
applications.commands
Select permissions
View Channels
Send Messages
Read Message History
Create Public Threads
Send Messages in Threads
Manage Threads
Manage Roles
Attach Files
```

# Environment Variables
The bot token must be provided as an environment variable.

### Linux / macOS
``` bash
export DISCORD_TOKEN="YOUR_TOKEN_HERE"
```

# Running the Bot
Start the bot with:
``` bash
python main.py
```

A database file will automatically be created on first startup.
Default file:
`challenge_bot.sqlite3`
You can override the location with:

### Linux / macOS
``` bash
export CHALLENGE_DB="/path/to/database.sqlite3"
```


# Commands
## Ladder Commands
### Join the ladder
``` bash
/join
```
Adds yourself to the ladder.

### Leave the ladder
``` bash
/withdraw
```
Removes yourself from the ladder.

### View ladder
``` bash
/ladder
```

### Displays the current ladder rankings.

#### View player profile
``` bash
/profile
```

Shows your ladder position and betting balance.

## Challenge Commands
### Start a challenge
```bash
/challenge defender:@Player
```
Creates a challenge and opens a challenge thread.

### View current challenge
```bash
/mychallenge
```
Shows the current active challenge.

### Ban a map
```bash
/ban map_name:"Map Name"
```
Records a map ban for the challenge.

### Pick the first map
```bash
/pickmap map_name:"Map Name"
```
Selects the first map of the match.

### Report match result
```bash
/report score:"2-1"
```
Records the match result.

### Cancel a challenge
```bash
/cancel
```
Cancels the active challenge.

## Betting Commands
### Check balance
```bash
/balance
```
Displays your betting balance.

### Place a bet
```bash
/bet challenge_id:ID pick:@Player amount:NUMBER
```

## Map Pool Commands
### Show current map pool
```bash
/maps
```
Displays the current map pool used for new challenges.

## Match History
### Show recent matches
```bash
/history
```
Displays recently reported matches.
