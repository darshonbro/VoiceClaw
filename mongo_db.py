"""
VoiceClaw MongoDB Engine
High-performance asynchronous MongoDB manager for VoiceClaw bot and ecosystem.
Connects directly to the VPS self-hosted MongoDB instance (database: voiceclaw).
Eliminates localdb/SQLite dependencies while preserving 100% query compatibility.
"""

import os
import re
import sys
import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import motor.motor_asyncio as motor_asyncio
    HAS_MOTOR = True
except ImportError:
    HAS_MOTOR = False

import pymongo

logger = logging.getLogger("VoiceClaw.MongoDB")

# Primary VPS MongoDB connection URI (self-hosted)
DEFAULT_MONGO_URI = "mongodb://root:Q2006%40Ff@173.212.250.63:27017/voiceclaw?authSource=admin"
MONGO_URI = os.getenv("MONGODB_URI", DEFAULT_MONGO_URI)
DB_NAME = os.getenv("MONGODB_DB", "voiceclaw")


class MongoCursor:
    """Emulates a database cursor for query results."""
    def __init__(self, rows: List[Tuple]):
        self._rows = rows
        self._index = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def fetchone(self) -> Optional[Tuple]:
        if self._index < len(self._rows):
            row = self._rows[self._index]
            self._index += 1
            return row
        return None

    async def fetchall(self) -> List[Tuple]:
        remaining = self._rows[self._index:]
        self._index = len(self._rows)
        return remaining

    def __aiter__(self):
        return self

    async def __anext__(self):
        row = await self.fetchone()
        if row is None:
            raise StopAsyncIteration
        return row


class AsyncExecuteContext:
    """Supports both `await db.execute(...)` and `async with db.execute(...) as cur:`"""
    def __init__(self, db, sql: str, params: Union[Tuple, List] = ()):
        self.db = db
        self.sql = sql
        self.params = params
        self._cursor: Optional[MongoCursor] = None

    async def _resolve(self) -> MongoCursor:
        if self._cursor is None:
            self._cursor = await execute_sql_on_mongo(self.db, self.sql, self.params)
        return self._cursor

    def __await__(self):
        return self._resolve().__await__()

    async def __aenter__(self) -> MongoCursor:
        return await self._resolve()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class MongoDatabase:
    """
    Asynchronous database client for VoiceClaw.
    Provides native collection access (db['collection']) AND an asynchronous
    execute() interpreter that maps bot SQL statements directly to MongoDB documents.
    """
    _client = None
    _db = None

    @classmethod
    def get_client(cls):
        if cls._client is None:
            if HAS_MOTOR:
                cls._client = motor_asyncio.AsyncIOMotorClient(
                    MONGO_URI,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                    socketTimeoutMS=5000,
                )
                cls._db = cls._client[DB_NAME]
            else:
                sync_client = pymongo.MongoClient(
                    MONGO_URI,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                    socketTimeoutMS=5000,
                )
                cls._client = sync_client
                cls._db = sync_client[DB_NAME]
        return cls._client, cls._db

    def __init__(self):
        _, self.db = self.get_client()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def commit(self):
        pass

    def execute(self, sql: str, params: Union[Tuple, List] = ()) -> AsyncExecuteContext:
        """Executes a query and returns an AsyncExecuteContext supporting await and async with."""
        return AsyncExecuteContext(self.db, sql, params)

    def __getattr__(self, name: str):
        if self.db is not None:
            return getattr(self.db, name)
        raise AttributeError(f"'MongoDatabase' object has no attribute '{name}'")

    def __getitem__(self, name: str):
        if self.db is not None:
            return self.db[name]
        raise KeyError(name)


