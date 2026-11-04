
import sqlite3
import pymongo

MONGO_URI = "mongodb://root:Q2006%40Ff@127.0.0.1:27017/voiceclaw?authSource=admin"
client = pymongo.MongoClient(MONGO_URI)
db = client["voiceclaw"]

print("[Mongo VPS] Connected to voiceclaw database!")

con = sqlite3.connect('/root/VoiceClaw/voice.db')
con.row_factory = sqlite3.Row
cur = con.cursor()

tables = [t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() if t[0] != 'sqlite_sequence']
total_migrated = 0

for table in tables:
    try:
        rows = cur.execute(f"SELECT * FROM {table}").fetchall()
    except Exception as e:
        print(f"Skipping {table}: {e}")
        continue

    col = db[table]
    count = 0
    for r in rows:
        d = dict(r)
        filter_query = {}
        if table == "guild":
            filter_query = {"guildID": d["guildID"]}
        elif table == "voiceHubs":
            filter_query = {"joinChannelID": d["joinChannelID"]}
        elif table == "voiceChannel":
            filter_query = {"voiceID": d["voiceID"]}
        elif table == "voiceTime":
            filter_query = {"guildID": d["guildID"], "userID": d["userID"]}
        elif table == "userSettings":
            filter_query = {"userID": d["userID"]}
        elif table == "guildSettings":
            filter_query = {"guildID": d["guildID"]}
        elif table == "userPresets":
            filter_query = {"userID": d["userID"], "presetName": d["presetName"]}
        elif table == "premiumGuilds":
            filter_query = {"guildID": d["guildID"]}
        elif table == "premiumUsers":
            filter_query = {"userID": d["userID"]}
        elif table == "serverBotProfile":
            filter_query = {"guildID": d["guildID"]}
        elif table in ("purgeWhitelist", "deleteWhitelist"):
            filter_query = {"guildID": d["guildID"], "targetType": d["targetType"], "targetID": d["targetID"]}
        elif table == "guildPolicy":
            filter_query = {"guildID": d["guildID"]}

        col.update_one(filter_query, {"$set": d}, upsert=True)
        count += 1
    print(f"Table '{table}': migrated {count} documents.")
    total_migrated += count

con.close()

# Create indexes
db.guild.create_index("guildID", unique=True)
db.voiceHubs.create_index("joinChannelID", unique=True)
db.voiceHubs.create_index("guildID")
db.voiceChannel.create_index("voiceID", unique=True)
db.voiceChannel.create_index("userID")
db.voiceTime.create_index([("guildID", 1), ("totalSeconds", -1)])
db.voiceTime.create_index([("guildID", 1), ("userID", 1)], unique=True)

print(f"TOTAL MIGRATED: {total_migrated} documents successfully pushed to MongoDB!")
print("COLLECTIONS:", db.list_collection_names())
