# Group Chat Feature — Implementation Spec

## Overview

Add WhatsApp-style group chats to the Dolphin Buddy platform. Any user can create a group, add other users (and optionally the AI bot) as members. All members see the same chat thread. The AI bot participates exactly like it does in 1:1 chats — same tools, same booking/policy logic — but in a shared, multi-user context.

This spec covers Phase 1: groups, members, group messaging, AI in groups, @mentions. Transfer chat is Phase 2 (separate spec).

---

## Current Architecture (what exists)

- **Users**: identified by `userId` (their name/agent ID stored in localStorage). No auth, no user table — users are implicit from session ownership.
- **Sessions**: each 1:1 chat is an ADK session (`session_XXXXX`), keyed by `userId + sessionId`. Stored in `sessions.db`.
- **Messages**: stored inside ADK session events. No separate messages table.
- **Conversation list**: frontend reads ADK sessions via `GET /apps/my_agent/users/{userId}/sessions`, sorted by `lastUpdateTime`.
- **AI**: single `root_agent` in `my_agent/agent.py`, invoked via `POST /run_sse` with `{ userId, sessionId, newMessage }`.
- **DB**: `bookings.db` (SQLite) holds bookings, wallets, campaigns, token_usage. `sessions.db` holds ADK sessions.

---

## What We're Building

### Data Model

Three new SQLite tables in `bookings.db`:

```sql
-- Groups
CREATE TABLE groups (
    id          TEXT PRIMARY KEY,           -- grp_XXXXX
    name        TEXT NOT NULL,
    created_by  TEXT NOT NULL,              -- userId of creator
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL               -- updated on every new message (for sorting)
);

-- Group members (users + bot)
CREATE TABLE group_members (
    group_id    TEXT NOT NULL,
    user_id     TEXT NOT NULL,              -- userId string, or "bot" for the AI
    is_bot      INTEGER NOT NULL DEFAULT 0, -- 1 = AI bot member
    added_at    TEXT NOT NULL,
    added_by    TEXT NOT NULL,
    PRIMARY KEY (group_id, user_id),
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
);

-- Group messages
CREATE TABLE group_messages (
    id          TEXT PRIMARY KEY,           -- msg_XXXXX
    group_id    TEXT NOT NULL,
    sender_id   TEXT NOT NULL,              -- userId or "bot"
    content     TEXT NOT NULL,              -- message text (may contain card markers)
    msg_type    TEXT NOT NULL DEFAULT 'text', -- 'text' | 'bot_response' | 'artifact'
    artifacts   TEXT,                       -- JSON array of filenames (PDFs etc.)
    mentions    TEXT,                       -- JSON array of mentioned userIds
    created_at  TEXT NOT NULL,
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
);

-- Per-user unread count per group
CREATE TABLE group_unread (
    group_id    TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    last_read   TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z',
    PRIMARY KEY (group_id, user_id)
);
```

**Group ID format**: `grp_` + 5 random alphanumeric chars (same pattern as `BUD-XXXXX`).
**Message ID format**: `msg_` + 8 random chars.

---

## Backend

### New file: `hip/data/groups.py`

Handles all DB operations:

```python
# Functions to implement:
init_groups_db()           # called on import — creates tables if not exist

create_group(name, created_by, members: list[str], include_bot: bool) -> dict
get_group(group_id) -> dict | None
list_groups_for_user(user_id) -> list[dict]  # groups where user is a member
delete_group(group_id) -> bool

add_member(group_id, user_id, added_by, is_bot=False) -> bool
remove_member(group_id, user_id) -> bool
get_members(group_id) -> list[dict]          # includes is_bot flag

post_message(group_id, sender_id, content, msg_type, artifacts=None, mentions=None) -> dict
get_messages(group_id, limit=50, before=None) -> list[dict]  # newest-first pagination

mark_read(group_id, user_id)                 # update last_read timestamp
get_unread_count(group_id, user_id) -> int
get_all_unread_for_user(user_id) -> dict     # {group_id: count}
update_group_timestamp(group_id)             # bump updated_at (called after each message)
```

### New file: `hip/data/group_ai_session.py`

The AI in a group needs a persistent ADK session scoped to the group (not to any individual user). This is how multi-turn context is maintained across different users' messages.

```python
# The group gets its own ADK session:
# app_name = "my_agent"
# user_id  = "group_{group_id}"   ← synthetic user for the group
# session_id = "gsession_{group_id}"

def get_or_create_group_session(group_id: str) -> tuple[str, str]:
    """Returns (user_id, session_id) for the group's AI session."""
    return f"group_{group_id}", f"gsession_{group_id}"
```

Why: ADK sessions are scoped to `(app_name, user_id, session_id)`. By using `group_{group_id}` as the user_id, the bot's conversation history for the group is isolated and persistent across all member messages.

### New endpoints in `hip/main.py`

