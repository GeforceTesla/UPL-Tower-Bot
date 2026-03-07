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

## Discord Permissions

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
Adds yourself to the ladder. New player starts at the bottom of the ladder.

### Leave the ladder
``` bash
/withdraw
```
Removes yourself from the ladder. All player below moves up after a player withdraws.

## Displays the current ladder rankings.
### View ladder
``` bash
/ladder
```

Example output:
``` bash
S Tier
#1 Alpha
#2 Beta
#3 Gamma

A Tier
#7 Delta
#8 Epsilon
```

### View Players
``` bash
/players
```

Show players from rank 1 to X and indicate whether you can challenge them.
Example output:

``` bash
#1 Alpha [S] AVAILABLE
#2 Beta [S] PROTECTED
#3 Gamma [A] AVAILABLE
#4 Delta [A] REMATCH BLOCKED
```

Status meanings:

``` bash
AVAILABLE
You can challenge this player.

PROTECTED
The player cannot be challenged yet due to defender cooldown.

COOLDOWN
You cannot initiate a new challenge yet.

REMATCH BLOCKED
You must challenge other players before challenging this one again.
```

### View player profile
``` bash
/profile
```

Show your player profile.
Example output:

``` bash
Player: Alpha
Rank: #3
Tier: S
Balance: 1150
```

## Challenge Commands
### Challenge eligibility

``` bash
/eligible
```
Show the list of players you can challenge right now.

This command evaluates all ladder rules and returns only valid opponents.

Rules checked include:

``` bash
Tier restrictions

Initiator cooldown

Defender protection

Rematch restrictions

Active challenge conflicts
```

Example output:

``` bash
Eligible opponents

#4 Beta [S]
#5 Gamma [A]
#6 Delta [A]
```

If no players are available:

``` bash
No eligible players to challenge.
```

Possible reasons players may not appear:

``` bash
You are currently in cooldown.

The opponent is protected after a recent match.

The opponent is too many tiers above.

You must challenge other players before re-challenging the same opponent.

Either player already has an active challenge.
```

### Start a challenge
``` bash
/challenge defender:@Player
```
Creates a challenge and opens a challenge thread.

Result:

A challenge is created.

A challenge thread is created automatically.

Thread title example:

``` bash
[#12] Alpha (#5) ⚔ Beta (#4)
```

### View current challenge
``` bash
/mychallenge
```
Shows the current active challenge.

Example output:
``` bash
Challenge ID: 12
Challenger: Alpha
Defender: Beta
Status: Waiting for map bans
```


### Ban a map
```bash
/ban map_name:"Map Name"
```
Ban a map for the current challenge.

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

Result:

Match is recorded.

Ladder positions update.

Thread closes automatically.

Betting results settle.

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
``` bash
/maps
```
Displays the current map pool used for new challenges.

Example output:

``` bash
Map Pool
Fighting Spirit
Polypoid
Circuit Breaker
Destination
Eclipse
Heartbreak Ridge
```

## Match History
### Show recent matches
``` bash
/history
```
Displays recently reported matches.

Example output:
``` bash
Match #11
Alpha vs Beta
Result: 2-1

Match #10
Gamma vs Delta
Result: 2-0
```

## Admin Commands

Admin commands require Manage Server permission.

### Initialize ladder with existing data

``` bash
/admin_seed_ladder
```

Paste player mentions in order:
``` bash
@Player1
@Player2
@Player3
@Player4
```

Result:

Ladder is initialized.

Rankings are assigned.

### Display rules for ladder

``` bash
/admin_rules
```

Example output:

``` bash
Initiator cooldown: 2d
Defender protection: 7d
Rematch requirement: 2
Players per bracket: 6
```

### Change ladder rules

``` bash
/admin_set_rules
```

Example:
``` bash
/admin_set_rules initiator_cd:2d defender_cd:7d rematch_count:2 bracket_size:6
```

Parameters:
``` bash
initiator_cd: Cooldown before a challenger can initiate again.
defender_cd: Time a player is protected after being challenged.
rematch_count: Number of other defenders required before re-challenging the same player.
bracket_size: Number of players in each tier bracket.
```

Example inputs:
``` bash
30s: 30 seconds
10m: 10 minutes
2h: 2 hours
1d: 1 day
```

# Example Match Flow
1. Player joins ladder

``` bash
/join
```

2. Player starts challenge

``` bash
/challenge defender:@Beta
```

3. Map bans (initiator first, then defender)

``` bash
/ban map_name:"Fighting Spirit"
```

4. Defender picks map

``` bash
/pickmap map_name:"Circuit Breaker"
```

5. Match is played. Winner reports result.

``` bash
/report score:"2-1"
```

Ladder updates automatically.