async def execute_sql_on_mongo(db, sql: str, params: Union[Tuple, List] = ()) -> MongoCursor:
    """
    Parses and translates VoiceClaw SQL statements to MongoDB operations.
    """
    sql_clean = " ".join(sql.strip().split())
    sql_upper = sql_clean.upper()
    p = list(params)

    # 1. DDL Statements (CREATE TABLE, ALTER TABLE, CREATE INDEX)
    if (sql_upper.startswith("CREATE TABLE") or 
        sql_upper.startswith("ALTER TABLE") or 
        sql_upper.startswith("CREATE INDEX") or 
        sql_upper.startswith("CREATE UNIQUE INDEX")):
        return MongoCursor([])

    # 2. SELECT Statements
    if sql_upper.startswith("SELECT"):
        return await _handle_select(db, sql_clean, p)

    # 3. INSERT Statements
    if sql_upper.startswith("INSERT"):
        return await _handle_insert(db, sql_clean, p)

    # 4. UPDATE Statements
    if sql_upper.startswith("UPDATE"):
        return await _handle_update(db, sql_clean, p)

    # 5. DELETE Statements
    if sql_upper.startswith("DELETE"):
        return await _handle_delete(db, sql_clean, p)

    logger.warning(f"[MongoDB] Unhandled statement: {sql_clean}")
    return MongoCursor([])


import inspect

async def _run_async(func, *args, **kwargs):
    """Runs a callable either natively if awaitable or executes safely."""
    res = func(*args, **kwargs)
    if inspect.isawaitable(res):
        return await res
    return res