```
POST   /groups                              — create group
GET    /groups?user_id=X                    — list groups for user
GET    /groups/{group_id}                   — get group + members
DELETE /groups/{group_id}                   — delete group (creator only)

POST   /groups/{group_id}/members           — add member(s)
DELETE /groups/{group_id}/members/{user_id} — remove member

GET    /groups/{group_id}/messages?limit=50&before=<msg_id>  — paginated history
POST   /groups/{group_id}/messages          — post a human message

POST   /groups/{group_id}/run_bot           — trigger bot response (SSE stream)
POST   /groups/{group_id}/read              — mark messages read for current user

GET    /users                               — list all known users (for member picker)
```

### `POST /groups/{group_id}/messages` — Human message flow

```
1. Validate sender is a member of the group
2. Insert message into group_messages
3. Update groups.updated_at
4. Reset group_unread for sender (mark as read)
5. Return { message_id, created_at }
```

### `POST /groups/{group_id}/run_bot` — Bot response flow

```
Request body: {
    "trigger_message_id": "msg_XXXXX",  — the message that triggered the bot
    "sender_id": "deepak",
    "content": "what plans do you have for dubai?"
}

Flow:
1. Verify bot is a member of the group
2. Get group context: group name, all members, recent messages (last 10)
3. Build enhanced message for ADK:
   - Prefix with: "[Group: {name}] {sender_id}: {content}"
   - Include group context in message if needed
4. Get/create the group's ADK session (group_{group_id}, gsession_{group_id})
5. Ensure that ADK session exists (create if not)
6. Stream /run_sse with group session credentials
7. As chunks arrive, accumulate full response
8. On completion, post bot response to group_messages as sender_id="bot"
9. Stream SSE chunks back to the caller in real-time
```

The bot prompt injection looks like:
```
[GROUP CONTEXT]
Group: "Dubai Trip Planning"
Members: deepak, prakhar, rahul (+ bot)
deepak asked: "what plans do you have for dubai?"
[END CONTEXT]
```

### `GET /users` endpoint

Returns all known user IDs from wallets + bookings tables (same query already in `campaigns.py`'s `get_all_users()`). Used by the frontend member picker when creating/editing a group.

```python
@app.get("/users")
def list_users_endpoint():
    return {"users": get_all_users()}
```

---

## AI Behaviour in Groups

The existing `root_agent` is used as-is. No new agent or prompt changes needed for Phase 1.

The group context is injected at the **message level** — the content sent to `/run_sse` includes a prefix:

```
[Group: Dubai Trip Planning | deepak asks]: what plans do you have for dubai 5 nights?
```

The agent responds as it normally would. Policy cards, booking cards, PDF artifacts — all work identically. The frontend renders the bot's response in the group thread just like a normal agent message bubble, but with "Dolphin Operations BOT" as the sender label instead of a user name.

**Important**: the bot uses a **group-scoped ADK session** (`group_{group_id}` / `gsession_{group_id}`). This means:
- The bot remembers the full conversation history across all members' messages
- If deepak asks for a quote and prakhar follows up, the bot has both in context
- Wallet operations: the bot uses the **sender's** userId for wallet deductions, not the group's synthetic userId. The `before_tool_callback` guardrail must be updated to allow this.

### Guardrail update needed

Current `_before_tool_guardrail` checks `tool_context.state.get("user_id")` against the tool arg `user_id`. In group sessions, state has `user_id = "group_{group_id}"` but the tool call will have the actual sender's userId. The fix: pass the real sender's userId as part of the message context, and update the guardrail to also check a `"sender_user_id"` key in state.

The `/run_bot` endpoint sets `sender_user_id` in the group's ADK session state before calling the agent.

---

## Frontend

### New file: `hip-frontend/lib/groupApi.ts`

All group-related API calls:

```typescript
createGroup(name, creatorId, memberIds, includeBot) -> Group
listGroups(userId) -> Group[]
getGroup(groupId) -> GroupWithMembers
deleteGroup(groupId) -> void
addMember(groupId, userId) -> void
removeMember(groupId, userId) -> void

getMessages(groupId, limit?, before?) -> GroupMessage[]
postMessage(groupId, senderId, content, mentions?) -> GroupMessage
runBot(groupId, senderId, content, triggerMessageId) -> AsyncGenerator<chunk>
markRead(groupId, userId) -> void

listUsers() -> string[]
```

### New file: `hip-frontend/components/GroupChatWindow.tsx`

A new view that replaces `ChatWindow`'s chat column (Col 3) when a group is active. Key differences from 1:1:

- **Sender labels** on every message bubble (left-aligned, coloured by user hash — same `getAvatarColor` logic from `ConversationList`)
- **Bot messages** labelled "Dolphin Operations BOT" with the existing shield avatar
- **@mention autocomplete** — typing `@` shows a dropdown of group members
- **Message input** posts to `/groups/{id}/messages` then triggers `/groups/{id}/run_bot` if bot is a member and the message isn't directed at a specific human
- **Bot typing indicator** shown while `/run_bot` SSE stream is in progress
- **Artifacts/PDFs** render the same as in 1:1 — using `buildDownloadUrl` with the group's synthetic userId

### Updates to `ConversationList.tsx`

Groups appear in the same conversation list, sorted by `updated_at` alongside ADK sessions. They are distinguished by a group icon (people icon) instead of initials avatar. The existing "Groups" filter pill (already in the UI but not wired) gets connected.

Group rows show:
- Group name as title
- Last message preview + sender name prefix (e.g. "deepak: sounds good")
- Unread badge from `get_all_unread_for_user`
- `lastUpdateTime` from `groups.updated_at`

### Updates to `ChatContext.tsx`

Add group state alongside session state:

```typescript
interface GroupMeta {
  id: string;
  name: string;
  lastUpdateTime: number;
  lastMessage?: string;
  unreadCount: number;
  members: string[];
  hasBot: boolean;
}

// New context values:
groups: GroupMeta[]
activeGroupId: string | null
setActiveGroupId: (id: string | null) => void
refreshGroups: () => Promise<void>
```

When `activeGroupId` is set, `ChatWindow` renders `GroupChatWindow` instead of the regular message feed.

### New component: `CreateGroupModal.tsx`

Triggered by a "New Group" button in the `ConversationList` header (next to the existing `+` button).

Fields:
- Group name (text input)
- Member picker — searchable list of all users from `GET /users`, checkboxes
- "Add Dolphin Bot" toggle (default: on)
- Create button

### Updates to `ChatWindow.tsx`

Add a conditional render:

```tsx
{activeGroupId ? (
  <GroupChatWindow groupId={activeGroupId} />
) : (
  /* existing 1:1 chat stream */
)}
```

---

## Message Rendering in Groups

Group messages use the existing `Message.tsx` component with one addition — a `senderLabel` prop:

```tsx
<Message
  msg={msg}
  userId={userId}
  sessionId={sessionId}  // group's synthetic session for artifact downloads
  senderLabel={msg.senderId !== userId ? msg.senderId : undefined}
  onSend={handleSend}
/>
```

`Message.tsx` renders `senderLabel` as a small coloured name above the bubble (like WhatsApp groups). Bot messages get `senderLabel="Dolphin Operations"` with the teal colour.

Card markers (`<!--POLICY_CARDS:...-->` etc.) in bot responses are parsed and rendered exactly as in 1:1. The `onChoose` callback posts the chosen prompt back to the group thread, triggering another bot response.

---

## Polling & Real-time

No websockets. Use the same polling pattern as campaigns:

- Frontend polls `GET /groups?user_id=X` every **5 seconds** to update unread counts and `lastUpdateTime`
- When a group is open, also poll `GET /groups/{id}/messages` every **3 seconds** for new messages
- Bot SSE stream is real-time during active response; polling picks up anything missed

---

## File Structure (new files)

```
hip/
  data/
    groups.py              ← new: all group DB operations
    group_ai_session.py    ← new: helper for group ADK session IDs
  
hip-frontend/
  lib/
    groupApi.ts            ← new: all group API calls
  components/
    GroupChatWindow.tsx    ← new: group chat UI (replaces ChatWindow col 3 for groups)
    CreateGroupModal.tsx   ← new: create group with member picker
```

Files to modify:
```
hip/main.py                     ← add group endpoints
hip/my_agent/agent.py           ← update before_tool_guardrail for group sender_user_id
hip-frontend/context/ChatContext.tsx    ← add group state + refresh
hip-frontend/components/ConversationList.tsx  ← show groups + wire Groups filter pill
hip-frontend/components/ChatWindow.tsx        ← conditional render GroupChatWindow
hip-frontend/components/Message.tsx           ← add optional senderLabel prop
```

---

## Implementation Order

1. `hip/data/groups.py` — DB schema + all data functions
2. `hip/main.py` — add all group endpoints + `/users`
3. `hip/my_agent/agent.py` — update guardrail for group sender
4. `hip-frontend/lib/groupApi.ts` — all API functions
5. `hip-frontend/context/ChatContext.tsx` — group state
6. `hip-frontend/components/CreateGroupModal.tsx`
7. `hip-frontend/components/GroupChatWindow.tsx`
8. `hip-frontend/components/ConversationList.tsx` — wire groups in
9. `hip-frontend/components/ChatWindow.tsx` — conditional render
10. `hip-frontend/components/Message.tsx` — senderLabel

---

## Open Questions / Decisions

- **Bot trigger**: does the bot respond to every message, or only when `@bot` is mentioned? Recommendation: respond to every message if bot is a member (like a group assistant), but add an option per group to set it to "mention only" in Phase 2.
- **Artifact ownership**: PDFs generated in group context are stored under the group's synthetic userId. The download URL uses `group_{group_id}` as userId. All members can download — no per-user restriction needed.
- **Group deletion**: only the creator can delete. Members can leave (self-remove). Deleting the group cascades to messages and members.
- **Message history limit**: fetch last 50 on open, paginate backwards with `before` param as messages scroll up.