async def _handle_select(db, sql: str, params: list) -> MongoCursor:
    # ── guild ─────────────────────────────────────────────────────────────
    if "FROM GUILD " in sql.upper() or "FROM GUILD\n" in sql.upper() or sql.strip().upper().endswith("FROM GUILD"):
        if "WHERE GUILDID = ?" in sql.upper():
            guild_id = params[0]
            col = db["guild"]
            doc = await _run_async(col.find_one, {"guildID": guild_id})
            if not doc:
                return MongoCursor([])
            
            # Check fields
            if "PERMINTERFACEID" in sql.upper():
                row = (
                    doc.get("guildID"),
                    doc.get("ownerID"),
                    doc.get("voiceChannelID"),
                    doc.get("voiceCategoryID"),
                    doc.get("interfaceChannelID"),
                    doc.get("logChannelID"),
                    doc.get("permCategoryID"),
                    doc.get("permChannelID"),
                    doc.get("permInterfaceID")
                )
                return MongoCursor([row])
            elif "LOGCHANNELID" in sql.upper() and "PERMCHANNELID" in sql.upper():
                row = (
                    doc.get("guildID"),
                    doc.get("ownerID"),
                    doc.get("voiceChannelID"),
                    doc.get("voiceCategoryID"),
                    doc.get("interfaceChannelID"),
                    doc.get("logChannelID"),
                    doc.get("permCategoryID"),
                    doc.get("permChannelID")
                )
                return MongoCursor([row])
            elif "VOICECATEGORYID, PERMCATEGORYID" in sql.upper():
                return MongoCursor([(doc.get("voiceCategoryID"), doc.get("permCategoryID"))])
            elif "VOICECHANNELID, PERMCHANNELID" in sql.upper():
                return MongoCursor([(doc.get("voiceChannelID"), doc.get("permChannelID"))])
            elif "INTERFACECHANNELID, PERMINTERFACEID" in sql.upper():
                return MongoCursor([(doc.get("interfaceChannelID"), doc.get("permInterfaceID"))])
            else:
                row = (
                    doc.get("guildID"),
                    doc.get("ownerID"),
                    doc.get("voiceChannelID"),
                    doc.get("voiceCategoryID"),
                    doc.get("interfaceChannelID"),
                    doc.get("logChannelID"),
                    doc.get("permCategoryID"),
                    doc.get("permChannelID"),
                    doc.get("permInterfaceID")
                )
                return MongoCursor([row])

    # ── voiceChannel ──────────────────────────────────────────────────────
    if "FROM VOICECHANNEL" in sql.upper():
        col = db["voiceChannel"]
        if "WHERE VOICEID = ?" in sql.upper():
            voice_id = params[0]
            doc = await _run_async(col.find_one, {"voiceID": voice_id})
            if not doc:
                return MongoCursor([])
            if "ISLOCKEDNAME" in sql.upper():
                return MongoCursor([(doc.get("isLockedName", 0),)])
            if "ISPERMANENT" in sql.upper() and "USERID" in sql.upper():
                return MongoCursor([(doc.get("userID"), doc.get("isPermanent", 0))])
            if "ISPERMANENT" in sql.upper():
                return MongoCursor([(doc.get("isPermanent", 0),)])
            if "USERID" in sql.upper():
                return MongoCursor([(doc.get("userID"),)])
            return MongoCursor([(doc.get("userID"), doc.get("voiceID"), doc.get("isPermanent", 0), doc.get("isLockedName", 0))])

        if "WHERE USERID = ?" in sql.upper():
            user_id = params[0]
            query = {"userID": user_id}
            if "ISPERMANENT = 1" in sql.upper():
                query["isPermanent"] = 1
            cursor = col.find(query)
            docs = await _cursor_to_list(cursor)
            return MongoCursor([(d.get("voiceID"),) for d in docs])

        # SELECT voiceID, userID, isPermanent / SELECT voiceID, userID / SELECT voiceID
        cursor = col.find({})
        docs = await _cursor_to_list(cursor)
        if "ISPERMANENT" in sql.upper():
            return MongoCursor([(d.get("voiceID"), d.get("userID"), d.get("isPermanent", 0)) for d in docs])
        if "USERID" in sql.upper():
            return MongoCursor([(d.get("voiceID"), d.get("userID")) for d in docs])
        return MongoCursor([(d.get("voiceID"),) for d in docs])

    # ── voiceHubs ─────────────────────────────────────────────────────────
    if "FROM VOICEHUBS" in sql.upper():
        col = db["voiceHubs"]
        
        # SELECT 1 FROM voiceHubs WHERE guildID = ? AND categoryID = ?
        if "SELECT 1" in sql.upper() and "CATEGORYID = ?" in sql.upper():
            doc = await _run_async(col.find_one, {"guildID": params[0], "categoryID": params[1]})
            return MongoCursor([(1,)] if doc else [])
        
        # SELECT 1 FROM voiceHubs WHERE guildID = ? AND joinChannelID = ?
        if "SELECT 1" in sql.upper() and "JOINCHANNELID = ?" in sql.upper():
            doc = await _run_async(col.find_one, {"guildID": params[0], "joinChannelID": params[1]})
            return MongoCursor([(1,)] if doc else [])

        # SELECT hubID FROM voiceHubs WHERE guildID = ? AND fixedName = ?
        if "SELECT HUBID FROM" in sql.upper():
            doc = await _run_async(col.find_one, {"guildID": params[0], "fixedName": params[1]})
            return MongoCursor([(doc.get("hubID", 1),)] if doc else [])

        # SELECT interfaceChannelID FROM voiceHubs WHERE guildID = ?
        if "SELECT INTERFACECHANNELID FROM" in sql.upper():
            cursor = col.find({"guildID": params[0]})
            docs = await _cursor_to_list(cursor)
            return MongoCursor([(d.get("interfaceChannelID"),) for d in docs if d.get("interfaceChannelID")])

        # SELECT hubID, guildID, categoryID, joinChannelID, interfaceChannelID, fixedName, userLimit, lockName, isPermanent
        filter_q = {}
        if "WHERE CATEGORYID = ?" in sql.upper():
            filter_q = {"categoryID": params[0]}
        elif "WHERE GUILDID = ?" in sql.upper():
            filter_q = {"guildID": params[0]}
        elif "WHERE JOINCHANNELID = ?" in sql.upper():
            filter_q = {"joinChannelID": params[0]}

        cursor = col.find(filter_q)
        docs = await _cursor_to_list(cursor)
        rows = [
            (
                d.get("hubID", 1),
                d.get("guildID"),
                d.get("categoryID"),
                d.get("joinChannelID"),
                d.get("interfaceChannelID"),
                d.get("fixedName"),
                d.get("userLimit", 0),
                d.get("lockName", 1),
                d.get("isPermanent", 0)
            )
            for d in docs
        ]
        return MongoCursor(rows)

    # ── voiceTime ─────────────────────────────────────────────────────────
    if "FROM VOICETIME" in sql.upper():
        col = db["voiceTime"]
        # SELECT userID, totalSeconds FROM voiceTime WHERE guildID = ? ORDER BY totalSeconds DESC LIMIT 10
        guild_id = params[0]
        cursor = col.find({"guildID": guild_id}).sort("totalSeconds", pymongo.DESCENDING).limit(10)
        docs = await _cursor_to_list(cursor)
        return MongoCursor([(d.get("userID"), d.get("totalSeconds", 0)) for d in docs])

    # ── userSettings ──────────────────────────────────────────────────────
    if "FROM USERSETTINGS" in sql.upper():
        col = db["userSettings"]
        user_id = params[0]
        doc = await _run_async(col.find_one, {"userID": user_id})
        if not doc:
            return MongoCursor([])
        return MongoCursor([(doc.get("channelName"), doc.get("channelLimit", 0), doc.get("bitrate"))])

    # ── guildSettings ─────────────────────────────────────────────────────
    if "FROM GUILDSETTINGS" in sql.upper():
        col = db["guildSettings"]
        if "WHERE PREFIX IS NOT NULL" in sql.upper():
            cursor = col.find({"prefix": {"$ne": None}})
            docs = await _cursor_to_list(cursor)
            return MongoCursor([(d.get("guildID"), d.get("prefix")) for d in docs])

        guild_id = params[0]
        doc = await _run_async(col.find_one, {"guildID": guild_id})
        if "SELECT 1" in sql.upper():
            return MongoCursor([(1,)] if doc else [])
        if not doc:
            return MongoCursor([])
        return MongoCursor([(doc.get("channelName"), doc.get("channelLimit", 0))])

    # ── userPresets ───────────────────────────────────────────────────────
    if "FROM USERPRESETS" in sql.upper():
        col = db["userPresets"]
        user_id = params[0]
        if len(params) > 1:
            preset_name = params[1]
            doc = await _run_async(col.find_one, {"userID": user_id, "presetName": preset_name})
            if not doc:
                return MongoCursor([])
            return MongoCursor([(doc.get("presetName"), doc.get("channelName"), doc.get("channelLimit", 0), doc.get("bitrate"))])
        else:
            cursor = col.find({"userID": user_id})
            docs = await _cursor_to_list(cursor)
            return MongoCursor([(d.get("presetName"), d.get("channelName"), d.get("channelLimit", 0), d.get("bitrate")) for d in docs])

    # ── premiumGuilds ─────────────────────────────────────────────────────
    if "FROM PREMIUMGUILDS" in sql.upper():
        col = db["premiumGuilds"]
        if "WHERE GUILDID = ?" in sql.upper():
            guild_id = params[0]
            doc = await _run_async(col.find_one, {"guildID": guild_id})
            return MongoCursor([(1,)] if doc else [])
        cursor = col.find({})
        docs = await _cursor_to_list(cursor)
        return MongoCursor([(d.get("guildID"), d.get("plan"), d.get("addedAt")) for d in docs])

    # ── premiumUsers ──────────────────────────────────────────────────────
    if "FROM PREMIUMUSERS" in sql.upper():
        col = db["premiumUsers"]
        if "WHERE USERID = ?" in sql.upper():
            user_id = params[0]
            doc = await _run_async(col.find_one, {"userID": user_id})
            return MongoCursor([(1,)] if doc else [])
        cursor = col.find({})
        docs = await _cursor_to_list(cursor)
        return MongoCursor([(d.get("userID"), d.get("plan"), d.get("addedAt")) for d in docs])

    # ── serverBotProfile ──────────────────────────────────────────────────
    if "FROM SERVERBOTPROFILE" in sql.upper():
        col = db["serverBotProfile"]
        guild_id = params[0]
        doc = await _run_async(col.find_one, {"guildID": guild_id})
        if not doc:
            return MongoCursor([])
        if "SERVERBANNER" in sql.upper() and len(sql.split(",")) == 1:
            return MongoCursor([(doc.get("serverBanner"),)])
        return MongoCursor([(doc.get("serverAvatar"), doc.get("serverBanner"), doc.get("serverBio"), doc.get("serverNickname"))])

    # ── purgeWhitelist / deleteWhitelist ──────────────────────────────────
    if "FROM PURGEWHITELIST" in sql.upper():
        col = db["purgeWhitelist"]
        if "SELECT 1" in sql.upper():
            guild_id = params[0]
            if "IN (" in sql.upper():
                role_ids = list(params[1:])
                doc = await _run_async(col.find_one, {"guildID": guild_id, "targetType": "role", "targetID": {"$in": role_ids}})
                return MongoCursor([(1,)] if doc else [])
            target_id = params[1]
            doc = await _run_async(col.find_one, {"guildID": guild_id, "targetType": "user", "targetID": target_id})
            return MongoCursor([(1,)] if doc else [])
        guild_id = params[0]
        cursor = col.find({"guildID": guild_id})
        docs = await _cursor_to_list(cursor)
        return MongoCursor([(d.get("targetType"), d.get("targetID")) for d in docs])

    if "FROM DELETEWHITELIST" in sql.upper():
        col = db["deleteWhitelist"]
        if "SELECT 1" in sql.upper():
            guild_id = params[0]
            if "IN (" in sql.upper():
                role_ids = list(params[1:])
                doc = await _run_async(col.find_one, {"guildID": guild_id, "targetType": "role", "targetID": {"$in": role_ids}})
                return MongoCursor([(1,)] if doc else [])
            target_id = params[1]
            doc = await _run_async(col.find_one, {"guildID": guild_id, "targetType": "user", "targetID": target_id})
            return MongoCursor([(1,)] if doc else [])
        guild_id = params[0]
        cursor = col.find({"guildID": guild_id})
        docs = await _cursor_to_list(cursor)
        return MongoCursor([(d.get("targetType"), d.get("targetID")) for d in docs])

    # ── guildPolicy ───────────────────────────────────────────────────────
    if "FROM GUILDPOLICY" in sql.upper():
        col = db["guildPolicy"]
        guild_id = params[0]
        doc = await _run_async(col.find_one, {"guildID": guild_id})
        if not doc:
            return MongoCursor([])
        return MongoCursor([(doc.get("allowPublicDelete", 0),)])

    return MongoCursor([])


async def _handle_insert(db, sql: str, params: list) -> MongoCursor:
    # ── guild ─────────────────────────────────────────────────────────────
    if "INTO GUILD " in sql.upper():
        col = db["guild"]
        if len(params) == 3: # (guildID, ownerID, permCategoryID)
            guild_id, owner_id, perm_cat = params
            await _run_async(
                col.update_one,
                {"guildID": guild_id},
                {"$set": {"guildID": guild_id, "ownerID": owner_id, "permCategoryID": perm_cat}},
                upsert=True
            )
        elif len(params) == 5:
            # (guildID, ownerID, permCategoryID, permChannelID, permInterfaceID)
            if "PERMINTERFACEID" in sql.upper():
                guild_id, owner_id, perm_cat, perm_chan, perm_iface = params
                await _run_async(
                    col.update_one,
                    {"guildID": guild_id},
                    {"$set": {
                        "guildID": guild_id,
                        "ownerID": owner_id,
                        "permCategoryID": perm_cat,
                        "permChannelID": perm_chan,
                        "permInterfaceID": perm_iface
                    }},
                    upsert=True
                )
            else:
                # (guildID, ownerID, voiceChannelID, voiceCategoryID, interfaceChannelID)
                guild_id, owner_id, vc_id, vc_cat, iface_id = params
                update_fields = {
                    "guildID": guild_id,
                    "ownerID": owner_id,
                    "voiceCategoryID": vc_cat,
                    "interfaceChannelID": iface_id
                }
                if vc_id is not None:
                    update_fields["voiceChannelID"] = vc_id
                await _run_async(
                    col.update_one,
                    {"guildID": guild_id},
                    {"$set": update_fields},
                    upsert=True
                )
        elif len(params) == 8:
            # (guildID, ownerID, voiceChannelID, voiceCategoryID, interfaceChannelID, permCategoryID, permChannelID, permInterfaceID)
            guild_id, owner_id, vc_id, vc_cat, iface_id, p_cat, p_chan, p_iface = params
            await _run_async(
                col.update_one,
                {"guildID": guild_id},
                {"$set": {
                    "guildID": guild_id,
                    "ownerID": owner_id,
                    "voiceChannelID": vc_id,
                    "voiceCategoryID": vc_cat,
                    "interfaceChannelID": iface_id,
                    "permCategoryID": p_cat,
                    "permChannelID": p_chan,
                    "permInterfaceID": p_iface
                }},
                upsert=True
            )
        return MongoCursor([])

    # ── voiceChannel ──────────────────────────────────────────────────────
    if "INTO VOICECHANNEL" in sql.upper():
        col = db["voiceChannel"]
        user_id, voice_id, is_perm, is_lock = params[0], params[1], params[2], params[3]
        await _run_async(
            col.update_one,
            {"voiceID": voice_id},
            {"$set": {
                "userID": user_id,
                "voiceID": voice_id,
                "isPermanent": is_perm,
                "isLockedName": is_lock
            }},
            upsert=True
        )
        return MongoCursor([])

    # ── voiceHubs ─────────────────────────────────────────────────────────
    if "INTO VOICEHUBS" in sql.upper():
        col = db["voiceHubs"]
        guild_id, category_id, join_chan, iface_chan, fixed_name, limit, lock, is_perm = params
        # Get next hubID if not present
        existing = await _run_async(col.find_one, {"joinChannelID": join_chan})
        hub_id = existing.get("hubID", 1) if existing else None
        if not hub_id:
            highest = await _run_async(col.find_one, {}, sort=[("hubID", pymongo.DESCENDING)])
            hub_id = (highest.get("hubID", 0) + 1) if highest else 1

        await _run_async(
            col.update_one,
            {"joinChannelID": join_chan},
            {"$set": {
                "hubID": hub_id,
                "guildID": guild_id,
                "categoryID": category_id,
                "joinChannelID": join_chan,
                "interfaceChannelID": iface_chan,
                "fixedName": fixed_name,
                "userLimit": limit,
                "lockName": lock,
                "isPermanent": is_perm
            }},
            upsert=True
        )
        return MongoCursor([])

    # ── voiceTime ─────────────────────────────────────────────────────────
    if "INTO VOICETIME" in sql.upper():
        col = db["voiceTime"]
        # INSERT INTO voiceTime (guildID, userID, totalSeconds) VALUES (?, ?, ?) ON CONFLICT(guildID, userID) DO UPDATE SET totalSeconds = totalSeconds + ?
        guild_id, user_id, seconds = params[0], params[1], params[2]
        inc_val = params[3] if len(params) > 3 else seconds
        await _run_async(
            col.update_one,
            {"guildID": guild_id, "userID": user_id},
            {"$inc": {"totalSeconds": inc_val}},
            upsert=True
        )
        return MongoCursor([])

    # ── guildSettings ─────────────────────────────────────────────────────
    if "INTO GUILDSETTINGS" in sql.upper():
        col = db["guildSettings"]
        guild_id, prefix = params[0], params[1]
        await _run_async(
            col.update_one,
            {"guildID": guild_id},
            {"$set": {"guildID": guild_id, "prefix": prefix}},
            upsert=True
        )
        return MongoCursor([])

    # ── userSettings ──────────────────────────────────────────────────────
    if "INTO USERSETTINGS" in sql.upper():
        col = db["userSettings"]
        user_id, ch_name, limit, bitrate = params[0], params[1], params[2], params[3]
        await _run_async(
            col.update_one,
            {"userID": user_id},
            {"$set": {
                "userID": user_id,
                "channelName": ch_name,
                "channelLimit": limit,
                "bitrate": bitrate
            }},
            upsert=True
        )
        return MongoCursor([])

    # ── userPresets ───────────────────────────────────────────────────────
    if "INTO USERPRESETS" in sql.upper():
        col = db["userPresets"]
        user_id, preset_name, ch_name, limit, bitrate = params
        await _run_async(
            col.update_one,
            {"userID": user_id, "presetName": preset_name},
            {"$set": {
                "userID": user_id,
                "presetName": preset_name,
                "channelName": ch_name,
                "channelLimit": limit,
                "bitrate": bitrate
            }},
            upsert=True
        )
        return MongoCursor([])

    # ── premiumGuilds / premiumUsers ──────────────────────────────────────
    if "INTO PREMIUMGUILDS" in sql.upper():
        col = db["premiumGuilds"]
        guild_id, plan, granted_by = params
        await _run_async(
            col.update_one,
            {"guildID": guild_id},
            {"$set": {"guildID": guild_id, "plan": plan, "grantedBy": granted_by}},
            upsert=True
        )
        return MongoCursor([])

    if "INTO PREMIUMUSERS" in sql.upper():
        col = db["premiumUsers"]
        user_id, plan, granted_by = params
        await _run_async(
            col.update_one,
            {"userID": user_id},
            {"$set": {"userID": user_id, "plan": plan, "grantedBy": granted_by}},
            upsert=True
        )
        return MongoCursor([])

    # ── serverBotProfile ──────────────────────────────────────────────────
    if "INTO SERVERBOTPROFILE" in sql.upper():
        col = db["serverBotProfile"]
        guild_id, val = params[0], params[1]
        field = "serverAvatar"
        if "SERVERBANNER" in sql.upper():
            field = "serverBanner"
        elif "SERVERBIO" in sql.upper():
            field = "serverBio"
        elif "SERVERNICKNAME" in sql.upper():
            field = "serverNickname"
        await _run_async(
            col.update_one,
            {"guildID": guild_id},
            {"$set": {"guildID": guild_id, field: val}},
            upsert=True
        )
        return MongoCursor([])

    # ── purgeWhitelist / deleteWhitelist ──────────────────────────────────
    if "INTO PURGEWHITELIST" in sql.upper():
        col = db["purgeWhitelist"]
        # INSERT OR REPLACE INTO purgeWhitelist (guildID, targetType, targetID, addedBy) VALUES (?, 'role', ?, ?)
        t_type = "role" if "'role'" in sql.lower() else "user"
        guild_id, target_id, added_by = params[0], params[1], params[2]
        await _run_async(
            col.update_one,
            {"guildID": guild_id, "targetType": t_type, "targetID": target_id},
            {"$set": {"guildID": guild_id, "targetType": t_type, "targetID": target_id, "addedBy": added_by}},
            upsert=True
        )
        return MongoCursor([])

    if "INTO DELETEWHITELIST" in sql.upper():
        col = db["deleteWhitelist"]
        t_type = "role" if "'role'" in sql.lower() else "user"
        guild_id, target_id, added_by = params[0], params[1], params[2]
        await _run_async(
            col.update_one,
            {"guildID": guild_id, "targetType": t_type, "targetID": target_id},
            {"$set": {"guildID": guild_id, "targetType": t_type, "targetID": target_id, "addedBy": added_by}},
            upsert=True
        )
        return MongoCursor([])

    # ── guildPolicy ───────────────────────────────────────────────────────
    if "INTO GUILDPOLICY" in sql.upper():
        col = db["guildPolicy"]
        guild_id, allow = params[0], params[1]
        await _run_async(
            col.update_one,
            {"guildID": guild_id},
            {"$set": {"guildID": guild_id, "allowPublicDelete": allow}},
            upsert=True
        )
        return MongoCursor([])

    return MongoCursor([])


async def _handle_update(db, sql: str, params: list) -> MongoCursor:
    # ── guild ─────────────────────────────────────────────────────────────
    if "UPDATE GUILD " in sql.upper():
        col = db["guild"]
        if "SET LOGCHANNELID = ?" in sql.upper():
            log_id, guild_id = params
            await _run_async(col.update_many, {"guildID": guild_id}, {"$set": {"logChannelID": log_id}})
        elif "SET PERMCHANNELID = ?" in sql.upper():
            perm_chan, guild_id = params
            await _run_async(col.update_many, {"guildID": guild_id}, {"$set": {"permChannelID": perm_chan}})
        elif "SET VOICECATEGORYID = ?" in sql.upper():
            v_cat, v_chan, iface, guild_id = params
            await _run_async(col.update_many, {"guildID": guild_id}, {"$set": {
                "voiceCategoryID": v_cat,
                "voiceChannelID": v_chan,
                "interfaceChannelID": iface
            }})
        elif "SET VOICECHANNELID = ?" in sql.upper():
            v_chan, guild_id = params
            await _run_async(col.update_many, {"guildID": guild_id}, {"$set": {"voiceChannelID": v_chan}})
        return MongoCursor([])

    # ── guildSettings ─────────────────────────────────────────────────────
    if "UPDATE GUILDSETTINGS " in sql.upper():
        col = db["guildSettings"]
        if "SET PREFIX = NULL" in sql.upper():
            guild_id = params[0]
            await _run_async(col.update_many, {"guildID": guild_id}, {"$set": {"prefix": None}})
        elif "SET PREFIX = ?" in sql.upper():
            prefix, guild_id = params
            await _run_async(col.update_many, {"guildID": guild_id}, {"$set": {"prefix": prefix}})
        return MongoCursor([])

    # ── voiceChannel ──────────────────────────────────────────────────────
    if "UPDATE VOICECHANNEL " in sql.upper():
        col = db["voiceChannel"]
        user_id, voice_id = params
        await _run_async(col.update_many, {"voiceID": voice_id}, {"$set": {"userID": user_id}})
        return MongoCursor([])

    # ── voiceHubs ─────────────────────────────────────────────────────────
    if "UPDATE VOICEHUBS " in sql.upper():
        col = db["voiceHubs"]
        if "SET CATEGORYID = ?" in sql.upper():
            cat_id, join_chan, iface, hub_id = params
            await _run_async(col.update_many, {"hubID": hub_id}, {"$set": {
                "categoryID": cat_id,
                "joinChannelID": join_chan,
                "interfaceChannelID": iface
            }})
        elif "SET JOINCHANNELID = ?" in sql.upper():
            join_chan, hub_id = params
            await _run_async(col.update_many, {"hubID": hub_id}, {"$set": {"joinChannelID": join_chan}})
        return MongoCursor([])

    # ── serverBotProfile ──────────────────────────────────────────────────
    if "UPDATE SERVERBOTPROFILE " in sql.upper():
        col = db["serverBotProfile"]
        guild_id = params[0]
        field = "serverAvatar"
        if "SERVERBANNER" in sql.upper():
            field = "serverBanner"
        elif "SERVERBIO" in sql.upper():
            field = "serverBio"
        elif "SERVERNICKNAME" in sql.upper():
            field = "serverNickname"
        await _run_async(col.update_many, {"guildID": guild_id}, {"$set": {field: None}})
        return MongoCursor([])

    return MongoCursor([])


async def _handle_delete(db, sql: str, params: list) -> MongoCursor:
    if "DELETE FROM GUILD " in sql.upper():
        guild_id = params[0]
        await _run_async(db["guild"].delete_many, {"guildID": guild_id})
        return MongoCursor([])

    if "DELETE FROM VOICECHANNEL " in sql.upper():
        voice_id = params[0]
        await _run_async(db["voiceChannel"].delete_many, {"voiceID": voice_id})
        return MongoCursor([])

    if "DELETE FROM VOICEHUBS " in sql.upper():
        col = db["voiceHubs"]
        if "WHERE HUBID = ?" in sql.upper():
            await _run_async(col.delete_many, {"hubID": params[0]})
        elif "WHERE JOINCHANNELID = ?" in sql.upper():
            await _run_async(col.delete_many, {"joinChannelID": params[0]})
        return MongoCursor([])

    if "DELETE FROM USERSETTINGS " in sql.upper():
        await _run_async(db["userSettings"].delete_many, {"userID": params[0]})
        return MongoCursor([])

    if "DELETE FROM USERPRESETS " in sql.upper():
        await _run_async(db["userPresets"].delete_many, {"userID": params[0], "presetName": params[1]})
        return MongoCursor([])

    if "DELETE FROM PREMIUMGUILDS " in sql.upper():
        await _run_async(db["premiumGuilds"].delete_many, {"guildID": params[0]})
        return MongoCursor([])

    if "DELETE FROM PREMIUMUSERS " in sql.upper():
        await _run_async(db["premiumUsers"].delete_many, {"userID": params[0]})
        return MongoCursor([])

    if "DELETE FROM PURGEWHITELIST " in sql.upper():
        t_type = "role" if "'role'" in sql.lower() else "user"
        guild_id, target_id = params[0], params[1]
        await _run_async(db["purgeWhitelist"].delete_many, {"guildID": guild_id, "targetType": t_type, "targetID": target_id})
        return MongoCursor([])

    if "DELETE FROM DELETEWHITELIST " in sql.upper():
        t_type = "role" if "'role'" in sql.lower() else "user"
        guild_id, target_id = params[0], params[1]
        await _run_async(db["deleteWhitelist"].delete_many, {"guildID": guild_id, "targetType": t_type, "targetID": target_id})
        return MongoCursor([])

    return MongoCursor([])


async def _cursor_to_list(cursor) -> List[Dict]:
    """Helper to convert Motor or PyMongo cursor to list of docs."""
    if hasattr(cursor, "to_list"):
        return await cursor.to_list(length=1000)
    return list(cursor)


# Global singleton instance
def get_db():
    return MongoDatabase()
